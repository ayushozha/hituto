"""Document ingestion orchestration: upload → parse → chunk → index.

`run_source_ingestion` looks up `SessionLocal` from this module's globals, so tests can
monkeypatch `app.rag.ingest.SessionLocal` to redirect the background DB session.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.tasks import spawn
from ..models import SourceChunk, SourceDocument
from ..providers import storage
from .chunk import chunk_document, detect_headings
from .liteparse_adapter import (
    CanonicalParse,
    canonical_to_parsed_document,
    dump_manifest,
    get_liteparse_engine,
    parse_canonical,
    source_hash_of,
)
from .outline import build_document_outline
from .passages import build_passage_specs, persist_passage_specs
from .teaching_map import (
    build_teaching_map_for_ingest,
    extract_teaching_map_llm,
    materialize_chapter_md,
    ocr_quality_below_threshold,
)

logger = logging.getLogger(__name__)

_EMBED_BATCH = 64  # texts per embedding request — bounds request size for big docs
_EMBED_BATCH_TIMEOUT = 120  # seconds per batch — a stalled provider can't hang ingestion forever

# Status values recoverable after process restart (ISA-4 / rag-context §5.0.1).
# `outlining` / `mapping` land with Phase 2; included early so recovery is ready.
NON_TERMINAL_INGEST_STATUSES = (
    "uploaded",
    "parsing",
    "outlining",
    "mapping",
    "chunking",
    "indexing",
)


def _upload_dir() -> Path:
    d = Path(get_settings().upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_and_ingest(
    db: Session,
    *,
    user_id: str,
    filename: str | None,
    content_type: str | None,
    ext: str,
    data: bytes,
) -> SourceDocument:
    """Persist the upload to InsForge storage, then kick off background ingestion.

    Primary path: store the bytes in InsForge Storage. Fallback (storage unconfigured, e.g. offline/stub tests): local disk.
    Either way the resulting locator is handed to the background ingestion task.
    """
    doc = SourceDocument(
        user_id=user_id,
        filename=filename or "upload",
        mime_type=content_type or "application/octet-stream",
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    source_map: dict = {}
    locator: str | None = None
    if storage.is_configured():
        key = f"sources/{doc.id}{ext or '.bin'}"
        try:
            res = await storage.upload(key, data, doc.mime_type)
            # Trust the returned key: the API auto-renames on conflict (e.g. "name (1)").
            stored_key = res.get("key", key)
            source_map = {
                "storage_bucket": get_settings().storage_bucket,
                "storage_key": stored_key,
                "storage_url": res.get("url"),
            }
            locator = stored_key
        except Exception as e:  # noqa: BLE001 — storage down → degrade to local disk
            source_map = {"storage_error": str(e)}

    if locator is None:  # storage unconfigured or upload failed → local disk
        stored = _upload_dir() / f"{doc.id}{ext or '.bin'}"
        stored.write_bytes(data)
        source_map["stored_path"] = str(stored)
        locator = str(stored)

    doc.source_map = source_map
    db.commit()
    spawn(run_source_ingestion(doc.id, locator, doc.mime_type, doc.filename), name=f"ingest:{doc.id}")
    return doc


async def _read_source_bytes(locator: str) -> bytes:
    """Resolve a source locator to bytes: a local path if it exists, else a InsForge storage object id / logical key."""
    p = Path(locator)
    if p.exists():
        return p.read_bytes()
    return await storage.download(locator)


async def _embed_all(texts: list[str], embedder) -> list[list[float]]:
    """Embed in bounded batches, each under a timeout. Raises on failure so the caller can
    degrade to keyword-only retrieval rather than persisting a half-embedded document."""
    out: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        batch = texts[start : start + _EMBED_BATCH]
        vecs = await asyncio.wait_for(embedder.embed_texts(batch), timeout=_EMBED_BATCH_TIMEOUT)
        out.extend(vecs)
    return out


def _source_locator(doc: SourceDocument) -> str | None:
    """The locator run_source_ingestion needs: InsForge object id / logical key, else local stored_path."""
    sm = doc.source_map or {}
    return sm.get("storage_key") or sm.get("stored_path")


def recover_orphaned_ingestions() -> int:
    """Requeue source documents stranded mid-ingestion by a previous process.

    Ingestion runs as an in-memory task (see core.tasks.spawn); a restart — uvicorn --reload
    on a code save, or a crash — kills any in-flight parse/chunk/embed while the row stays in a
    non-terminal state forever ("stuck ingesting"). Because uploads are now durable in InsForge
    storage, we can re-download and re-run ingestion. Rows with no recoverable locator are marked
    failed so the UI stops spinning. Returns the number of sources requeued. Call at startup while
    the event loop is running.
    """
    requeued = 0
    with SessionLocal() as db:
        stuck = db.scalars(
            select(SourceDocument).where(SourceDocument.status.in_(NON_TERMINAL_INGEST_STATUSES))
        ).all()
        for doc in stuck:
            if doc.source_type == "video":
                # Video recovery owns transcription before reusing this text-ingestion pipeline.
                continue
            locator = _source_locator(doc)
            if locator:
                spawn(
                    run_source_ingestion(doc.id, locator, doc.mime_type, doc.filename),
                    name=f"reingest:{doc.id}",
                )
                requeued += 1
            else:
                doc.status = "failed"
                doc.error = "ingestion interrupted and no stored file to recover — re-upload"
        db.commit()
    return requeued


def _parse_root(upload_dir: Path, source_id: str, source_hash: str) -> Path:
    """Local mirror of `sources/{id}/parses/{hash}/` (hash includes `sha256:` prefix stripped)."""
    h = source_hash.removeprefix("sha256:")
    return upload_dir / "parses" / source_id / h


async def _store_bytes(key: str, data: bytes, content_type: str, *, local_path: Path) -> str:
    """Write parse artifacts to InsForge when configured, always also to local_path for tests.

    Returns the locator callers should persist: the remote key on a successful upload,
    otherwise the absolute local path so RAG can still load the artifact.
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    if storage.is_configured():
        try:
            res = await storage.upload(key, data, content_type)
            return res.get("key", key)
        except Exception as exc:  # noqa: BLE001 — keep local; ingest must not fail solely on storage
            logger.warning("storage upload failed for %s — using local %s (%s)", key, local_path, exc)
            return str(local_path.resolve())
    return str(local_path.resolve())


async def _persist_canonical_artifacts(
    doc: SourceDocument,
    canon: CanonicalParse,
    *,
    upload_dir: Path,
) -> dict:
    """Write document.md, parse_manifest.json, figures; return source_map['parse']."""
    h = canon.source_hash or source_hash_of(canon.document_md.encode())
    prefix = f"sources/{doc.id}/parses/{h.removeprefix('sha256:')}"
    root = _parse_root(upload_dir, doc.id, h)

    md_key = f"{prefix}/document.md"
    manifest_key = f"{prefix}/parse_manifest.json"
    md_loc = await _store_bytes(
        md_key, canon.document_md.encode("utf-8"), "text/markdown", local_path=root / "document.md"
    )

    figure_entries: list[dict] = []
    for fig in canon.figures:
        fig_name = f"{fig.image_id}.{fig.format.lstrip('.') or 'png'}"
        fig_key = f"{prefix}/figures/{fig_name}"
        ctype = "image/png" if fig.format in ("png",) else f"image/{fig.format}"
        stored = await _store_bytes(fig_key, fig.data, ctype, local_path=root / "figures" / fig_name)
        entry = {
            "image_id": fig.image_id,
            # Prefer whatever `_store_bytes` returned — local path when InsForge upload fails.
            "storage_key": stored,
            "page": fig.page,
            "element_id": fig.element_id,
            "md_ref": fig.md_ref or fig_name,
        }
        figure_entries.append(entry)

    # Stamp storage keys into the durable manifest before writing it.
    manifest = dict(canon.manifest)
    manifest["source_hash"] = h
    manifest_figures = []
    fig_by_id = {f["image_id"]: f for f in figure_entries}
    for raw in manifest.get("figures") or []:
        merged = dict(raw)
        match = fig_by_id.get(merged.get("figure_id") or merged.get("image_id") or "")
        if match:
            merged["storage_key"] = match["storage_key"]
            merged.setdefault("md_ref", match.get("md_ref"))
        manifest_figures.append(merged)
    if not manifest_figures:
        manifest_figures = [
            {
                "figure_id": f["image_id"],
                "storage_key": f["storage_key"],
                "page": f.get("page"),
                "element_id": f.get("element_id"),
                "md_ref": f.get("md_ref"),
            }
            for f in figure_entries
        ]
    manifest["figures"] = manifest_figures

    man_loc = await _store_bytes(
        manifest_key, dump_manifest(manifest), "application/json", local_path=root / "parse_manifest.json"
    )

    return {
        "source_hash": h,
        "parser_name": canon.parser_name,
        "parser_version": canon.parser_version,
        # Use returned locators (remote key on success, local path when storage upload fails).
        "document_md_key": md_loc,
        "manifest_key": man_loc,
        "figures": figure_entries,
        "quality": dict(canon.quality or {}),
    }


async def _materialize_chapter_files(
    doc: SourceDocument,
    document_md: str,
    outline: dict,
    teaching: dict,
    *,
    source_hash: str,
    upload_dir: Path,
) -> dict:
    """Write chapter.md files and stamp md_key onto each teaching chapter."""
    h = source_hash.removeprefix("sha256:")
    prefix = f"sources/{doc.id}/parses/{h}/chapters"
    root = _parse_root(upload_dir, doc.id, source_hash) / "chapters"
    chapters_out: list[dict] = []
    for ch in teaching.get("chapters") or []:
        body, _spans, _el = materialize_chapter_md(
            document_md, outline, list(ch.get("source_node_ids") or [])
        )
        fig_name = f"{ch['id']}.md"
        key = f"{prefix}/{fig_name}"
        loc = await _store_bytes(
            key, body.encode("utf-8"), "text/markdown", local_path=root / fig_name
        )
        entry = dict(ch)
        entry["md_key"] = loc
        entry["token_count"] = entry.get("token_count") or max(1, len(body.split()))
        chapters_out.append(entry)
    out = dict(teaching)
    out["chapters"] = chapters_out
    return out


async def run_source_ingestion(source_id: str, locator: str, mime_type: str, filename: str) -> None:
    """Background ingestion: parse -> chunk -> persist. Failures land as status=failed.

    `locator` is a local filesystem path (tests / local-disk fallback) or a InsForge
    storage key; `_read_source_bytes` resolves either.

    When enabled (default), PDFs and MD/TXT go through the canonical LiteParse
    adapter and write versioned parse artifacts, outline, and teaching_map.
    """
    settings = get_settings()
    db = SessionLocal()
    try:
        doc = db.get(SourceDocument, source_id)
        if not doc:
            return
        doc.status = "parsing"
        db.commit()

        data = await _read_source_bytes(locator)
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise ValueError(f"source exceeds max upload size ({len(data)} > {max_bytes})")

        # Always LiteParse / text adapter (Phase 5 — PyMuPDF path removed).
        last_err: Exception | None = None
        canon: CanonicalParse | None = None
        for attempt in range(2):
            try:
                canon = await asyncio.wait_for(
                    asyncio.to_thread(
                        parse_canonical,
                        data,
                        mime_type,
                        filename,
                        max_pages=settings.max_pages,
                        max_bytes=max_bytes,
                        ocr_setting=settings.rag_ocr_enabled,
                        engine=get_liteparse_engine(),
                    ),
                    timeout=settings.parse_timeout_s,
                )
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt == 0:
                    continue
        if last_err is not None:
            raise last_err
        assert canon is not None
        if canon.page_count > settings.max_pages:
            raise ValueError(f"page count {canon.page_count} exceeds MAX_PAGES={settings.max_pages}")
        if ocr_quality_below_threshold(
            canon.quality,
            min_confidence=settings.rag_ocr_min_confidence,
            ocr_was_enabled=bool((canon.quality or {}).get("ocr_enabled")),
        ):
            raise ValueError("ocr_quality_below_threshold")

        parse_meta = await _persist_canonical_artifacts(doc, canon, upload_dir=_upload_dir())
        source_map = dict(doc.source_map or {})
        source_map["parse"] = parse_meta
        source_map.pop("concept_dag", None)
        doc.source_map = source_map
        db.commit()

        doc.status = "outlining"
        db.commit()
        outline = build_document_outline(
            canon.document_md,
            canon.manifest,
            source_unit_tokens=settings.rag_source_unit_tokens,
        )
        source_map = dict(doc.source_map or {})
        source_map["document_outline"] = outline
        doc.source_map = source_map
        db.commit()

        doc.status = "mapping"
        db.commit()
        llm_map = None
        if settings.rag_tree_enabled:
            try:
                from ..providers.registry import get_llm

                llm_map = await extract_teaching_map_llm(
                    document_md=canon.document_md,
                    outline=outline,
                    llm=get_llm(),
                    model_name=settings.llm_model,
                    full_token_budget=settings.rag_tree_full_tokens,
                    context_window=settings.rag_tree_context_window,
                    output_reserve=settings.rag_tree_output_reserve,
                )
            except Exception:  # noqa: BLE001 — fallback teaching map
                llm_map = None
        teaching = build_teaching_map_for_ingest(
            canon.document_md,
            outline,
            tree_enabled=settings.rag_tree_enabled,
            llm_map=llm_map,
            lesson_context_tokens=settings.rag_lesson_context_tokens,
        )
        teaching = await _materialize_chapter_files(
            doc,
            canon.document_md,
            outline,
            teaching,
            source_hash=canon.source_hash,
            upload_dir=_upload_dir(),
        )
        source_map = dict(doc.source_map or {})
        source_map["teaching_map"] = teaching
        source_map.pop("concept_dag", None)
        doc.source_map = source_map
        if teaching.get("document_kind") in ("paper", "textbook", "lecture_notes", "slides"):
            doc.source_type = {
                "paper": "paper",
                "textbook": "textbook",
                "lecture_notes": "notes",
                "slides": "notes",
            }.get(teaching["document_kind"], doc.source_type)
        db.commit()

        parsed = canonical_to_parsed_document(canon)

        doc.page_count = parsed.page_count
        doc.full_text = parsed.full_text[:500_000]  # cap to keep the row sane
        if not doc.source_type:
            doc.source_type = "paper" if parsed.kind == "pdf" else "notes"
        if not doc.title:
            first = next(
                (ln.strip().lstrip("# ") for ln in parsed.full_text.splitlines() if len(ln.strip()) > 8),
                None,
            )
            doc.title = (first or doc.filename)[:160]
        m = re.search(r"(?im)^\s*abstract\b[:.]?\s*(.+)", parsed.full_text)
        if m:
            doc.abstract = m.group(1).strip()[:1000]
        doc.status = "chunking"
        db.commit()

        # Idempotent re-ingestion: clear prior chunks before rewriting.
        for old in list(doc.chunks):
            db.delete(old)
        db.flush()

        teaching = (doc.source_map or {}).get("teaching_map") or {}
        outline = (doc.source_map or {}).get("document_outline") or {}
        use_passages = bool(
            settings.rag_chapter_embed
            and teaching.get("chapters")
            and outline.get("nodes")
        )

        chunks_for_embed: list = []
        if use_passages:
            specs = build_passage_specs(
                canon.document_md,
                outline,
                teaching,
                source_hash=canon.source_hash,
                parse_version=1,
                size_tokens=settings.chunk_size_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            embeddings = None
            if settings.vector_store == "pgvector" and specs:
                doc.status = "indexing"
                db.commit()
                try:
                    from ..providers.registry import get_embedder

                    embeddings = await _embed_all([s.text for s in specs], get_embedder())
                except Exception:
                    embeddings = None
            persist_passage_specs(
                db, doc=doc, specs=specs, embeddings=embeddings, start_index=0
            )
            chunks_for_embed = specs
        else:
            chunks = chunk_document(
                parsed,
                size_tokens=settings.chunk_size_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            embeddings = None
            if settings.vector_store == "pgvector" and chunks:
                doc.status = "indexing"
                db.commit()
                try:
                    from ..providers.registry import get_embedder

                    embeddings = await _embed_all([c.text for c in chunks], get_embedder())
                except Exception:
                    embeddings = None
            for i, c in enumerate(chunks):
                db.add(
                    SourceChunk(
                        source_document_id=source_id,
                        user_id=doc.user_id,
                        chunk_index=c.chunk_index,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        section_title=c.section_title,
                        heading_path=c.heading_path,
                        text=c.text,
                        token_count=c.token_count,
                        embedding=(embeddings[i] if embeddings else None),
                    )
                )
            chunks_for_embed = chunks

        sections = detect_headings(parsed.full_text)
        if not sections and use_passages:
            for ch in teaching.get("chapters") or []:
                t = ch.get("title")
                if t and t not in sections:
                    sections.append(t)
        elif not sections:
            for c in chunks_for_embed:
                st = getattr(c, "section_title", None)
                if st and st not in sections:
                    sections.append(st)
        source_map = dict(doc.source_map or {})
        source_map["sections"] = sections
        source_map.pop("concept_dag", None)
        doc.source_map = source_map
        quality = {
            "chunk_count": len(chunks_for_embed),
            "ok": bool(parsed.full_text.strip()),
            "low_text": len(parsed.full_text.strip()) < 200,
            "passage_index": use_passages,
            "parser": canon.parser_name,
            "parser_version": canon.parser_version,
            "source_hash": canon.source_hash,
        }
        quality.update({k: v for k, v in (canon.quality or {}).items() if k not in quality})
        doc.extraction_quality = quality
        doc.status = "ready"
        db.commit()
    except Exception as e:  # noqa: BLE001 — record, don't hide (R1.6)
        db.rollback()
        try:
            doc = db.get(SourceDocument, source_id)
            if doc:
                doc.status = "failed"
                doc.error = str(e)[:2000]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()

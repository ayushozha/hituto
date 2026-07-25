"""Lazy upgrade for pre-cutover source documents (rag-context §5.2.1).

`ensure_parse_artifacts` / `ensure_knowledge_tree` run on first course-from-source or
retrieve that needs a teaching map. Prefer re-parsing original bytes through LiteParse;
else build outline + fallback teaching map from `full_text`. Never 500 the tutor.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import SourceDocument
from ..providers import storage
from .liteparse_adapter import parse_canonical, source_hash_of
from .outline import build_document_outline
from .passages import build_passage_specs, persist_passage_specs
from .teaching_map import build_teaching_map_for_ingest, materialize_chapter_md

logger = logging.getLogger(__name__)


def _has_teaching_map(doc: SourceDocument) -> bool:
    return bool(((doc.source_map or {}).get("teaching_map") or {}).get("chapters"))


def _has_parse(doc: SourceDocument) -> bool:
    return bool((doc.source_map or {}).get("parse"))


async def _read_original_bytes(doc: SourceDocument) -> bytes | None:
    sm = doc.source_map or {}
    locator = sm.get("stored_path") or sm.get("storage_key")
    if not locator:
        return None
    p = Path(str(locator))
    if p.exists():
        try:
            return p.read_bytes()
        except Exception as exc:  # noqa: BLE001
            logger.warning("legacy re-read local failed for %s: %s", locator, exc)
            return None
    if storage.is_configured():
        try:
            return await storage.download(str(locator), bucket=sm.get("storage_bucket"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("legacy re-read storage failed for %s: %s", locator, exc)
    return None


def _text_adapter_manifest(md: str) -> dict:
    from .liteparse_adapter import parse_text_canonical

    return parse_text_canonical(md.encode("utf-8"), kind="markdown").manifest


async def ensure_parse_artifacts(db: Session, doc: SourceDocument) -> SourceDocument:
    """Ensure `source_map.parse` (+ document.md body available via full_text / keys).

    Re-parses original bytes when possible; otherwise synthesizes a text-adapter parse
    pointer from existing `full_text`. Idempotent when parse already present.
    """
    if _has_parse(doc) and (doc.full_text or "").strip():
        return doc

    settings = get_settings()
    sm = dict(doc.source_map or {})
    data = await _read_original_bytes(doc)
    try:
        if data:
            canon = parse_canonical(
                data,
                doc.mime_type or "",
                doc.filename or "",
                max_pages=settings.max_pages,
                ocr_setting=settings.rag_ocr_enabled,
            )
        elif (doc.full_text or "").strip():
            from .liteparse_adapter import parse_text_canonical

            canon = parse_text_canonical((doc.full_text or "").encode("utf-8"), kind="markdown")
            canon.source_hash = source_hash_of((doc.full_text or "").encode("utf-8"))
            canon.manifest["source_hash"] = canon.source_hash
        else:
            return doc

        if not doc.full_text:
            doc.full_text = canon.document_md[:500_000]
        if not doc.page_count:
            doc.page_count = canon.page_count
        sm["parse"] = {
            "source_hash": canon.source_hash,
            "parser_name": canon.parser_name,
            "parser_version": canon.parser_version,
            "document_md_key": None,  # lazy path may not rewrite bucket
            "manifest_key": None,
            "figures": [],
            "quality": dict(canon.quality or {}),
            "lazy": True,
        }
        # Stash markdown on a synthetic key field for rematerialize (full_text is canonical here).
        sm["_lazy_document_md"] = canon.document_md
        sm["_lazy_manifest"] = canon.manifest
        doc.source_map = sm
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception as exc:  # noqa: BLE001 — never block callers
        logger.warning("ensure_parse_artifacts failed for %s: %s", doc.id, exc)
        db.rollback()
    return doc


async def ensure_knowledge_tree(db: Session, doc: SourceDocument) -> SourceDocument:
    """Ensure `document_outline` + `teaching_map` exist (fallback map if needed).

    Also indexes passage rows when `RAG_CHAPTER_EMBED` and no passage meta rows yet.
    """
    doc = await ensure_parse_artifacts(db, doc)
    if _has_teaching_map(doc):
        return doc

    settings = get_settings()
    sm = dict(doc.source_map or {})
    md = sm.get("_lazy_document_md") or doc.full_text or ""
    if not md.strip():
        return doc

    try:
        manifest = sm.get("_lazy_manifest") or _text_adapter_manifest(md)
        outline = sm.get("document_outline") or build_document_outline(
            md, manifest, source_unit_tokens=settings.rag_source_unit_tokens
        )
        teaching = build_teaching_map_for_ingest(
            md,
            outline,
            tree_enabled=False,  # lazy path always uses fallback map (no LLM at request time)
            lesson_context_tokens=settings.rag_lesson_context_tokens,
        )
        # Stamp md_key as None — materialize via rematerialize from full_text.
        for ch in teaching.get("chapters") or []:
            body, _, _ = materialize_chapter_md(md, outline, list(ch.get("source_node_ids") or []))
            ch["token_count"] = ch.get("token_count") or max(1, len(body.split()))
            ch.setdefault("md_key", None)

        sm["document_outline"] = outline
        sm["teaching_map"] = teaching
        sm.pop("concept_dag", None)
        if not sm.get("sections"):
            sm["sections"] = [c.get("title") for c in teaching.get("chapters") or [] if c.get("title")]
        doc.source_map = sm
        db.add(doc)
        db.flush()

        if settings.rag_chapter_embed:
            has_passage = any(
                (c.chunk_meta or {}).get("kind") == "passage" for c in (doc.chunks or [])
            )
            if not has_passage:
                specs = build_passage_specs(
                    md,
                    outline,
                    teaching,
                    source_hash=(sm.get("parse") or {}).get("source_hash"),
                    size_tokens=settings.chunk_size_tokens,
                    overlap_tokens=settings.chunk_overlap_tokens,
                )
                start = max((c.chunk_index for c in (doc.chunks or [])), default=-1) + 1
                persist_passage_specs(db, doc=doc, specs=specs, start_index=start)

        db.commit()
        db.refresh(doc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_knowledge_tree failed for %s: %s", doc.id, exc)
        db.rollback()
    return doc


async def backfill_maps(db: Session, *, limit: int = 50) -> int:
    """Ops helper: upgrade up to `limit` ready docs missing a teaching_map. Returns count."""
    from sqlalchemy import select

    rows = db.scalars(
        select(SourceDocument).where(SourceDocument.status == "ready").limit(limit * 4)
    ).all()
    n = 0
    for doc in rows:
        if _has_teaching_map(doc):
            continue
        await ensure_knowledge_tree(db, doc)
        db.refresh(doc)
        if _has_teaching_map(doc):
            n += 1
        if n >= limit:
            break
    return n

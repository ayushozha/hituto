"""Shared lesson RAG context — pack-first, teaching-map, then live retrieve, then none."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Course, Lesson, LessonSourcePack, SourceChunk, SourceDocument
from ..providers import storage
from .passages import excerpt_from_chunk
from .retrieve import rank_chunks, retrieve_passages
from .teaching_map import materialize_chapter_md

# "chapter" = pack-backed (chapter_ids + passages/chunks).
# "retrieve" = live search over the source document.
# "none" = web-discovery / no source.
LessonRagMode = Literal["chapter", "retrieve", "none"]


@dataclass
class LessonRagContext:
    mode: LessonRagMode
    source_document_id: Optional[str] = None
    excerpts: list[dict[str, Any]] = field(default_factory=list)
    chapter_ids: list[str] = field(default_factory=list)
    passage_ids: list[str] = field(default_factory=list)
    pack_id: Optional[str] = None
    retrieval_query: Optional[str] = None


@dataclass
class TeachingMapView:
    """Validated view over `source_map.teaching_map`."""

    status: str
    document_kind: str
    document_summary: str
    thesis: str | None
    chapters: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass
class ChapterContext:
    chapter_id: str
    title: str
    summary: str
    markdown: str
    document_summary: str
    thesis: str | None
    source_node_ids: list[str]
    neighbor_titles: list[str]
    figure_storage_keys: list[str]
    token_count: int
    md_key: str | None = None


def _excerpt(c: SourceChunk) -> dict[str, Any]:
    return {
        "id": c.id[:8],
        "page_start": c.page_start,
        "page_end": c.page_end,
        "section_title": c.section_title,
        "text": (c.text or "")[:600],
    }


def _latest_pack(db: Session, lesson_id: str) -> LessonSourcePack | None:
    return db.scalars(
        select(LessonSourcePack)
        .where(LessonSourcePack.lesson_id == lesson_id)
        .order_by(LessonSourcePack.created_at.desc())
    ).first()


def _chunks_by_ids(db: Session, chunk_ids: list[str]) -> list[SourceChunk]:
    if not chunk_ids:
        return []
    by_id = {
        c.id: c
        for c in db.scalars(select(SourceChunk).where(SourceChunk.id.in_(chunk_ids))).all()
    }
    # Preserve pack order.
    return [by_id[i] for i in chunk_ids if i in by_id]


def get_teaching_map(db: Session, *, doc: SourceDocument) -> TeachingMapView | None:
    """Return the durable teaching map, or None if the doc has not been mapped yet.

    Callers that need a map on legacy docs should `await ensure_knowledge_tree` first.
    """
    _ = db
    raw = (doc.source_map or {}).get("teaching_map")
    if not isinstance(raw, dict) or not raw.get("chapters"):
        return None
    return TeachingMapView(
        status=str(raw.get("status") or "unknown"),
        document_kind=str(raw.get("document_kind") or "unknown"),
        document_summary=str(raw.get("document_summary") or ""),
        thesis=(str(raw["thesis"]) if raw.get("thesis") else None),
        chapters=list(raw.get("chapters") or []),
        raw=raw,
    )


# Legacy alias during migration.
get_knowledge_tree = get_teaching_map


def teaching_map_chapter(doc: SourceDocument, chapter_id: str) -> dict | None:
    tm = (doc.source_map or {}).get("teaching_map") or {}
    for ch in tm.get("chapters") or []:
        if ch.get("id") == chapter_id:
            return ch
    return None


async def _load_bytes(locator: str) -> bytes:
    p = Path(locator)
    if p.exists():
        return p.read_bytes()
    if storage.is_configured():
        return await storage.download(locator)
    raise FileNotFoundError(locator)


async def get_chapter_context(
    db: Session,
    *,
    doc: SourceDocument,
    chapter_id: str,
    lesson_context_tokens: int | None = None,
) -> ChapterContext:
    """Load verbatim chapter Markdown (from md_key, or re-materialize from outline spans).

    Never blind-truncates: if over budget, returns the full body and callers may split
    into scoped teaching units (token_count reflects the full materialized size).
    """
    _ = db
    from ..core.config import get_settings

    budget = lesson_context_tokens
    if budget is None:
        budget = get_settings().rag_lesson_context_tokens

    tm = get_teaching_map(db, doc=doc)
    if tm is None:
        raise ValueError(f"no teaching_map for source {doc.id}")
    ch = teaching_map_chapter(doc, chapter_id)
    if ch is None:
        raise ValueError(f"unknown teaching chapter_id: {chapter_id}")

    chapters = tm.chapters
    idx = next((i for i, c in enumerate(chapters) if c.get("id") == chapter_id), -1)
    neighbors: list[str] = []
    if idx > 0:
        neighbors.append(str(chapters[idx - 1].get("title") or ""))
    if 0 <= idx < len(chapters) - 1:
        neighbors.append(str(chapters[idx + 1].get("title") or ""))

    markdown = ""
    md_key = ch.get("md_key")
    if md_key:
        try:
            markdown = (await _load_bytes(str(md_key))).decode("utf-8")
        except Exception:  # noqa: BLE001 — fall through to rematerialize
            markdown = ""

    if not markdown:
        outline = (doc.source_map or {}).get("document_outline") or {}
        parse = (doc.source_map or {}).get("parse") or {}
        document_md = doc.full_text or ""
        # Prefer canonical document.md when available.
        doc_md_key = parse.get("document_md_key")
        if doc_md_key:
            try:
                document_md = (await _load_bytes(str(doc_md_key))).decode("utf-8")
            except Exception:  # noqa: BLE001
                pass
        markdown, _spans, _el = materialize_chapter_md(
            document_md, outline, list(ch.get("source_node_ids") or [])
        )

    # Oversized: do NOT blind-truncate (3.6). Callers may split teaching units.
    token_count = int(ch.get("token_count") or max(1, len(markdown.split())))
    _ = budget  # used by planner/split path; context returns full verbatim body

    figure_keys = list(ch.get("figure_image_ids") or [])
    # Resolve to storage keys via parse.figures when ids are image_ids.
    parse_figures = ((doc.source_map or {}).get("parse") or {}).get("figures") or []
    by_id = {f.get("image_id"): f.get("storage_key") for f in parse_figures if f.get("image_id")}
    storage_keys = [by_id[i] for i in figure_keys if i in by_id and by_id[i]]
    if not storage_keys:
        # Prefer figures whose pages overlap chapter evidence (best-effort).
        storage_keys = [f.get("storage_key") for f in parse_figures if f.get("storage_key")][:3]

    return ChapterContext(
        chapter_id=chapter_id,
        title=str(ch.get("title") or chapter_id),
        summary=str(ch.get("summary") or ""),
        markdown=markdown,
        document_summary=tm.document_summary,
        thesis=tm.thesis,
        source_node_ids=list(ch.get("source_node_ids") or []),
        neighbor_titles=[t for t in neighbors if t],
        figure_storage_keys=[k for k in storage_keys if k],
        token_count=token_count,
        md_key=str(md_key) if md_key else None,
    )


# Legacy alias.
rag_chapter = get_chapter_context


def resolve_visual_candidates(doc: SourceDocument, chapter_ids: list[str]) -> list[dict]:
    """Figures linked to the lesson's teaching chapters (prefer over /gen)."""
    parse = (doc.source_map or {}).get("parse") or {}
    figures = list(parse.get("figures") or [])
    if not figures:
        return []
    # Prefer chapters' figure_image_ids; else return all parse figures as candidates.
    wanted: set[str] = set()
    tm = (doc.source_map or {}).get("teaching_map") or {}
    for ch in tm.get("chapters") or []:
        if ch.get("id") in chapter_ids:
            for fid in ch.get("figure_image_ids") or []:
                wanted.add(fid)
    if wanted:
        return [f for f in figures if f.get("image_id") in wanted]
    return figures


def validate_lesson_scopes(
    teaching_map: dict,
    lesson_scopes: dict,
    *,
    selected_outline_nodes: list[str] | None = None,
) -> list[str]:
    """Structural grounding checks. Returns list of error strings (empty = ok)."""
    errors: list[str] = []
    chapters = {c["id"]: c for c in (teaching_map.get("chapters") or []) if c.get("id")}
    outline_ok = selected_outline_nodes
    for ordinal, scope in (lesson_scopes or {}).items():
        ids = list((scope or {}).get("chapter_ids") or [])
        if not ids:
            errors.append(f"lesson_{ordinal}_empty_chapter_ids")
            continue
        for cid in ids:
            if cid not in chapters:
                errors.append(f"unknown_chapter_id:{cid}")
                continue
            if outline_ok is not None:
                for nid in chapters[cid].get("source_node_ids") or []:
                    if nid not in outline_ok:
                        errors.append(f"chapter_{cid}_node_outside_selection:{nid}")
    return errors


def _excerpt_dict_from_source_excerpt(ex) -> dict[str, Any]:
    return {
        "id": (ex.chunk_id or "")[:8] or "pass",
        "page_start": ex.page_start,
        "page_end": ex.page_end,
        "section_title": ex.section_title,
        "text": ex.text,
        "chapter_id": ex.chapter_id,
        "outline_node_id": ex.outline_node_id,
        "element_ids": list(ex.element_ids or []),
        "ref_label": ex.ref_label,
        "kind": ex.kind,
    }


async def get_lesson_context(
    db: Session,
    *,
    course: Course,
    lesson: Lesson,
    user_query: Optional[str] = None,
    limit: int = 5,
) -> LessonRagContext:
    """Pack-first chapters/passages → two-stage retrieve → none.

    1. Pack with `chapter_ids` → `retrieve_passages` constrained to those chapters
       (or explicit `passage_ids` / legacy `chunk_ids` when present).
    2. Else document course → two-stage retrieve over the whole teaching map.
    3. Else mode=none.
    """
    sid = (course.knobs or {}).get("source_document_id")
    query = (user_query or lesson.title or "").strip() or None
    # Lesson scopes from coursegen (may exist even before a pack is persisted).
    scopes = (course.knobs or {}).get("lesson_scopes") or {}
    scope = scopes.get(str(lesson.ordinal)) or scopes.get(lesson.ordinal) or {}
    scoped_chapters = list(scope.get("chapter_ids") or [])

    pack = _latest_pack(db, lesson.id)
    if pack is not None:
        chapter_ids = list(getattr(pack, "chapter_ids", None) or []) or scoped_chapters
        passage_ids = list(getattr(pack, "passage_ids", None) or [])
        chunk_ids = list(pack.chunk_ids or [])
        doc_id = pack.source_document_id or sid

        # Prefer explicit passage/chunk soft refs when present (generation-time evidence).
        if passage_ids or (chunk_ids and not chapter_ids):
            ids = passage_ids or chunk_ids
            chunks = _chunks_by_ids(db, ids)
            if query and chunks:
                ranked = rank_chunks(query, chunks, limit=limit)
                chunks = ranked if ranked else chunks[:limit]
            else:
                chunks = chunks[:limit]
            return LessonRagContext(
                mode="chapter",
                source_document_id=doc_id,
                excerpts=[
                    excerpt_from_chunk(c, answer_tokens=get_settings().rag_answer_context_tokens)
                    for c in chunks
                ],
                chapter_ids=chapter_ids,
                passage_ids=passage_ids or [c.id for c in chunks],
                pack_id=pack.id,
                retrieval_query=query or pack.retrieval_query or None,
            )

        if doc_id and chapter_ids:
            excerpts = await retrieve_passages(
                db,
                source_document_id=doc_id,
                user_id=course.user_id,
                query=query or lesson.title or "",
                chapter_ids=chapter_ids,
                limit=limit,
            )
            return LessonRagContext(
                mode="chapter",
                source_document_id=doc_id,
                excerpts=[_excerpt_dict_from_source_excerpt(e) for e in excerpts],
                chapter_ids=chapter_ids,
                passage_ids=[e.chunk_id for e in excerpts if e.chunk_id],
                pack_id=pack.id,
                retrieval_query=query or pack.retrieval_query or None,
            )

        # Pack exists but empty → still mark chapter mode with no excerpts.
        return LessonRagContext(
            mode="chapter",
            source_document_id=doc_id,
            excerpts=[],
            chapter_ids=chapter_ids,
            pack_id=pack.id,
            retrieval_query=query or pack.retrieval_query or None,
        )

    if not sid:
        return LessonRagContext(mode="none", retrieval_query=query)

    # Best-effort lazy upgrade; tutor still works via keyword shim if upgrade fails.
    try:
        from .ensure import ensure_knowledge_tree

        doc = db.get(SourceDocument, sid)
        if doc and not ((doc.source_map or {}).get("teaching_map") or {}).get("chapters"):
            await ensure_knowledge_tree(db, doc)
    except Exception:  # noqa: BLE001
        pass

    # Live two-stage retrieve (optionally constrained by lesson_scopes).
    excerpts = await retrieve_passages(
        db,
        source_document_id=sid,
        user_id=course.user_id,
        query=query or lesson.title or "",
        chapter_ids=scoped_chapters or None,
        limit=limit,
    )
    return LessonRagContext(
        mode="retrieve",
        source_document_id=sid,
        excerpts=[_excerpt_dict_from_source_excerpt(e) for e in excerpts],
        chapter_ids=scoped_chapters,
        passage_ids=[e.chunk_id for e in excerpts if e.chunk_id],
        retrieval_query=query,
    )

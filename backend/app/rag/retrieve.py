"""Source retrieval (tasks.md #15) + two-stage tutor retrieve (rag-context Phase 4).

`rank_chunks` is the pure, testable core; `keyword_search` wraps the DB query. Vector
(pgvector) and chapter-routed passage search layer on top.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import SourceChunk, SourceDocument
from .passages import (
    chapter_id_of,
    chunk_is_chapter_summary,
    chunk_is_passage,
    excerpt_from_chunk,
)

_WORD = re.compile(r"[a-z0-9]+")

logger = logging.getLogger(__name__)


@dataclass
class SourceExcerpt:
    text: str
    chapter_id: str | None = None
    outline_node_id: str | None = None
    element_ids: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    ref_label: str = ""
    chunk_id: str | None = None
    kind: str = "passage"


def _tokens(s: str) -> list[str]:
    return [w for w in _WORD.findall((s or "").lower()) if len(w) > 2]


def rank_chunks(query: str, chunks: Iterable, limit: int = 10) -> list:
    """Rank objects with a `.text` attribute by length-normalized term overlap with the query."""
    q = set(_tokens(query))
    scored: list[tuple[float, object]] = []
    if not q:
        return list(chunks)[:limit]
    for c in chunks:
        ct = _tokens(getattr(c, "text", ""))
        if not ct:
            continue
        overlap = sum(1 for w in ct if w in q)
        if overlap == 0:
            continue
        scored.append((overlap / (len(ct) ** 0.5), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]


def keyword_search(
    db: Session, *, source_document_id: str, user_id: str, query: str, limit: int = 10
) -> list[SourceChunk]:
    rows = db.scalars(
        select(SourceChunk).where(
            SourceChunk.source_document_id == source_document_id,
            SourceChunk.user_id == user_id,
        )
    ).all()
    return rank_chunks(query, rows, limit)


def vector_search(
    db: Session, *, source_document_id: str, user_id: str, query_embedding: list[float], limit: int = 10
) -> list[SourceChunk]:
    """pgvector cosine search (Postgres only). Returns ORM SourceChunks in similarity order."""
    vec = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"
    ordered_ids = db.execute(
        text(
            "SELECT id FROM source_chunks "
            "WHERE source_document_id = :sid AND user_id = :uid AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :lim"
        ),
        {"sid": source_document_id, "uid": user_id, "q": vec, "lim": limit},
    ).scalars().all()
    if not ordered_ids:
        return []
    by_id = {c.id: c for c in db.scalars(select(SourceChunk).where(SourceChunk.id.in_(ordered_ids)))}
    return [by_id[i] for i in ordered_ids if i in by_id]


async def search_source_pack(
    db: Session, *, source_document_id: str, user_id: str, query: str, limit: int = 10
) -> list[SourceChunk]:
    """Retrieve a lesson/tutor source pack: pgvector when configured, else keyword."""
    s = get_settings()
    if s.vector_store == "pgvector" and db.get_bind().dialect.name == "postgresql":
        try:
            from ..providers.registry import get_embedder

            qvec = await get_embedder().embed_query(query)
            hits = vector_search(
                db, source_document_id=source_document_id, user_id=user_id, query_embedding=qvec, limit=limit
            )
            if hits:
                return hits
        except Exception as exc:
            logger.warning("Vector search failed; falling back to keyword retrieval: %s", exc)
    return keyword_search(db, source_document_id=source_document_id, user_id=user_id, query=query, limit=limit)


def _all_doc_chunks(db: Session, *, source_document_id: str, user_id: str) -> list[SourceChunk]:
    return list(
        db.scalars(
            select(SourceChunk).where(
                SourceChunk.source_document_id == source_document_id,
                SourceChunk.user_id == user_id,
            )
        ).all()
    )


def route_chapters(
    query: str,
    chunks: list[SourceChunk],
    *,
    chapter_ids: list[str] | None = None,
    limit: int = 3,
) -> list[str]:
    """Stage 1: pick teaching chapters from chapter_summary rows (or constrain to pack ids)."""
    if chapter_ids:
        summaries = [
            c
            for c in chunks
            if chunk_is_chapter_summary(c) and chapter_id_of(c) in set(chapter_ids)
        ]
        if query and summaries:
            ranked = rank_chunks(query, summaries, limit=limit)
            ordered = [chapter_id_of(c) for c in ranked if chapter_id_of(c)]
            for cid in chapter_ids:
                if cid not in ordered:
                    ordered.append(cid)
            return ordered[: max(limit, len(chapter_ids))]
        return list(chapter_ids)[: max(limit, len(chapter_ids))]

    summaries = [c for c in chunks if chunk_is_chapter_summary(c)]
    if not summaries:
        passages = [c for c in chunks if chunk_is_passage(c)]
        ranked = rank_chunks(query, passages, limit=limit * 3) if query else passages[: limit * 3]
        seen: list[str] = []
        for c in ranked:
            cid = chapter_id_of(c)
            if cid and cid not in seen:
                seen.append(cid)
            if len(seen) >= limit:
                break
        return seen

    ranked = rank_chunks(query, summaries, limit=limit) if query else summaries[:limit]
    out: list[str] = []
    for c in ranked:
        cid = chapter_id_of(c)
        if cid and cid not in out:
            out.append(cid)
    return out


async def retrieve_passages(
    db: Session,
    *,
    source_document_id: str,
    user_id: str,
    query: str,
    chapter_ids: list[str] | None = None,
    limit: int = 5,
) -> list[SourceExcerpt]:
    """Two-stage retrieve: route chapters → search passages inside them → provenance.

    Falls back to legacy keyword/vector search over all chunks when no passage rows exist
    (pre-cutover documents).
    """
    chunks = _all_doc_chunks(db, source_document_id=source_document_id, user_id=user_id)
    passages = [c for c in chunks if chunk_is_passage(c)]
    settings = get_settings()

    if not passages:
        hits = await search_source_pack(
            db,
            source_document_id=source_document_id,
            user_id=user_id,
            query=query or "",
            limit=limit,
        )
        out_legacy: list[SourceExcerpt] = []
        for c in hits:
            ex = excerpt_from_chunk(c, answer_tokens=settings.rag_answer_context_tokens)
            out_legacy.append(
                SourceExcerpt(
                    text=ex["text"],
                    chapter_id=ex.get("chapter_id"),
                    outline_node_id=ex.get("outline_node_id"),
                    element_ids=list(ex.get("element_ids") or []),
                    page_start=ex.get("page_start"),
                    page_end=ex.get("page_end"),
                    section_title=ex.get("section_title"),
                    ref_label=ex.get("ref_label") or "",
                    chunk_id=c.id,
                    kind=str(ex.get("kind") or "passage"),
                )
            )
        return out_legacy

    routed = route_chapters(query or "", chunks, chapter_ids=chapter_ids, limit=3)
    allowed = set(routed) if routed else set(chapter_ids or [])
    pool = [c for c in passages if not allowed or chapter_id_of(c) in allowed]
    if not pool:
        pool = passages

    hits: list[SourceChunk] = []
    if (
        settings.vector_store == "pgvector"
        and db.get_bind().dialect.name == "postgresql"
        and any(c.embedding for c in pool)
    ):
        try:
            wide = await search_source_pack(
                db,
                source_document_id=source_document_id,
                user_id=user_id,
                query=query or "",
                limit=max(limit * 4, 20),
            )
            hits = [
                c
                for c in wide
                if chunk_is_passage(c) and (not allowed or chapter_id_of(c) in allowed)
            ]
            if not hits:
                hits = rank_chunks(query or "", pool, limit=limit)
            else:
                hits = hits[:limit]
        except Exception as exc:
            logger.warning("Passage vector route failed; keyword within chapters: %s", exc)
            hits = rank_chunks(query or "", pool, limit=limit)
    else:
        hits = rank_chunks(query or "", pool, limit=limit) if query else pool[:limit]

    doc = db.get(SourceDocument, source_document_id)
    require_elements = bool(
        doc and ((doc.source_map or {}).get("teaching_map") or {}).get("chapters")
    )
    out: list[SourceExcerpt] = []
    for c in hits:
        meta = c.chunk_meta or {}
        el_ids = list(meta.get("element_ids") or [])
        if require_elements and not el_ids:
            continue
        ex = excerpt_from_chunk(c, answer_tokens=settings.rag_answer_context_tokens)
        out.append(
            SourceExcerpt(
                text=ex["text"],
                chapter_id=ex.get("chapter_id"),
                outline_node_id=ex.get("outline_node_id"),
                element_ids=list(ex.get("element_ids") or []),
                page_start=ex.get("page_start"),
                page_end=ex.get("page_end"),
                section_title=ex.get("section_title"),
                ref_label=ex.get("ref_label") or "",
                chunk_id=c.id,
                kind=str(ex.get("kind") or "passage"),
            )
        )
        if len(out) >= limit:
            break
    return out


async def assemble_source_pack(
    db: Session,
    *,
    source_document_id: str,
    user_id: str,
    query: str,
    dag: dict | None = None,
    lesson_title: str = "",
    limit: int = 10,
) -> list[SourceChunk]:
    """Legacy alias for `search_source_pack`. ``dag`` / ``lesson_title`` are ignored (Phase 5)."""
    _ = (dag, lesson_title)
    return await search_source_pack(
        db, source_document_id=source_document_id, user_id=user_id, query=query, limit=limit
    )

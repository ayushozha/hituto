"""Passage + chapter-summary indexing for two-stage tutor retrieve (rag-context Phase 4).

Reuses `source_chunks` with RAG metadata in `chunk_meta` (`kind`: passage | chapter_summary).
Bodies are verbatim slices of teaching-chapter Markdown — never LLM-paraphrased.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import SourceChunk, SourceDocument
from .chunk import _encoder, _splitter
from .teaching_map import materialize_chapter_md


@dataclass
class PassageSpec:
    text: str
    kind: str  # passage | chapter_summary
    chapter_id: str
    outline_node_id: str | None
    element_ids: list[str]
    section_title: str | None
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    token_count: int
    source_hash: str | None
    parse_version: int


def _token_count(text: str) -> int:
    return len(_encoder().encode(text or "")) or (1 if (text or "").strip() else 0)


def build_passage_specs(
    document_md: str,
    outline: dict,
    teaching_map: dict,
    *,
    source_hash: str | None = None,
    parse_version: int = 1,
    size_tokens: int = 1000,
    overlap_tokens: int = 150,
) -> list[PassageSpec]:
    """Deterministic chapter_summary + passage rows from teaching-map spans."""
    idx = {n["id"]: n for n in (outline or {}).get("nodes") or [] if n.get("id")}
    specs: list[PassageSpec] = []
    for ch in teaching_map.get("chapters") or []:
        cid = str(ch.get("id") or "")
        if not cid:
            continue
        title = str(ch.get("title") or cid)
        summary = str(ch.get("summary") or "")
        route_text = f"{title}\n{summary}".strip()
        node_ids = list(ch.get("source_node_ids") or [])
        element_ids: list[str] = []
        pages: list[int] = []
        for nid in node_ids:
            n = idx.get(nid) or {}
            for eid in n.get("element_ids") or []:
                if eid not in element_ids:
                    element_ids.append(eid)
            for p in (n.get("page_start"), n.get("page_end")):
                if p is not None:
                    pages.append(int(p))
        page_start = min(pages) if pages else None
        page_end = max(pages) if pages else None

        specs.append(
            PassageSpec(
                text=route_text,
                kind="chapter_summary",
                chapter_id=cid,
                outline_node_id=node_ids[0] if node_ids else None,
                element_ids=list(element_ids),
                section_title=title,
                heading_path=[title],
                page_start=page_start,
                page_end=page_end,
                token_count=_token_count(route_text),
                source_hash=source_hash,
                parse_version=parse_version,
            )
        )

        body, _spans, body_els = materialize_chapter_md(document_md, outline, node_ids)
        if not body.strip():
            continue
        splitter = _splitter(size_tokens, overlap_tokens)
        pieces = splitter.split_text(body) or [body]
        for piece in pieces:
            piece = (piece or "").strip()
            if not piece:
                continue
            specs.append(
                PassageSpec(
                    text=piece,
                    kind="passage",
                    chapter_id=cid,
                    outline_node_id=node_ids[0] if node_ids else None,
                    element_ids=list(body_els or element_ids),
                    section_title=title,
                    heading_path=[title],
                    page_start=page_start,
                    page_end=page_end,
                    token_count=_token_count(piece),
                    source_hash=source_hash,
                    parse_version=parse_version,
                )
            )
    return specs


def persist_passage_specs(
    db: Session,
    *,
    doc: SourceDocument,
    specs: list[PassageSpec],
    embeddings: list[list[float]] | None = None,
    start_index: int = 0,
) -> list[SourceChunk]:
    """Insert passage/chapter_summary rows. Caller clears prior RAG rows if re-indexing."""
    out: list[SourceChunk] = []
    for i, spec in enumerate(specs):
        meta = {
            "kind": spec.kind,
            "chapter_id": spec.chapter_id,
            "outline_node_id": spec.outline_node_id,
            "parse_version": spec.parse_version,
            "source_hash": spec.source_hash,
            "element_ids": list(spec.element_ids),
        }
        row = SourceChunk(
            source_document_id=doc.id,
            user_id=doc.user_id,
            chunk_index=start_index + i,
            page_start=spec.page_start,
            page_end=spec.page_end,
            section_title=spec.section_title,
            heading_path=list(spec.heading_path),
            text=spec.text,
            token_count=spec.token_count,
            embedding=(embeddings[i] if embeddings and i < len(embeddings) else None),
            chunk_meta=meta,
        )
        db.add(row)
        out.append(row)
    return out


def chunk_is_passage(c: SourceChunk) -> bool:
    meta = c.chunk_meta or {}
    return meta.get("kind") == "passage"


def chunk_is_chapter_summary(c: SourceChunk) -> bool:
    meta = c.chunk_meta or {}
    return meta.get("kind") == "chapter_summary"


def chapter_id_of(c: SourceChunk) -> str | None:
    meta = c.chunk_meta or {}
    cid = meta.get("chapter_id")
    return str(cid) if cid else None


def excerpt_from_chunk(c: SourceChunk, *, answer_tokens: int = 4000) -> dict[str, Any]:
    """Tutor-facing excerpt with manifest-backed provenance fields."""
    meta = dict(c.chunk_meta or {})
    text = c.text or ""
    # Soft budget: ~4 chars/token approx for injection.
    max_chars = max(200, answer_tokens * 4)
    if len(text) > max_chars:
        text = text[:max_chars]
    title = c.section_title or meta.get("outline_node_id") or "source"
    page = c.page_start
    ref = f"[§{title}"
    if page is not None:
        ref += f", p.{page}"
    ref += "]"
    return {
        "id": c.id[:8],
        "page_start": c.page_start,
        "page_end": c.page_end,
        "section_title": c.section_title,
        "text": text,
        "chapter_id": meta.get("chapter_id"),
        "outline_node_id": meta.get("outline_node_id"),
        "element_ids": list(meta.get("element_ids") or []),
        "kind": meta.get("kind") or "passage",
        "ref_label": ref,
        "source_hash": meta.get("source_hash"),
    }

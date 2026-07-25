"""Document-grounded course models (specs/document-grounded-courses).

SourceDocument / SourceChunk / CourseSource / LessonSourcePack.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.vectortype import VectorColumn
from .base import EMBED_DIM, Base, _now, _uuid


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, default="dev", index=True)
    filename: Mapped[str] = mapped_column(String)
    mime_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    # uploaded|parsing|outlining|mapping|chunking|indexing|ready|failed
    # (outlining/mapping land with rag-context Phase 2)
    status: Mapped[str] = mapped_column(String, default="uploaded")
    title: Mapped[str | None] = mapped_column(String, default=None)
    abstract: Mapped[str | None] = mapped_column(Text, default=None)
    source_type: Mapped[str | None] = mapped_column(
        String, default=None
    )  # paper|textbook|notes|video|unknown — video = public-link ingestion only
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    extraction_quality: Mapped[dict] = mapped_column(JSON, default=dict)
    # locators + parse{} + (Phase 2+) document_outline/teaching_map; legacy sections/concept_dag
    source_map: Mapped[dict] = mapped_column(JSON, default=dict)
    full_text: Mapped[str | None] = mapped_column(Text, default=None)  # small-doc full-context + tutor
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    chunks: Mapped[list["SourceChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="SourceChunk.chunk_index"
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String, default="dev", index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, default=None)
    page_end: Mapped[int | None] = mapped_column(Integer, default=None)
    section_title: Mapped[str | None] = mapped_column(String, default=None)
    heading_path: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    # pgvector Vector on Postgres, JSON list on SQLite (see app/core/vectortype.py)
    embedding: Mapped[list | None] = mapped_column(VectorColumn(EMBED_DIM), default=None)
    # NB: attr `metadata` is reserved by SQLAlchemy declarative Base — use chunk_meta
    chunk_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")


class CourseSource(Base):
    __tablename__ = "course_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    selected_sections: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String, default="paper_walkthrough")


class LessonSourcePack(Base):
    __tablename__ = "lesson_source_packs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    # Soft refs to teaching_map chapter ids / passage chunk ids (rag-context; Alembic c3d4…).
    # Never store teaching chapter ids in chunk_ids.
    chapter_ids: Mapped[list] = mapped_column(JSON, default=list)
    passage_ids: Mapped[list] = mapped_column(JSON, default=list)
    retrieval_query: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

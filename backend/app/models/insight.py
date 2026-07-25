"""Durable personal-learning telemetry and generated insight snapshots."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now, _uuid


class LearningEvent(Base):
    """Append-only, user-owned event used to derive learning metrics."""

    __tablename__ = "learning_events"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_learning_events_user_event"),
        Index("ix_learning_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_learning_events_user_type_occurred", "user_id", "event_type", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    course_id: Mapped[str | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    lesson_id: Mapped[str | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(24), default="web")
    authority: Mapped[str] = mapped_column(String(24), default="client")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class InsightSnapshot(Base):
    """Append-only agent/deterministic narrative tied to an evidence fingerprint."""

    __tablename__ = "insight_snapshots"
    __table_args__ = (Index("ix_insight_snapshots_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    window: Mapped[str] = mapped_column(String(12), default="7d")
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    generator: Mapped[str] = mapped_column(String(24), default="deterministic")
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InsightPreference(Base):
    """User-controlled privacy and collection preferences."""

    __tablename__ = "insight_preferences"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    analytics_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    question_content_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

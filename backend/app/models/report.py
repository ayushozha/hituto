"""Parent-custodied learner records and immutable teacher progress reports."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now, _uuid


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    display_alias: Mapped[str] = mapped_column(String(120))
    grade_band: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linked_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LearnerAccessGrant(Base):
    __tablename__ = "learner_access_grants"
    __table_args__ = (
        CheckConstraint(
            "capability IN ('custody:manage', 'report:create', 'report:view')",
            name="ck_learner_access_capability",
        ),
        UniqueConstraint(
            "learner_id",
            "principal_user_id",
            "capability",
            name="uq_learner_access_principal_capability",
        ),
        Index(
            "uq_learner_access_one_active_custodian",
            "learner_id",
            unique=True,
            sqlite_where=text(
                "capability = 'custody:manage' "
                "AND accepted_at IS NOT NULL AND revoked_at IS NULL"
            ),
            postgresql_where=text(
                "capability = 'custody:manage' "
                "AND accepted_at IS NOT NULL AND revoked_at IS NULL"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    principal_user_id: Mapped[str] = mapped_column(String, index=True)
    principal_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    capability: Mapped[str] = mapped_column(String(40), index=True)
    granted_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ProgressReport(Base):
    __tablename__ = "progress_reports"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_progress_report_version"),
        CheckConstraint("schema_version = 1", name="ck_progress_report_schema_version"),
        CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_progress_report_status",
        ),
        CheckConstraint(
            "evidence_mode = 'teacher_entered'",
            name="ck_progress_report_evidence_mode",
        ),
        CheckConstraint(
            "reporting_period_start IS NULL OR reporting_period_end IS NULL "
            "OR reporting_period_start <= reporting_period_end",
            name="ck_progress_report_period",
        ),
        UniqueConstraint("series_id", "version", name="uq_progress_report_series_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    series_id: Mapped[str] = mapped_column(String, default=_uuid, index=True)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[str] = mapped_column(String, index=True)
    author_display_name: Mapped[str] = mapped_column(String(160))
    reporting_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    reporting_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_mode: Mapped[str] = mapped_column(String(40), default="teacher_entered")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("progress_reports.id"), nullable=True, unique=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ReportDelivery(Base):
    __tablename__ = "report_deliveries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("progress_reports.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReportAuditEvent(Base):
    __tablename__ = "report_audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[str | None] = mapped_column(
        ForeignKey("progress_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    delivery_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_deliveries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

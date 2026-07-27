"""Add the parent-custodied progress report vault.

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h4c5d6e7f8a9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("display_alias", sa.String(length=120), nullable=False),
        sa.Column("grade_band", sa.String(length=80), nullable=True),
        sa.Column("linked_user_id", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learners_linked_user_id", "learners", ["linked_user_id"])
    op.create_index("ix_learners_created_by_user_id", "learners", ["created_by_user_id"])

    op.create_table(
        "learner_access_grants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("learner_id", sa.String(), nullable=False),
        sa.Column("principal_user_id", sa.String(), nullable=False),
        sa.Column("principal_label", sa.String(length=160), nullable=True),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("granted_by_user_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability IN ('custody:manage', 'report:create', 'report:view')",
            name="ck_learner_access_capability",
        ),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "learner_id",
            "principal_user_id",
            "capability",
            name="uq_learner_access_principal_capability",
        ),
    )
    op.create_index(
        "ix_learner_access_grants_learner_id",
        "learner_access_grants",
        ["learner_id"],
    )
    op.create_index(
        "ix_learner_access_grants_principal_user_id",
        "learner_access_grants",
        ["principal_user_id"],
    )
    op.create_index(
        "ix_learner_access_grants_capability",
        "learner_access_grants",
        ["capability"],
    )
    op.create_index(
        "uq_learner_access_one_active_custodian",
        "learner_access_grants",
        ["learner_id"],
        unique=True,
        sqlite_where=sa.text(
            "capability = 'custody:manage' "
            "AND accepted_at IS NOT NULL AND revoked_at IS NULL"
        ),
        postgresql_where=sa.text(
            "capability = 'custody:manage' "
            "AND accepted_at IS NOT NULL AND revoked_at IS NULL"
        ),
    )

    op.create_table(
        "progress_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("learner_id", sa.String(), nullable=False),
        sa.Column("author_user_id", sa.String(), nullable=False),
        sa.Column("author_display_name", sa.String(length=160), nullable=False),
        sa.Column("reporting_period_start", sa.Date(), nullable=True),
        sa.Column("reporting_period_end", sa.Date(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("evidence_mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.String(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_mode = 'teacher_entered'",
            name="ck_progress_report_evidence_mode",
        ),
        sa.CheckConstraint(
            "reporting_period_start IS NULL OR reporting_period_end IS NULL "
            "OR reporting_period_start <= reporting_period_end",
            name="ck_progress_report_period",
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_progress_report_schema_version",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_progress_report_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_progress_report_version"),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["progress_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "version", name="uq_progress_report_series_version"),
        sa.UniqueConstraint("supersedes_id"),
    )
    op.create_index("ix_progress_reports_series_id", "progress_reports", ["series_id"])
    op.create_index("ix_progress_reports_learner_id", "progress_reports", ["learner_id"])
    op.create_index(
        "ix_progress_reports_author_user_id",
        "progress_reports",
        ["author_user_id"],
    )
    op.create_index("ix_progress_reports_status", "progress_reports", ["status"])

    op.create_table(
        "report_deliveries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by_user_id", sa.String(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["progress_reports.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_deliveries_report_id", "report_deliveries", ["report_id"])
    op.create_index(
        "ix_report_deliveries_token_hash",
        "report_deliveries",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_report_deliveries_expires_at",
        "report_deliveries",
        ["expires_at"],
    )

    op.create_table(
        "report_audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("learner_id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("delivery_id", sa.String(), nullable=True),
        sa.Column("actor_user_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["progress_reports.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["report_deliveries.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_audit_events_learner_id",
        "report_audit_events",
        ["learner_id"],
    )
    op.create_index(
        "ix_report_audit_events_report_id",
        "report_audit_events",
        ["report_id"],
    )
    op.create_index(
        "ix_report_audit_events_delivery_id",
        "report_audit_events",
        ["delivery_id"],
    )
    op.create_index(
        "ix_report_audit_events_actor_user_id",
        "report_audit_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_report_audit_events_event_type",
        "report_audit_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_table("report_audit_events")
    op.drop_table("report_deliveries")
    op.drop_table("progress_reports")
    op.drop_table("learner_access_grants")
    op.drop_table("learners")

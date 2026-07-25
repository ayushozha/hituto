"""Personal learning events, insight snapshots, and privacy preferences.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=True),
        sa.Column("lesson_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("authority", sa.String(length=24), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_id", name="uq_learning_events_user_event"),
    )
    op.create_index("ix_learning_events_user_id", "learning_events", ["user_id"])
    op.create_index("ix_learning_events_event_id", "learning_events", ["event_id"])
    op.create_index("ix_learning_events_course_id", "learning_events", ["course_id"])
    op.create_index("ix_learning_events_lesson_id", "learning_events", ["lesson_id"])
    op.create_index("ix_learning_events_session_id", "learning_events", ["session_id"])
    op.create_index("ix_learning_events_event_type", "learning_events", ["event_type"])
    op.create_index("ix_learning_events_occurred_at", "learning_events", ["occurred_at"])
    op.create_index(
        "ix_learning_events_user_occurred", "learning_events", ["user_id", "occurred_at"]
    )
    op.create_index(
        "ix_learning_events_user_type_occurred",
        "learning_events",
        ["user_id", "event_type", "occurred_at"],
    )

    op.create_table(
        "insight_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("window", sa.String(length=12), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("generator", sa.String(length=24), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insight_snapshots_user_id", "insight_snapshots", ["user_id"])
    op.create_index(
        "ix_insight_snapshots_evidence_fingerprint",
        "insight_snapshots",
        ["evidence_fingerprint"],
    )
    op.create_index(
        "ix_insight_snapshots_user_created", "insight_snapshots", ["user_id", "created_at"]
    )

    op.create_table(
        "insight_preferences",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("analytics_enabled", sa.Boolean(), nullable=False),
        sa.Column("question_content_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("insight_preferences")
    op.drop_index("ix_insight_snapshots_user_created", table_name="insight_snapshots")
    op.drop_index("ix_insight_snapshots_evidence_fingerprint", table_name="insight_snapshots")
    op.drop_index("ix_insight_snapshots_user_id", table_name="insight_snapshots")
    op.drop_table("insight_snapshots")
    op.drop_index("ix_learning_events_user_type_occurred", table_name="learning_events")
    op.drop_index("ix_learning_events_user_occurred", table_name="learning_events")
    op.drop_index("ix_learning_events_occurred_at", table_name="learning_events")
    op.drop_index("ix_learning_events_event_type", table_name="learning_events")
    op.drop_index("ix_learning_events_session_id", table_name="learning_events")
    op.drop_index("ix_learning_events_lesson_id", table_name="learning_events")
    op.drop_index("ix_learning_events_course_id", table_name="learning_events")
    op.drop_index("ix_learning_events_event_id", table_name="learning_events")
    op.drop_index("ix_learning_events_user_id", table_name="learning_events")
    op.drop_table("learning_events")

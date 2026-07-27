"""Add coding_lab_sessions for tutor-driven coding practice workspace.

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("coding_lab_sessions"):
        return
    op.create_table(
        "coding_lab_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lesson_id",
            sa.String(),
            sa.ForeignKey("lessons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tool_call_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("entrypoint", sa.String(), nullable=True),
        sa.Column("expected_stdout", sa.Text(), nullable=True),
        sa.Column("workspace", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tool_call_id",
            name="uq_coding_lab_sessions_tool_call_id",
        ),
    )
    op.create_index("ix_coding_lab_sessions_course_id", "coding_lab_sessions", ["course_id"])
    op.create_index("ix_coding_lab_sessions_lesson_id", "coding_lab_sessions", ["lesson_id"])
    op.create_index("ix_coding_lab_sessions_user_id", "coding_lab_sessions", ["user_id"])
    op.create_index("ix_coding_lab_sessions_tool_call_id", "coding_lab_sessions", ["tool_call_id"])
    op.create_index("ix_coding_lab_sessions_updated_at", "coding_lab_sessions", ["updated_at"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("coding_lab_sessions"):
        return
    op.drop_index("ix_coding_lab_sessions_updated_at", table_name="coding_lab_sessions")
    op.drop_index("ix_coding_lab_sessions_tool_call_id", table_name="coding_lab_sessions")
    op.drop_index("ix_coding_lab_sessions_user_id", table_name="coding_lab_sessions")
    op.drop_index("ix_coding_lab_sessions_lesson_id", table_name="coding_lab_sessions")
    op.drop_index("ix_coding_lab_sessions_course_id", table_name="coding_lab_sessions")
    op.drop_table("coding_lab_sessions")

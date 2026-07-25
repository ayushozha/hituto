"""Add courses.tagline + whiteboard_sessions for Postgres deploy parity.

SQLite gets tagline via ``_ensure_added_columns`` and whiteboard via create_all;
Alembic never recorded either. Without tagline, startup recovery queries fail.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    course_cols = {c["name"] for c in insp.get_columns("courses")} if insp.has_table("courses") else set()
    if "tagline" not in course_cols:
        op.add_column("courses", sa.Column("tagline", sa.String(), nullable=True))

    if not insp.has_table("whiteboard_sessions"):
        op.create_table(
            "whiteboard_sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("course_id", sa.String(), nullable=False),
            sa.Column("lesson_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("tool_call_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("intent", sa.Text(), nullable=False),
            sa.Column("scene", sa.JSON(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_whiteboard_sessions_course_id"),
            "whiteboard_sessions",
            ["course_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_whiteboard_sessions_lesson_id"),
            "whiteboard_sessions",
            ["lesson_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_whiteboard_sessions_user_id"),
            "whiteboard_sessions",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_whiteboard_sessions_tool_call_id"),
            "whiteboard_sessions",
            ["tool_call_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_whiteboard_sessions_updated_at"),
            "whiteboard_sessions",
            ["updated_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("whiteboard_sessions"):
        op.drop_table("whiteboard_sessions")
    course_cols = {c["name"] for c in insp.get_columns("courses")} if insp.has_table("courses") else set()
    if "tagline" in course_cols:
        op.drop_column("courses", "tagline")

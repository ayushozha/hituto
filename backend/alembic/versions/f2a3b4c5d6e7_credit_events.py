"""credit_events ledger for course-credit metering

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=True),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credit_events_user_id", "credit_events", ["user_id"])
    op.create_index("ix_credit_events_course_id", "credit_events", ["course_id"])
    op.create_index("ix_credit_events_period", "credit_events", ["period"])


def downgrade() -> None:
    op.drop_index("ix_credit_events_period", table_name="credit_events")
    op.drop_index("ix_credit_events_course_id", table_name="credit_events")
    op.drop_index("ix_credit_events_user_id", table_name="credit_events")
    op.drop_table("credit_events")

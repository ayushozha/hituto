"""Add learner_profiles (onboarding-captured learning preferences).

SQLite gets the table via create_all in dev; this records it for Postgres deploys.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("learner_profiles"):
        op.create_table(
            "learner_profiles",
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("preferences", sa.JSON(), nullable=False),
            sa.Column("onboarded_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("user_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("learner_profiles"):
        op.drop_table("learner_profiles")

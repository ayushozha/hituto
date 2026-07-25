"""lessons.share_token for opt-in public share links

Adds a nullable, unique share token to lessons. Null = private; a non-null token
lets anyone with the link read that one lesson's artifact without auth. Postgres
deploy path; SQLite dev gets the column via create_all on a fresh DB.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lessons", sa.Column("share_token", sa.String(), nullable=True))
    op.create_index(
        "ix_lessons_share_token", "lessons", ["share_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_lessons_share_token", table_name="lessons")
    op.drop_column("lessons", "share_token")

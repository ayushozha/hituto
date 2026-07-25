"""lesson_source_packs.chapter_ids + passage_ids (rag-context)

Adds soft-reference JSON columns for teaching-map chapters and passage chunks.
Do not overload chunk_ids with chapter ids.

Drafted in rag-context Phase 0; applied / consumed by coursegen in Phase 3.
SQLite create_all on a fresh DB picks these up from the ORM model.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lesson_source_packs",
        sa.Column("chapter_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "lesson_source_packs",
        sa.Column("passage_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("lesson_source_packs", "passage_ids")
    op.drop_column("lesson_source_packs", "chapter_ids")

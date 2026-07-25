"""artifacts.kind + artifacts.a2ui for A2UI lessons (coursegen Phase 5)

Adds additive columns; existing rows default to kind='html'. SQLite create_all
picks these up from the ORM on a fresh DB.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("kind", sa.String(), nullable=False, server_default="html"),
    )
    op.add_column("artifacts", sa.Column("a2ui", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("artifacts", "a2ui")
    op.drop_column("artifacts", "kind")

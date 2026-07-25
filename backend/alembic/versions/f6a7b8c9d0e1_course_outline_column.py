"""courses.outline for the chapter-outline HITL flow (course-authoring-flow §3)

Additive nullable JSON column holding the OutlineDoc draft/approved payload.
SQLite create_all picks it up from the ORM on a fresh DB. The new course
status value `outline_review` needs no schema change (status is a String).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("outline", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "outline")

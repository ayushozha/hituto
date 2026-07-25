"""lessons.status may be awaiting_review (teacher HITL)

No DDL: `lessons.status` is an unconstrained String. Documents the additive
status value used when `require_teacher_review` is enabled (coursegen-agent §9).
SQLite create_all unchanged; Postgres deploy path records the revision for ops.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Status values are application-level; column already exists as String.
    op.execute("SELECT 1")  # no-op marker so the revision is applied


def downgrade() -> None:
    pass

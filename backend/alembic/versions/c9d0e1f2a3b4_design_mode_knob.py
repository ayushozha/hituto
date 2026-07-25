"""Rename courses.knobs.presentation → design_mode (user-facing Design mode).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def _as_dict(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if raw is None:
        return {}
    return json.loads(raw)


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, knobs FROM courses")).fetchall()
    for row_id, raw in rows:
        knobs = _as_dict(raw)
        if "design_mode" in knobs:
            knobs.pop("presentation", None)
        elif "presentation" in knobs:
            knobs["design_mode"] = knobs.pop("presentation")
        else:
            continue
        conn.execute(
            sa.text("UPDATE courses SET knobs = :knobs WHERE id = :id"),
            {"id": row_id, "knobs": json.dumps(knobs)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, knobs FROM courses")).fetchall()
    for row_id, raw in rows:
        knobs = _as_dict(raw)
        if "presentation" in knobs:
            knobs.pop("design_mode", None)
        elif "design_mode" in knobs:
            knobs["presentation"] = knobs.pop("design_mode")
        else:
            continue
        conn.execute(
            sa.text("UPDATE courses SET knobs = :knobs WHERE id = :id"),
            {"id": row_id, "knobs": json.dumps(knobs)},
        )

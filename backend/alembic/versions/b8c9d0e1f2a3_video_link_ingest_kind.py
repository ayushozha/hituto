"""Tag video sources with source_map.video.ingest_kind (link vs legacy upload).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _ingest_kind(source_map: dict) -> str | None:
    video = source_map.get("video") or {}
    if video.get("ingest_kind") in {"link", "upload"}:
        return video["ingest_kind"]
    if video.get("external_url"):
        return "link"
    if (
        video.get("media_storage_key")
        or video.get("media_stored_path")
        or source_map.get("storage_key")
        or source_map.get("stored_path")
    ):
        return "upload"
    return None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, source_map FROM source_documents WHERE source_type = 'video'"
        )
    ).fetchall()
    for row_id, raw_map in rows:
        source_map = raw_map if isinstance(raw_map, dict) else json.loads(raw_map or "{}")
        video = dict(source_map.get("video") or {})
        ingest_kind = _ingest_kind(source_map)
        if not ingest_kind or video.get("ingest_kind") == ingest_kind:
            continue
        video["ingest_kind"] = ingest_kind
        source_map["video"] = video
        conn.execute(
            sa.text("UPDATE source_documents SET source_map = :source_map WHERE id = :id"),
            {"id": row_id, "source_map": json.dumps(source_map)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, source_map FROM source_documents WHERE source_type = 'video'"
        )
    ).fetchall()
    for row_id, raw_map in rows:
        source_map = raw_map if isinstance(raw_map, dict) else json.loads(raw_map or "{}")
        video = dict(source_map.get("video") or {})
        if "ingest_kind" not in video:
            continue
        video.pop("ingest_kind", None)
        source_map["video"] = video
        conn.execute(
            sa.text("UPDATE source_documents SET source_map = :source_map WHERE id = :id"),
            {"id": row_id, "source_map": json.dumps(source_map)},
        )

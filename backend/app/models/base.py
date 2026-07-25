"""Shared model helpers + the declarative Base (defined in core.db).

`EMBED_DIM` is read once at import so the pgvector column width is fixed per process.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..core.config import get_settings
from ..core.db import Base  # re-exported via app.models

EMBED_DIM = get_settings().embedding_dim

__all__ = ["Base", "EMBED_DIM", "_uuid", "_now"]


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)

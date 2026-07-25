"""Database engine + session (SQLite for the vertical slice; Postgres-ready).

The spec targets Postgres for prod; SQLAlchemy keeps the swap a URL change.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_database_url, get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_db_url = get_database_url()
_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from .. import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(engine)
    _ensure_added_columns()


def _ensure_added_columns() -> None:
    """Additive nullable columns for schemas create_all will not ALTER.

    SQLite (dev) and Postgres (Render) both need this when Alembic lags the ORM.
    Prefer a real Alembic revision for production; this is a fail-open safety net.
    """
    is_sqlite = settings.database_url.startswith("sqlite")
    adds = {
        # Chapter-outline HITL (alembic f6a7b8c9d0e1 / d0e1f2a3b4c5)
        "courses": [
            ("outline", "JSON"),
            ("tagline", "VARCHAR"),
        ],
        "lessons": [
            ("module_ordinal", "INTEGER"),
            ("module_title", "VARCHAR"),
            ("share_token", "VARCHAR"),
        ],
        # A2UI lessons (alembic e5f6a7b8c9d0)
        "artifacts": [
            ("kind", "VARCHAR NOT NULL DEFAULT 'html'"),
            ("a2ui", "JSON"),
        ],
        # Teaching-map packs (alembic c3d4e5f6a7b8)
        "lesson_source_packs": [
            ("chapter_ids", "JSON NOT NULL DEFAULT '[]'"),
            ("passage_ids", "JSON NOT NULL DEFAULT '[]'"),
        ],
        # Billing ledger (alembic f2a3b4c5d6e7)
        "credit_events": [
            ("units", "INTEGER NOT NULL DEFAULT 1"),
        ],
    }
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            for table, cols in adds.items():
                if is_sqlite:
                    existing = {
                        row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
                    }
                else:
                    existing = {
                        row[0]
                        for row in conn.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema = current_schema() AND table_name = :t"
                            ),
                            {"t": table},
                        )
                    }
                if not existing:
                    continue  # table absent; create_all built it fresh with all columns
                for name, decl in cols:
                    if name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))
    except Exception as exc:
        logger.warning("Additive column migration failed (continuing with existing schema): %s", exc)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

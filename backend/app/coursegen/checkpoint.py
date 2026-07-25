"""Durable LangGraph checkpointer for teacher-review HITL (coursegen-agent Phase 4).

Dev/default: SQLite via `langgraph-checkpoint-sqlite`. Recreated when the running
event loop changes so `asyncio.run(...)` in tests (and short-lived loops) never
reuse a saver bound to a closed loop.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..core.config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: Any = None
_cm: Any = None  # async context manager holding the open saver
_loop_id: int | None = None


def checkpoint_sqlite_path() -> str:
    """Path for the SQLite checkpoint DB (or `:memory:` when tests force it)."""
    settings = get_settings()
    override = (getattr(settings, "langgraph_checkpoint_path", None) or "").strip()
    if override:
        return override
    # Prefer a sibling of the SQLite app DB when using sqlite:///./hituto.db
    url = (settings.database_url or "").strip()
    if url.startswith("sqlite:///"):
        db_path = url.removeprefix("sqlite:///")
        if db_path in {":memory:", ""}:
            return ":memory:"
        p = Path(db_path).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return str(p.with_name(p.stem + ".langgraph.db"))
    # Postgres app DB — still use a local sqlite file for checkpoints unless overridden
    return str(Path.cwd() / "hituto.langgraph.db")


async def get_checkpointer():
    """Return an AsyncSqliteSaver for the current event loop (created once per loop)."""
    global _checkpointer, _cm, _loop_id
    loop = asyncio.get_running_loop()
    lid = id(loop)
    if _checkpointer is not None and _loop_id == lid:
        return _checkpointer

    # Previous loop closed — drop the old saver without awaiting its aexit (loop is gone).
    _checkpointer = None
    _cm = None
    _loop_id = lid

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path = checkpoint_sqlite_path()
    _cm = AsyncSqliteSaver.from_conn_string(path)
    _checkpointer = await _cm.__aenter__()
    await _checkpointer.setup()
    logger.info("LangGraph checkpointer ready (%s)", path)
    return _checkpointer


async def close_checkpointer() -> None:
    """Release the checkpointer (tests / shutdown)."""
    global _checkpointer, _cm, _loop_id
    if _cm is not None:
        try:
            await _cm.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
    _checkpointer = None
    _cm = None
    _loop_id = None


def reset_checkpointer_for_tests() -> None:
    """Drop cached checkpointer without awaiting (test fixture helper)."""
    global _checkpointer, _cm, _loop_id
    _checkpointer = None
    _cm = None
    _loop_id = None


def generation_thread_id(lesson_id: str) -> str:
    """Stable thread id for a lesson generation run (HITL resume key)."""
    return f"lesson-gen:{lesson_id}"

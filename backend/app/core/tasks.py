"""Fire-and-forget background tasks that don't vanish mid-flight.

`asyncio.create_task` only creates a *weak* reference from the event loop, so a task
whose result nobody stores can be garbage-collected before it finishes — silently
stopping long-running background work (e.g. document ingestion stuck at "chunking"
forever). `spawn` keeps a strong reference until the task completes, then drops it.

See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

_log = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine, *, name: str | None = None) -> asyncio.Task:
    """Schedule `coro` on the running loop and hold a strong reference until it's done."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and (exc := t.exception()) is not None:
            _log.error("background task %s failed: %r", t.get_name(), exc)

    task.add_done_callback(_done)
    return task

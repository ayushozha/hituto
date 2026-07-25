"""In-memory progress pub/sub for SSE (design.md §8).

For the slice this is a process-local broker. Prod would back this with Redis
pub/sub so it survives multiple workers; the interface stays the same.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class ProgressEvent:
    stage: str
    detail: str = ""
    pct: int = 0
    # Optional structured payload for rich frames (skeleton, gen_fragment, …).
    # Serialized as-is over SSE; plain-progress consumers ignore it.
    data: dict | None = None


# Transient stream frames: high-frequency deltas that are useless without the
# frames before them, so they must never be replayed to late subscribers.
_TRANSIENT_STAGES = {"gen_fragment", "a2ui_section"}


class ProgressBroker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        # last event per course so late subscribers get current state (R3.4)
        self._last: dict[str, ProgressEvent] = {}

    async def publish(self, course_id: str, event: ProgressEvent) -> None:
        if event.stage not in _TRANSIENT_STAGES:
            self._last[course_id] = event
        for q in list(self._subs.get(course_id, ())):
            await q.put(event)

    def subscribe(self, course_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[course_id].add(q)
        if course_id in self._last:
            q.put_nowait(self._last[course_id])
        return q

    def unsubscribe(self, course_id: str, q: asyncio.Queue) -> None:
        self._subs.get(course_id, set()).discard(q)


broker = ProgressBroker()

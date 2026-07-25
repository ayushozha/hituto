"""Design-agent contract (specs/design_agents §4).

One agent per design family, all implementing the same small contract, selected by the
registry in ``designs/__init__``. The LangGraph pipeline stays generic scaffolding
(assets, streaming, repair loop, persist); a design agent owns *authoring only*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol


@dataclass
class AuthorContext:
    """Everything an agent may use to author one attempt. Read-only by convention."""

    course_id: str
    lesson_id: str
    attempt: int
    plan: dict
    knobs: dict
    # GenState view — previous_html/target_*/html/checks/grounding_repair for repairs.
    state: dict
    llm: Any
    # streamer_factory(section_id|None) -> fragment streamer or None (streaming off).
    streamer_factory: Callable[[str | None], Any] | None = None
    # emit(stage, detail, pct) — progress frames pre-scoped to the course channel.
    emit: Callable[[str, str, int], Awaitable[None]] | None = None

    async def progress(self, stage: str, detail: str, pct: int) -> None:
        if self.emit is not None:
            await self.emit(stage, detail, pct)


@dataclass
class DesignOutput:
    """What an authoring attempt produced; the pipeline turns this into GenState."""

    kind: Literal["html", "a2ui", "reading"] = "html"
    html: str = ""
    a2ui: dict | None = None
    # The (possibly updated) plan — studio stamps its manifest, page may merge assets.
    plan: dict = field(default_factory=dict)


class DesignAgent(Protocol):
    mode: str

    async def author(self, ctx: AuthorContext) -> DesignOutput: ...

"""Deep Agents orchestrator (coursegen-agent).

Public entry for lesson generation. Syllabus planning lives in
`syllabus_planner.py` — call `plan_sourced_syllabus` / `plan_free_topic_syllabus`.

When `DEEP_AGENTS_ENABLED` is off, or Deep Agents fails to import/run, lesson
generation falls back to the deterministic LangGraph pipeline (`graph.py`).
"""
from __future__ import annotations

import logging

from ...core.config import get_settings

logger = logging.getLogger(__name__)


def deep_agents_enabled() -> bool:
    """True when the Deep Agents path may be attempted (still falls back on failure)."""
    return bool(get_settings().deep_agents_enabled)


async def run_generation_via_orchestrator(
    course_id: str,
    lesson_id: str,
    topic: str,
    knobs: dict,
    refinement: str | None = None,
    target_id: str | None = None,
    target_html: str | None = None,
) -> None:
    """Lesson generation entry used by `coursegen.run`.

    Delegates to LangGraph until full Deep Agents lesson orchestration lands.
    Any unexpected failure is handled inside `graph.run_generation` (marks lesson failed).
    """
    if deep_agents_enabled():
        try:
            used = await _try_deep_agent_generation(
                course_id,
                lesson_id,
                topic,
                knobs,
                refinement=refinement,
                target_id=target_id,
                target_html=target_html,
            )
            if used:
                return
        except Exception as exc:  # noqa: BLE001 — never block deterministic path
            logger.warning(
                "Deep Agents lesson path unavailable (%s); falling back to LangGraph", exc
            )

    from .. import graph as graph_mod

    await graph_mod.run_generation(
        course_id,
        lesson_id,
        topic,
        knobs,
        refinement=refinement,
        target_id=target_id,
        target_html=target_html,
    )


async def _try_deep_agent_generation(
    course_id: str,
    lesson_id: str,
    topic: str,
    knobs: dict,
    refinement: str | None = None,
    target_id: str | None = None,
    target_html: str | None = None,
) -> bool:
    """Return True if a Deep Agents lesson run completed; False to use LangGraph.

    Proof slice: refinements / targeted in-iframe edits always defer to the graph pipeline,
    which owns the refine + edit-mode flows. Fresh generations are attempted by the Deep Agent,
    which itself returns False (→ graph fallback) for unsupported archetypes or any failure.
    """
    if refinement or target_id or target_html:
        return False
    from .lesson_agent import run_lesson_deep_agent

    return await run_lesson_deep_agent(course_id, lesson_id, topic, knobs)

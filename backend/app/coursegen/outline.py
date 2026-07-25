"""Chapter-outline building, revision, and grounding validation (course-authoring-flow §3).

Pure coursegen logic — persistence and status transitions live in
`services/outline_service.py`. The revision loop is app-level and stateless:
each revise call is a fresh, bounded LLM invocation fed the current outline +
feedback history, so restarts can never strand a course mid-loop.
"""
from __future__ import annotations

import json
import logging
import re

from ..core.config import get_settings
from ..schemas.outline import OutlineDoc

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _clean(content: str) -> str:
    content = _THINK.sub("", content or "").strip()
    return _FENCE.sub("", content).strip()


# --- plan → OutlineDoc ------------------------------------------------------


def plan_to_outline(plan: dict, *, design: str) -> dict:
    """Convert a syllabus plan (sourced or free-topic) into an OutlineDoc dict.

    Sourced plans carry chapters; free-topic plans are flat, so each lesson
    becomes its own outline chapter (the outline items the teacher edits ARE
    the course roadmap either way).
    """
    chapters: list[dict] = []
    if plan.get("chapters"):
        for i, ch in enumerate(plan["chapters"]):
            lessons = [_outline_lesson(les) for les in ch.get("lessons") or []]
            source_ids = sorted({cid for les in lessons for cid in les["chapter_ids"]})
            chapters.append(
                {
                    "id": f"ch-{i + 1}",
                    "title": ch.get("title") or f"Chapter {i + 1}",
                    "description": ch.get("summary") or _chapter_description(lessons),
                    "source_chapter_ids": source_ids,
                    "lessons": lessons,
                }
            )
    else:
        for i, les in enumerate(plan.get("lessons") or []):
            lesson = _outline_lesson(les)
            chapters.append(
                {
                    "id": f"ch-{i + 1}",
                    "title": lesson["title"],
                    "description": lesson["objective"],
                    "source_chapter_ids": list(lesson["chapter_ids"]),
                    "lessons": [lesson],
                }
            )
    doc = OutlineDoc.model_validate(
        {
            "design": design,
            "title": plan.get("title") or "Course",
            "subtitle": plan.get("subtitle") or "",
            "chapters": chapters,
        }
    )
    return doc.model_dump()


def _outline_lesson(les: dict) -> dict:
    return {
        "title": les.get("title") or "Lesson",
        "objective": les.get("objective") or "",
        "archetype": les.get("archetype") or "explainer",
        "estimated_duration": les.get("estimated_duration") or "5m",
        "chapter_ids": [str(c) for c in (les.get("chapter_ids") or []) if c],
    }


def _chapter_description(lessons: list[dict]) -> str:
    return (lessons[0]["objective"] if lessons else "")[:400]


# --- grounding --------------------------------------------------------------


def validate_outline_grounding(outline: dict, teaching_map: dict | None) -> list[str]:
    """Grounded outlines may never reference chapters outside the teaching map."""
    if not teaching_map:
        return []
    valid = {str(c.get("id")) for c in teaching_map.get("chapters") or [] if c.get("id")}
    errors: list[str] = []
    for ch in outline.get("chapters") or []:
        for cid in ch.get("source_chapter_ids") or []:
            if str(cid) not in valid:
                errors.append(f"chapter '{ch.get('title')}' references unknown source chapter {cid}")
        for les in ch.get("lessons") or []:
            for cid in les.get("chapter_ids") or []:
                if str(cid) not in valid:
                    errors.append(
                        f"lesson '{les.get('title')}' references unknown source chapter {cid}"
                    )
    return errors


# --- revision (LLM) ---------------------------------------------------------

_REVISE_SYSTEM = (
    "You revise a course chapter outline based on teacher feedback. Keep the same JSON shape. "
    "Rules: keep chapter `id` values stable for chapters you keep (new chapters get new ids); "
    "one focused mechanism per lesson; respect the design type; never invent source chapter ids. "
    "Output ONLY the revised outline JSON — no prose, no markdown fences."
)


async def revise_outline(
    outline: dict,
    feedback: str,
    *,
    topic: str,
    teaching_map: dict | None = None,
) -> dict:
    """One bounded revision round: current outline + feedback → revised OutlineDoc dict.

    Tries the syllabus Deep Agent when enabled; always falls back to a direct
    LLM call, so the loop works (and is testable) without deepagents. Raises
    ValueError when the revision is unparseable or breaks grounding.
    """
    current = OutlineDoc.model_validate(outline)
    grounding = ""
    if teaching_map:
        valid_ids = [str(c.get("id")) for c in teaching_map.get("chapters") or [] if c.get("id")]
        grounding = (
            "\nGROUNDING: this course is document-grounded. `source_chapter_ids` and lesson "
            f"`chapter_ids` MUST be a subset of: {json.dumps(valid_ids)}. Re-title, merge, or "
            "re-scope chapters freely, but never invent new source chapters."
        )
    history = ""
    if current.feedback_log:
        history = "\nEarlier feedback already applied:\n- " + "\n- ".join(current.feedback_log[-5:])
    user = (
        f"Topic: {topic}\nDesign: {current.design}\n"
        f"CURRENT OUTLINE JSON:\n{json.dumps(current.model_dump(exclude={'feedback_log'}))[:12000]}\n"
        f"{history}{grounding}\n\nTEACHER FEEDBACK to apply now:\n{feedback}\n\n"
        "Return the full revised outline JSON (same shape, all chapters included)."
    )

    raw = await _revise_via_agent(user) or await _revise_via_llm(user)
    data = json.loads(_clean(raw))
    data["design"] = current.design  # design is teacher-picked, never model-changed
    data["status"] = "outline_review"
    data["revision"] = current.revision + 1
    data["feedback_log"] = [*current.feedback_log, feedback]
    revised = OutlineDoc.model_validate(data)
    errors = validate_outline_grounding(revised.model_dump(), teaching_map)
    if errors:
        raise ValueError("; ".join(errors))
    return revised.model_dump()


async def _revise_via_agent(user: str) -> str | None:
    """Flag-gated Deep Agent revision (same agent as syllabus planning); None on any failure."""
    if not get_settings().deep_agents_enabled:
        return None
    try:
        from .agents.syllabus_planner import build_syllabus_agent

        agent = build_syllabus_agent()
        res = await agent.ainvoke(
            {"messages": [{"role": "user", "content": f"{_REVISE_SYSTEM}\n\n{user}"}]},
            {"recursion_limit": 30},
        )
        return res["messages"][-1].content
    except Exception as exc:  # noqa: BLE001 — always fall back to the direct call
        logger.warning("outline revision Deep Agent path failed: %s", exc)
        return None


async def _revise_via_llm(user: str) -> str:
    from ..providers.registry import get_coursegen_llm

    return await get_coursegen_llm().generate_html(_REVISE_SYSTEM, user)

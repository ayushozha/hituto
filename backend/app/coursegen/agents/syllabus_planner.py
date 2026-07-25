"""Syllabus planner agent (coursegen-agent Phase 3).

Replaces direct `expert_panel` / ad-hoc `source_planner` calls for course
planning. Deep Agents path is flag-gated; failures always fall back to:

- sourced → deterministic teaching map (`plan_source_course`)
- free-topic → `planner.build_syllabus`
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...core.config import get_settings
from ..source_planner import plan_source_course

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agents" / "syllabus_planner.md"


def _load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "You are the Hi Tuto syllabus planner. Design prerequisite-ordered "
            "concept-capsule lessons. Output ONLY valid JSON."
        )


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:48] or "concept")


def _clean(content: str) -> str:
    content = _THINK.sub("", content or "").strip()
    return _FENCE.sub("", content).strip()


def deep_agents_enabled() -> bool:
    return bool(get_settings().deep_agents_enabled)


# --- Deep Agents output schemas -------------------------------------------------


class _Lesson(BaseModel):
    title: str
    objective: str
    concept: str = ""
    archetype: str = "explainer"
    chapter_ids: list[str] = Field(default_factory=list)
    estimated_duration: str = "5m"


class _Chapter(BaseModel):
    title: str
    lessons: list[_Lesson]


class _SourcedPlan(BaseModel):
    title: str
    chapters: list[_Chapter]


class _FreePlan(BaseModel):
    title: str
    subtitle: str = ""
    lessons: list[_Lesson]


def rag_outline(source_map: dict) -> dict[str, Any]:
    """Tool-shaped view of the teaching map for syllabus planning (design §8)."""
    tm = (source_map or {}).get("teaching_map") or {}
    outline = (source_map or {}).get("document_outline") or {}
    chapters = []
    for ch in tm.get("chapters") or []:
        chapters.append(
            {
                "id": ch.get("id"),
                "title": ch.get("title"),
                "summary": (ch.get("summary") or "")[:400],
                "source_node_ids": list(ch.get("source_node_ids") or []),
                "order": ch.get("order"),
            }
        )
    return {
        "document_summary": tm.get("document_summary") or "",
        "thesis": tm.get("thesis"),
        "chapters": chapters,
        "outline_node_count": len((outline.get("nodes") or [])),
        "sections": list((source_map or {}).get("sections") or [])[:40],
    }


def _chat_model(*, heavy: bool = False):
    from .llm import chat_model

    return chat_model(heavy=heavy)


def _skill_dirs(coursegen_dir: Path, topic: str) -> list[str]:
    """Skill sources (virtual `/skills/…` paths) for the syllabus agent: core + subject."""
    from .registry import resolve_specialist

    dirs = ["/skills/core"]
    spec = resolve_specialist(topic)
    if spec and spec.subjects:
        subj = spec.subjects[0]
        if (coursegen_dir / "skills" / "subjects" / subj).is_dir():
            dirs.append(f"/skills/subjects/{subj}")
    return dirs


def _specialist_subagent(topic: str) -> dict | None:
    """Optional subject specialist from the registry (maths / science)."""
    from .registry import resolve_specialist

    spec = resolve_specialist(topic)
    if spec is None:
        return None
    return {
        "name": spec.name.replace("-", "_"),
        "description": spec.description,
        "system_prompt": (
            f"You are the {spec.name} for syllabus design. Keep lessons focused on "
            f"one mechanism each; respect grounding when a source document is present."
        ),
    }


def build_syllabus_agent(*, topic: str = ""):
    """Deep Agent for syllabus planning (lazy-imports deepagents).

    Loads the `core` pedagogy/grounding skills (+ the routed subject skill) via the
    hardened web backend: `/skills/…` is a read-only mount over coursegen/skills;
    scratch writes stay in the ephemeral StateBackend (never the repo).
    """
    from deepagents import create_deep_agent

    from .backends import web_backend

    subagents = [
        {
            "name": "curriculum_designer",
            "description": "Turn outline/topic analysis into prerequisite-ordered capsules.",
            "system_prompt": (
                "Design Brilliant-style courses: one mechanism per lesson, prerequisite "
                "order, grouped into chapters. Never produce broad overview dumps."
            ),
        },
    ]
    specialist = _specialist_subagent(topic)
    if specialist:
        subagents.append(specialist)

    from .llm import assign_subagent_models, chat_model

    assign_subagent_models(subagents)
    coursegen_dir = Path(__file__).resolve().parents[1]
    return create_deep_agent(
        model=chat_model(heavy=True),  # syllabus orchestrator: thinking / planning
        subagents=subagents,
        system_prompt=_load_system_prompt(),
        backend=web_backend(),
        skills=_skill_dirs(coursegen_dir, topic),
    )


def _sourced_plan_from_agent(raw: _SourcedPlan, *, title: str, mode: str, difficulty: str) -> dict:
    chapters: list[dict] = []
    lesson_scopes: dict[str, dict] = {}
    ordinal = 0
    for ch in raw.chapters:
        lessons = []
        for lesson in ch.lessons:
            cid_list = [str(x) for x in (lesson.chapter_ids or []) if x]
            concept = lesson.concept or lesson.title
            lessons.append(
                {
                    "concept_id": _slug(lesson.title),
                    "title": lesson.title,
                    "objective": lesson.objective,
                    "archetype": lesson.archetype or "explainer",
                    "source_query": concept,
                    "chapter_ids": cid_list,
                }
            )
            if cid_list:
                lesson_scopes[str(ordinal)] = {
                    "chapter_ids": cid_list,
                    "covers": (lesson.objective or "")[:240],
                    "avoid": "",
                }
            ordinal += 1
        if lessons:
            chapters.append({"title": ch.title, "lessons": lessons})
    if not chapters:
        raise ValueError("syllabus planner produced no lessons")
    out: dict[str, Any] = {
        "title": raw.title or title,
        "mode": mode,
        "difficulty": difficulty,
        "chapters": chapters,
        "planner": "syllabus_planner",
    }
    if lesson_scopes:
        out["lesson_scopes"] = lesson_scopes
    return out


async def _try_deep_sourced_plan(
    *,
    title: str,
    source_map: dict,
    excerpt: str,
    difficulty: str,
    lesson_count: int,
    mode: str,
) -> dict | None:
    if not deep_agents_enabled():
        return None
    try:
        outline = rag_outline(source_map)
        agent = build_syllabus_agent(topic=title)
        prompt = (
            f"SOURCE TITLE: {title}\n"
            f"RAG_OUTLINE (teaching chapters):\n{json.dumps(outline, indent=2)[:8000]}\n\n"
            f"SOURCE EXCERPT:\n{(excerpt or '')[:4000]}\n\n"
            f"Design a {difficulty} course of AT MOST {lesson_count} focused concept-capsule "
            "lessons, grouped into chapters. Prefer 1:1 teaching-chapter → lesson; every "
            "lesson that is grounded MUST include chapter_ids from RAG_OUTLINE.chapters[].id. "
            "Output ONLY JSON matching:\n"
            '{"title": str, "chapters": [{"title": str, "lessons": [{"title": str, '
            '"objective": str, "concept": str, "archetype": '
            '"explainer|simulation|game|tool|narrative", "chapter_ids": [str]}]}]}'
        )
        res = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            {"recursion_limit": 30},
        )
        parsed = _SourcedPlan.model_validate_json(_clean(res["messages"][-1].content))
        return _sourced_plan_from_agent(parsed, title=title, mode=mode, difficulty=difficulty)
    except Exception as exc:  # noqa: BLE001 — always fall back
        logger.warning("syllabus planner Deep Agents sourced path failed: %s", exc)
        return None


async def _try_deep_free_plan(topic: str, knobs: dict) -> dict | None:
    if not deep_agents_enabled():
        return None
    try:
        from ..studio_catalog import is_studio_knobs

        difficulty = knobs.get("difficulty", "intermediate")
        agent = build_syllabus_agent(topic=topic)
        from ...services.profile_service import summary_line

        learner = summary_line(knobs.get("learner_profile") or {})
        learner_prompt = f"{learner} Shape lesson ordering and sizing accordingly.\n" if learner else ""
        if is_studio_knobs(knobs):
            prompt = (
                f"Topic: {topic}\nDifficulty: {difficulty}\n"
                f"Archetype preference: {knobs.get('archetype') or 'auto'}\n"
                f"{learner_prompt}\n"
                "Design EXACTLY 1 studio chapter (single-page Canvas Studio). "
                "Subjects/parts live inside that chapter — do NOT create multiple lessons.\n"
                "Output ONLY JSON matching:\n"
                '{"title": str, "subtitle": str, "lessons": [{"title": str, "objective": str, '
                '"archetype": "explainer|game|simulation|tool|narrative", '
                '"estimated_duration": "10m"}]}'
            )
        else:
            prompt = (
                f"Topic: {topic}\nDifficulty: {difficulty}\n"
                f"Archetype preference: {knobs.get('archetype') or 'auto'}\n"
                f"{learner_prompt}\n"
                "Design 3–6 lessons. Output ONLY JSON matching:\n"
                '{"title": str, "subtitle": str, "lessons": [{"title": str, "objective": str, '
                '"archetype": "explainer|game|simulation|tool|narrative", '
                '"estimated_duration": "5m"}]}'
            )
        res = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            {"recursion_limit": 30},
        )
        parsed = _FreePlan.model_validate_json(_clean(res["messages"][-1].content))
        lessons = [
            {
                "title": les.title,
                "objective": les.objective,
                "archetype": les.archetype or "explainer",
                "estimated_duration": les.estimated_duration or "5m",
            }
            for les in parsed.lessons
        ]
        if not lessons:
            raise ValueError("no lessons")
        return {
            "title": parsed.title or topic,
            "subtitle": parsed.subtitle
            or f"An interactive {difficulty}-level guide to {parsed.title or topic}.",
            "lessons": lessons,
            "planner": "syllabus_planner",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("syllabus planner Deep Agents free-topic path failed: %s", exc)
        return None


async def plan_sourced_syllabus(
    source_map: dict,
    *,
    title: str,
    excerpt: str = "",
    difficulty: str = "intermediate",
    lesson_count: int = 6,
    mode: str = "paper_walkthrough",
    use_teaching_map: bool | None = None,
    selected_outline_nodes: list[str] | None = None,
) -> dict:
    """Plan a document-grounded course.

    When a teaching map is active, use the deterministic map (structural grounding).
    Otherwise optionally try Deep Agents, then fall back to `plan_source_course`.
    """
    settings = get_settings()
    has_tm = bool((source_map or {}).get("teaching_map", {}).get("chapters"))
    prefer_tm = use_teaching_map if use_teaching_map is not None else (
        bool(settings.rag_teaching_map_planner and has_tm)
    )

    # Teaching-map path: never invent topics via Deep Agents (would bypass grounding).
    if prefer_tm and has_tm:
        return plan_source_course(
            source_map,
            title=title,
            difficulty=difficulty,
            lesson_count=lesson_count,
            mode=mode,
            use_teaching_map=True,
            selected_outline_nodes=selected_outline_nodes,
        )

    deep = await _try_deep_sourced_plan(
        title=title,
        source_map=source_map,
        excerpt=excerpt,
        difficulty=difficulty,
        lesson_count=lesson_count,
        mode=mode,
    )
    if deep is not None:
        return deep

    return plan_source_course(
        source_map,
        title=title,
        difficulty=difficulty,
        lesson_count=lesson_count,
        mode=mode,
        use_teaching_map=prefer_tm,
        selected_outline_nodes=selected_outline_nodes,
    )


async def plan_free_topic_syllabus(topic: str, knobs: dict) -> dict:
    """Plan a free-topic (non-sourced) syllabus for `run_syllabus_planning`."""
    from ..studio_catalog import is_studio_knobs, shape_studio_syllabus

    deep = await _try_deep_free_plan(topic, knobs)
    if deep is not None:
        plan = deep
    else:
        from ..planner import build_syllabus

        plan = await build_syllabus(topic, knobs)
        plan.setdefault("planner", "build_syllabus")
    if is_studio_knobs(knobs):
        plan = shape_studio_syllabus(plan, topic)
        plan["planner"] = (plan.get("planner") or "syllabus") + "+studio"
    return plan

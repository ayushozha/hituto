"""Deep Agent lesson orchestration (coursegen-agent §3).

Proof slice: a `create_deep_agent` orchestrator delegates (via `task`) to researcher →
capsule_author → qa_reviewer; the capsule_author writes /build/capsule.html; the result is
gated by `capsule.postprocess` and persisted via `graph.persist_artifact`. ANY failure returns
False so the caller (`orchestrator`) falls back to the deterministic LangGraph pipeline.

Scratch files live in the default StateBackend (ephemeral, thread-scoped) — no FilesystemBackend
in the web process. Skills / compute / mesh / document-grounding are layered in later slices;
those lessons defer to the graph pipeline for now.
"""
from __future__ import annotations

import logging

from ...core.db import SessionLocal
from ...models import Course, Lesson

logger = logging.getLogger(__name__)

_CAPSULE_PATH = "/build/capsule.html"
_COMPUTE_MANIFEST_PATH = "/build/compute/manifest.json"
_MESH_MANIFEST_PATH = "/build/mesh/manifest.json"
_MAX_RECURSION = 48
# Web/ungrounded lessons the Deep Agent path handles; studio / document-grounded defer to the graph.
_SUPPORTED_ARCHETYPES = ("explainer", "narrative", "simulation", "game", "tool")
# Archetypes that also get the compute subagents (data-synthesizer + viz-engineer).
_COMPUTE_ARCHETYPES = ("simulation", "game", "tool")


def build_lesson_agent(
    *,
    subject: str | None = None,
    archetype: str = "explainer",
    design: str = "page",
    specialist=None,
):
    """Construct the lesson Deep Agent (orchestrator + role subagents).

    Roster depends on the lesson: studio designs get the mesh_viz subagent; compute archetypes
    get data-synthesizer + viz-engineer; explainer/narrative page lessons get neither. The
    resolved `design` (page | studio | slide) selects the shell skill injected into the capsule
    author. A routed subject `specialist` (maths/science) is added as a domain-review consultant
    when one matches.
    """
    from deepagents import create_deep_agent

    from .llm import assign_subagent_models, chat_model
    from .prompt_loader import load_agent_prompt
    from .roles.capsule_author import capsule_author_subagent
    from .roles.qa_reviewer import qa_reviewer_subagent
    from .roles.researcher import researcher_subagent
    from .tools import emit_progress

    studio = design == "studio"
    compute = (archetype or "").lower() in _COMPUTE_ARCHETYPES
    subagents = [researcher_subagent(subject)]
    if studio:
        from .roles.mesh_viz import mesh_viz_subagent

        subagents.append(mesh_viz_subagent(subject))
    elif compute:
        from .roles.data_synthesizer import data_synthesizer_subagent
        from .roles.viz_engineer import viz_engineer_subagent

        subagents += [data_synthesizer_subagent(subject), viz_engineer_subagent(subject)]
    if studio or compute:
        # Bespoke motion pays off where the lesson is the interaction (course-authoring-flow §5).
        from .roles.animation_coder import animation_coder_subagent

        subagents.append(animation_coder_subagent(subject))
    if specialist is not None:
        from .specialists import specialist_subagent

        subagents.append(specialist_subagent(specialist))
    from .roles.image_artist import image_artist_subagent

    subagents += [
        image_artist_subagent(subject),
        capsule_author_subagent(subject, design=design),
        qa_reviewer_subagent(subject),
    ]
    assign_subagent_models(subagents)

    return create_deep_agent(
        model=chat_model(heavy=True),  # orchestrator: thinking / planning
        system_prompt=load_agent_prompt("orchestrator"),
        tools=[emit_progress],
        subagents=subagents,
    )


def _read_scratch_json(files: dict, path: str) -> dict | None:
    """Parse an optional JSON file a subagent wrote to scratch (best-effort)."""
    import json

    raw = (files.get(path) or {}).get("content")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


async def run_lesson_deep_agent(course_id: str, lesson_id: str, topic: str, knobs: dict) -> bool:
    """Generate one lesson via the Deep Agent. True only on a persisted, passing capsule."""
    try:
        from ...capsule.postprocess import postprocess
        from ..graph import persist_artifact
        from ..planner import build_lesson_plan
        from .registry import resolve_specialist

        with SessionLocal() as db:
            course = db.get(Course, course_id)
            lesson = db.get(Lesson, lesson_id)
            if course is None or lesson is None:
                return False
            archetype = (lesson.archetype or "explainer").lower()
            knobs_db = course.knobs or {}
            from ..presentation import knobs_design_mode

            presentation = knobs_design_mode(knobs_db)
            # Defer compute/mesh/studio + document-grounded lessons to the graph pipeline.
            if archetype not in _SUPPORTED_ARCHETYPES:
                return False
            if knobs_db.get("source_document_id"):
                return False  # document-grounded → graph (rag retrieval)
            if knobs_db.get("require_teacher_review"):
                return False  # teacher-HITL lessons use the graph's durable interrupt (Phase 5b)
            from ..presentation import resolve_presentation

            if resolve_presentation(
                {"title": lesson.title, "topic": course.topic, "presentation": presentation},
                knobs_db,
            ) == "studio":
                return False  # Studio v2 uses the graph's validated manifest + owned renderer.
            course_title = course.title or course.topic
            lesson_title = lesson.title
            objective = lesson.objective
            difficulty = knobs_db.get("difficulty", "intermediate")
            style_theme = knobs_db.get("style_theme")

        plan = await build_lesson_plan(
            course_title=course_title,
            lesson_title=lesson_title,
            objective=objective,
            archetype=archetype,
            difficulty=difficulty,
            style_theme=style_theme,
            presentation=presentation,
        )

        with SessionLocal() as db:
            lesson = db.get(Lesson, lesson_id)
            if lesson is not None:
                lesson.status = "generating"
                db.commit()

        subject = None
        spec = resolve_specialist(topic or course_title)
        if spec and spec.subjects:
            subject = spec.subjects[0]

        from ..presentation import resolve_presentation

        design = resolve_presentation(
            {"title": lesson_title, "topic": course_title, "presentation": presentation},
            knobs_db,
        )
        agent = build_lesson_agent(
            subject=subject, archetype=archetype, design=design, specialist=spec
        )
        result = await agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": _brief(course_id, plan, topic or course_title, design)}
                ]
            },
            {"recursion_limit": _MAX_RECURSION},
        )

        files = result.get("files") or {}
        html = (files.get(_CAPSULE_PATH) or {}).get("content") or ""
        if not html.strip():
            logger.info("Deep Agent authored no capsule for %s; deferring to graph", lesson_id)
            return False

        clean_html, checks = postprocess(html)
        if not checks.get("passed"):
            logger.info(
                "Deep Agent capsule failed checks %s for %s; deferring to graph",
                checks.get("failed"),
                lesson_id,
            )
            return False

        mesh_manifest = _read_scratch_json(files, _MESH_MANIFEST_PATH) or {}
        status = await persist_artifact(
            course_id=course_id,
            lesson_id=lesson_id,
            plan=plan,
            checks=checks,
            html=clean_html,
            kind="html",
            compute_artifact=_read_scratch_json(files, _COMPUTE_MANIFEST_PATH),  # best-effort
            mesh_artifact=mesh_manifest.get("mesh_artifact"),  # /mesh?key= rewrite at persist
            mesh_catalog=mesh_manifest.get("mesh_catalog"),
        )
        return status == "ready"
    except Exception as exc:  # noqa: BLE001 — any failure defers to the graph pipeline
        logger.warning("Deep Agent lesson path failed (%s); falling back to LangGraph", exc)
        return False


def _brief(course_id: str, plan: dict, topic: str, design: str = "page") -> str:
    extra = ""
    if design == "studio":
        extra = (
            " This is a STUDIO lesson: first delegate to `mesh_viz` (writes /build/mesh/manifest.json), "
            "then have `capsule_author` build the Canvas Studio specimen-explorer shell wiring in those "
            "meshes."
        )
    elif design == "slide":
        extra = (
            " This is a SLIDE lesson: `capsule_author` must build a stepped slide deck (one idea "
            "per slide, prev/next controls with data-lesson-control) — never a scrolling page."
        )
    elif (plan.get("archetype") or "explainer").lower() in _COMPUTE_ARCHETYPES:
        extra = (
            " For this data/simulation lesson, first delegate to `data_synthesizer` (writes "
            "/build/dataset.json) and `viz_engineer` (writes /build/compute/manifest.json), and have "
            "the capsule embed the resulting plots."
        )
    if design == "page":
        extra += (
            " This is an embedded PAGE lesson: the trusted host owns the lesson title and controls. "
            "Start /build/capsule.html directly with the first content section—no title/intro header, "
            "module label, table of contents, sidebar, or section-navigation buttons."
        )
    return (
        "Produce ONE interactive HTML lesson capsule for this lesson.\n"
        f"Topic: {topic}\n"
        f"Lesson title: {plan.get('title')}\n"
        f"Archetype: {plan.get('archetype')}\n"
        f"course_id (pass to emit_progress): {course_id}\n\n"
        "Plan with write_todos first, then delegate via `task`: (1) `researcher` for grounded "
        "facts;" + extra + " optionally `image_artist` (writes /build/media.json image prompts) "
        "and, when available, `animation_coder` (writes /build/anim/*.js canvas modules) if the "
        "lesson benefits; then `capsule_author` to write the finished capsule to "
        "/build/capsule.html (embedding any planned media and inlining animation modules); and "
        "`qa_reviewer` to validate it. The capsule must be a single self-contained HTML document: "
        "Tailwind CDN, at least one <canvas>, one interactive control, and one "
        "<img go-data-src=...>; never touch window.parent, window.top, or localStorage."
    )

"""Source-grounded course creation (stays in services — calls coursegen).

Document ingestion / projections live in `app.rag`; API handlers import those
directly. This module owns `create_course_from_source` only.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Course, CourseSource, Lesson, SourceDocument
from ..schemas import CreateSourceCourse
from . import billing_service
from .billing_plans import MAX_LESSONS_PER_COURSE_CREDIT


async def create_course_from_source(
    db: Session,
    doc: SourceDocument,
    body: CreateSourceCourse,
    *,
    plan_slug: str | None = None,
) -> Course:
    """Plan a chaptered course from a ready source doc, persist it, and fire JIT lesson 0.

    Raises ValueError if the teaching map can't be sequenced (handler maps to 422)
    or if course credits are exhausted when BILLING_ENFORCE is on (handler maps to 402).
    """
    billing_service.ensure_course_credit_available(db, doc.user_id, plan_slug)
    settings = get_settings()
    # Lazy-upgrade legacy rows before planning.
    if settings.rag_teaching_map_planner:
        from ..rag.ensure import ensure_knowledge_tree

        doc = await ensure_knowledge_tree(db, doc)
        db.refresh(doc)

    sm = doc.source_map or {}
    has_tm = bool((sm.get("teaching_map") or {}).get("chapters"))
    # Always prefer teaching_map when present; plan_source_course synthesizes from sections otherwise.
    use_tm = bool(settings.rag_teaching_map_planner and has_tm)

    # selected_sections from the UI are section *titles*; map to outline node ids when present.
    selected_outline_nodes: list[str] | None = None
    if body.selected_sections:
        outline_nodes = ((sm.get("document_outline") or {}).get("nodes") or [])
        wanted = set(body.selected_sections)
        mapped = [
            n["id"]
            for n in outline_nodes
            if n.get("id") and (n.get("title") in wanted or n.get("id") in wanted)
        ]
        selected_outline_nodes = mapped or None

    # Syllabus planner owns planning (Deep Agents when enabled + no teaching map;
    # otherwise deterministic teaching map / section synthetic fallback).
    from ..coursegen.agents.syllabus_planner import plan_sourced_syllabus
    from ..coursegen.studio_catalog import is_studio_knobs, shape_studio_syllabus

    lesson_count = 1 if body.design_mode == "studio" else min(
        body.lesson_count, MAX_LESSONS_PER_COURSE_CREDIT
    )

    plan = await plan_sourced_syllabus(
        sm,
        title=doc.title or doc.filename,
        excerpt=doc.full_text or "",
        difficulty=body.difficulty,
        lesson_count=lesson_count,
        mode=body.mode,
        use_teaching_map=use_tm,
        selected_outline_nodes=selected_outline_nodes,
    )
    if is_studio_knobs({"design_mode": body.design_mode}):
        plan = shape_studio_syllabus(
            plan,
            doc.title or doc.filename or "Studio",
            {"studio_mode": body.studio_mode},
        )

    if use_tm:
        from ..rag.context import validate_lesson_scopes

        errs = validate_lesson_scopes(
            sm.get("teaching_map") or {},
            plan.get("lesson_scopes") or {},
            selected_outline_nodes=selected_outline_nodes,
        )
        if errs:
            raise ValueError(f"ungrounded teaching-map plan: {'; '.join(errs)}")

    course = Course(
        user_id=doc.user_id,
        topic=plan["title"],
        title=plan["title"],
        archetype="explainer",
        status="ready",  # roadmap ready; per-lesson artifacts generate JIT
        knobs={
            "source_document_id": doc.id,
            "source_type": doc.source_type,
            "source_mode": body.mode,
            "selected_sections": body.selected_sections,
            "grounding_required": True,
            "lesson_scopes": plan.get("lesson_scopes") or {},
            "planner": plan.get("planner") or ("teaching_map" if use_tm else "sections"),
            "difficulty": body.difficulty,
            "design_mode": body.design_mode,
            "studio_mode": body.studio_mode,
            "style_theme": body.style_theme,
            "review_outline": body.review_outline,
            "video_sync": doc.source_type == "video",
            "max_lessons": MAX_LESSONS_PER_COURSE_CREDIT,
        },
    )
    db.add(course)
    db.flush()  # assign course.id before adding children
    db.add(
        CourseSource(
            course_id=course.id,
            source_document_id=doc.id,
            selected_sections=body.selected_sections,
            mode=body.mode,
        )
    )

    # Outline HITL: park the plan for teacher review instead of creating lessons.
    if body.review_outline:
        from .outline_service import draft_outline

        db.commit()
        db.refresh(course)
        draft_outline(db, course, plan)
        return course

    ordinal = 0
    for ch_i, chapter in enumerate(plan["chapters"]):
        for les in chapter["lessons"]:
            if ordinal >= MAX_LESSONS_PER_COURSE_CREDIT:
                break
            db.add(
                Lesson(
                    course_id=course.id,
                    ordinal=ordinal,
                    title=les["title"],
                    objective=les["objective"],
                    status="pending",
                    archetype=les["archetype"],
                    module_ordinal=ch_i,
                    module_title=chapter["title"],
                )
            )
            ordinal += 1
        if ordinal >= MAX_LESSONS_PER_COURSE_CREDIT:
            break
    db.commit()
    db.refresh(course)
    billing_service.spend_course_credit(db, doc.user_id, course.id)
    # Fire grounded generation for lesson 0 (JIT; later lessons generate on completion).
    first = min(course.lessons, key=lambda x: x.ordinal, default=None)
    if first:
        from . import course_service

        course_service.start_generation(db, course, first)
    return course

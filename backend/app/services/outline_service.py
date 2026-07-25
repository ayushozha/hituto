"""Chapter-outline HITL orchestration (course-authoring-flow §3).

Owns the outline state machine on Course rows:

    draft (outline_review) → edit* / revise* → approve → lessons + generation

The loop is app-level and restart-safe by construction: the outline JSON and
`course.status = "outline_review"` live in the DB, and each revision is a fresh
bounded LLM call — there is no in-flight interrupt to lose on restart.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.progress import ProgressEvent, broker
from ..core.tasks import spawn
from ..coursegen import run_generation
from ..coursegen.outline import plan_to_outline, revise_outline, validate_outline_grounding
from ..models import Course, Lesson, SourceDocument
from ..schemas import OutlineDoc, OutlineOut, OutlineReviewRequest
from . import billing_service

logger = logging.getLogger(__name__)


async def _emit(course_id: str, stage: str, detail: str, pct: int) -> None:
    await broker.publish(course_id, ProgressEvent(stage=stage, detail=detail, pct=pct))


def review_outline_requested(knobs: dict | None) -> bool:
    return bool((knobs or {}).get("review_outline"))


def _teaching_map(db: Session, course: Course) -> dict | None:
    sid = (course.knobs or {}).get("source_document_id")
    if not sid:
        return None
    doc = db.get(SourceDocument, sid)
    return ((doc.source_map or {}).get("teaching_map") or None) if doc else None


def _resolved_design(course: Course) -> str:
    from ..coursegen.presentation import resolve_presentation

    knobs = course.knobs or {}
    return resolve_presentation(
        {"title": course.title or course.topic, "topic": course.topic}, knobs
    )


# --- draft ------------------------------------------------------------------


def draft_outline(db: Session, course: Course, plan: dict) -> dict:
    """Persist the planned syllabus as an OutlineDoc draft awaiting teacher review."""
    outline = plan_to_outline(plan, design=_resolved_design(course))
    course.outline = outline
    course.status = "outline_review"
    course.title = plan.get("title") or course.title or course.topic
    if plan.get("cover_prompt") and not course.cover_prompt:
        course.cover_prompt = plan["cover_prompt"]
    if plan.get("subtitle") and not course.tagline:
        course.tagline = plan["subtitle"]
    db.commit()
    db.refresh(course)
    return outline


# --- read -------------------------------------------------------------------


def get_outline(course: Course) -> OutlineOut:
    return OutlineOut(
        course_id=course.id,
        course_status=course.status,
        outline=OutlineDoc.model_validate(course.outline) if course.outline else None,
        max_revisions=get_settings().max_outline_revisions,
    )


# --- review decisions -------------------------------------------------------


def review_outline(
    db: Session,
    course: Course,
    body: OutlineReviewRequest,
    *,
    plan_slug: str | None = None,
) -> OutlineOut:
    """Apply a teacher decision. Raises ValueError on invalid state/input (HTTP 400/409)."""
    if course.status != "outline_review":
        raise ValueError("course is not awaiting outline review")
    if not course.outline:
        raise ValueError("course has no outline draft")

    if body.action == "approve":
        billing_service.ensure_course_credit_available(db, course.user_id, plan_slug)
        _approve(db, course)
        # Approval is the spend moment for reviewed courses (drafting was free).
        billing_service.spend_course_credit(db, course.user_id, course.id)
    elif body.action == "edit":
        if body.outline is None:
            raise ValueError("action=edit requires an outline payload")
        _apply_edit(db, course, body.outline)
    else:  # revise
        if not body.feedback:
            raise ValueError("action=revise requires feedback")
        _schedule_revision(db, course, body.feedback)
    return get_outline(course)


def _apply_edit(db: Session, course: Course, edited: OutlineDoc) -> None:
    """Persist the teacher's directly-edited outline verbatim (no LLM round-trip)."""
    current = OutlineDoc.model_validate(course.outline)
    doc = edited.model_dump()
    doc["design"] = current.design  # teacher-picked at creation; not editable here
    doc["status"] = "outline_review"
    doc["revision"] = current.revision + 1
    doc["feedback_log"] = current.feedback_log
    errors = validate_outline_grounding(doc, _teaching_map(db, course))
    if errors:
        raise ValueError("; ".join(errors))
    course.outline = doc
    db.commit()
    db.refresh(course)


def _schedule_revision(db: Session, course: Course, feedback: str) -> None:
    """Kick a background LLM revision round (bounded; soft cap — editing always works)."""
    current = OutlineDoc.model_validate(course.outline)
    cap = get_settings().max_outline_revisions
    if len(current.feedback_log) >= cap:
        raise ValueError(
            f"revision limit ({cap}) reached — edit the outline directly and approve"
        )
    teaching_map = _teaching_map(db, course)
    spawn(
        _run_revision(course.id, course.topic, feedback, teaching_map),
        name=f"outline-revise:{course.id}",
    )


async def _run_revision(
    course_id: str, topic: str, feedback: str, teaching_map: dict | None
) -> None:
    await _emit(course_id, "outline", "Revising the course outline…", 8)
    try:
        with SessionLocal() as db:
            course = db.get(Course, course_id)
            if course is None or course.status != "outline_review" or not course.outline:
                return
            outline = dict(course.outline)
        revised = await revise_outline(outline, feedback, topic=topic, teaching_map=teaching_map)
        with SessionLocal() as db:
            course = db.get(Course, course_id)
            if course is None or course.status != "outline_review":
                return  # approved/deleted while revising — drop the stale revision
            course.outline = revised
            db.commit()
        await _emit(course_id, "outline_revised", "Outline revised — ready for review.", 10)
    except Exception as exc:  # noqa: BLE001 — a failed revision never fails the course
        logger.warning("outline revision failed for %s: %s", course_id, exc)
        await _emit(course_id, "outline", f"Revision failed: {exc}", 10)


# --- approve → lessons ------------------------------------------------------


def _approve(db: Session, course: Course) -> None:
    """Flatten the approved outline into Lesson rows and start lesson 0 (JIT)."""
    doc = OutlineDoc.model_validate(course.outline)
    knobs = dict(course.knobs or {})
    sourced = bool(knobs.get("source_document_id"))

    ordinal = 0
    first_lesson: Lesson | None = None
    lesson_scopes: dict[str, dict] = {}
    for ch_i, chapter in enumerate(doc.chapters):
        for les in chapter.lessons:
            lesson = Lesson(
                course_id=course.id,
                ordinal=ordinal,
                title=les.title,
                objective=les.objective,
                archetype=les.archetype or "explainer",
                estimated_duration=les.estimated_duration or "5m",
                status="pending",
                module_ordinal=ch_i,
                module_title=chapter.title,
            )
            db.add(lesson)
            if first_lesson is None:
                first_lesson = lesson
            cids = les.chapter_ids or chapter.source_chapter_ids
            if sourced and cids:
                lesson_scopes[str(ordinal)] = {
                    "chapter_ids": list(cids),
                    "covers": (les.objective or "")[:240],
                    "avoid": "",
                }
            ordinal += 1

    if ordinal == 0:
        raise ValueError("outline has no lessons")

    doc.status = "approved"
    course.outline = doc.model_dump()
    course.title = doc.title or course.title
    # Rebuild grounding scopes from the (possibly edited) outline, keyed by new ordinals.
    if sourced:
        knobs["lesson_scopes"] = lesson_scopes
        course.knobs = knobs
    # Sourced roadmaps are navigable immediately (JIT artifacts); free-topic mirrors
    # run_syllabus_planning and stays "generating" until lesson 0 lands.
    course.status = "ready" if sourced else "generating"
    course.error = None
    db.commit()
    db.refresh(course)

    if first_lesson is not None:
        first_lesson.status = "generating"
        db.commit()
        spawn(
            run_generation(course.id, first_lesson.id, course.topic, course.knobs),
            name=f"gen:{first_lesson.id}",
        )

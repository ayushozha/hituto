"""Tutor-facing context builder — wraps rag.get_lesson_context() + lesson metadata."""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..models import Course, Lesson
from ..rag.context import get_lesson_context
from ..schemas.tutor import ChatMessage
from ..services.profile_service import generation_context, get_preferences
from ..surface import build_surface
from ..services.whiteboard_service import latest_context as latest_whiteboard
from ..services.coding_lab_service import latest_context as latest_coding_lab


async def build_tutor_context(
    db: Session, course: Course, lesson: Lesson, messages: List[ChatMessage]
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Build the lesson context (+ pack-first / two-stage source grounding) and normalize messages.

    Shared by the non-streaming `chat()` and the streaming endpoint so both feed the model the
    same context. Includes an artifact digest for voice/text parity (tutor-agent Phase 2.4).
    """
    context: Dict[str, Any] = {
        "user_id": course.user_id,
        "course_id": course.id,
        "lesson_id": lesson.id,
        "course_title": course.title or course.topic,
        "lesson_title": lesson.title,
        "lesson_objective": lesson.objective,
        "lesson_archetype": lesson.archetype,
    }

    # Design-agnostic grounding (specs/design_agents §6): the surface digester handles
    # every artifact kind — including A2UI trees, which the old HTML-only digest missed.
    surface = build_surface(db, course, lesson)
    if surface.digest:
        context["artifact_digest"] = surface.digest
    context["surface_kind"] = surface.kind

    whiteboard = latest_whiteboard(lesson_id=lesson.id, user_id=course.user_id)
    if whiteboard:
        context["whiteboard_state"] = whiteboard

    coding_lab = latest_coding_lab(lesson_id=lesson.id, user_id=course.user_id)
    if coding_lab:
        context["coding_lab_state"] = coding_lab

    # Learner profile (specs/learner_profile): live read so explanations track the user's
    # current preferences. Fail-closed — any error just omits the block.
    try:
        prefs = get_preferences(db, course.user_id)
        if prefs is not None:
            learner_profile = generation_context(prefs)
            if learner_profile:
                context["learner_profile"] = learner_profile
    except Exception:  # noqa: BLE001
        pass

    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    rag = await get_lesson_context(db, course=course, lesson=lesson, user_query=last_user or None)
    if rag.excerpts:
        context["source_excerpts"] = rag.excerpts
        refs = [e.get("ref_label") for e in rag.excerpts if e.get("ref_label")]
        if refs:
            context["source_refs"] = refs
    context["rag_mode"] = rag.mode
    if rag.pack_id:
        context["rag_pack_id"] = rag.pack_id
    if rag.source_document_id:
        context["source_document_id"] = rag.source_document_id
    if rag.chapter_ids:
        context["chapter_ids"] = rag.chapter_ids
    if rag.passage_ids:
        context["passage_ids"] = rag.passage_ids

    msgs: List[Dict[str, Any]] = []
    for msg in messages:
        m: Dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_call:
            m["tool_call"] = msg.tool_call.model_dump()
        if msg.whiteboard_state:
            m["whiteboard_state"] = msg.whiteboard_state
        if msg.coding_lab_state:
            m["coding_lab_state"] = msg.coding_lab_state
        msgs.append(m)
    return context, msgs

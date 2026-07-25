"""Tutor chat business logic: build lesson context and run the chat."""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..models import Course, Lesson
from ..schemas.tutor import ChatMessage
from ..tutor import run_tutor_chat
from ..tutor.context import build_tutor_context


async def build_context(
    db: Session, course: Course, lesson: Lesson, messages: List[ChatMessage]
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Delegate to tutor.context — kept for existing importers/tests."""
    return await build_tutor_context(db, course, lesson, messages)


async def chat(db: Session, course: Course, lesson: Lesson, messages: List[ChatMessage]) -> Dict[str, Any]:
    context, msgs = await build_tutor_context(db, course, lesson, messages)
    return await run_tutor_chat(
        messages=msgs, course_id=course.id, lesson_id=lesson.id, lesson_context=context
    )

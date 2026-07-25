"""Voice instructor WebSocket endpoint."""
from __future__ import annotations

import logging
import math
import time

from fastapi import APIRouter, HTTPException, WebSocket, status

from ...core.auth import get_principal_from_websocket
from ...core.config import get_settings
from ...core.db import SessionLocal
from ...models import Course, Lesson
from ...voice.grounding import load_lesson_context
from ...voice.session import VoiceSession
from ...services import billing_service, insight_service
from ...services.whiteboard_service import latest_context as latest_whiteboard
from ...services.coding_lab_service import latest_context as latest_coding_lab

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/lessons/{lesson_id}/voice", tags=["voice"])


@router.websocket("/ws")
async def voice_ws(websocket: WebSocket, course_id: str, lesson_id: str):
    await websocket.accept()
    # Settings are lru_cached for the process lifetime; refresh on each voice session so
    # .env changes (e.g. LLM_MODEL) apply without a manual server restart.
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.voice_ready():
        await _close_with_error(websocket, "voice instructor is not configured", code=1013)
        return

    try:
        principal = get_principal_from_websocket(websocket)
        user_id = principal.user_id
        _authorize_voice_session(course_id=course_id, lesson_id=lesson_id, user_id=user_id)
        with SessionLocal() as db:
            billing_service.ensure_voice_minutes_available(
                db, user_id, principal.plan_slug, need=1
            )
    except HTTPException as exc:
        await _close_with_error(websocket, str(exc.detail), code=1008)
        return
    except ValueError as exc:
        await _close_with_error(websocket, str(exc), code=1008)
        return

    lesson_context = load_lesson_context(course_id, lesson_id) or {
        "course_title": "this course",
        "lesson_title": "this lesson",
        "lesson_objective": "",
        "lesson_archetype": "explainer",
        "artifact_digest": "",
    }
    # Ids the generate_ui (Path B) tool needs to tag + serve stored capsules for THIS owner/lesson.
    lesson_context["course_id"] = course_id
    lesson_context["lesson_id"] = lesson_id
    lesson_context["user_id"] = user_id
    whiteboard = latest_whiteboard(lesson_id=lesson_id, user_id=user_id)
    if whiteboard:
        lesson_context["whiteboard_state"] = whiteboard
    coding_lab = latest_coding_lab(lesson_id=lesson_id, user_id=user_id)
    if coding_lab:
        lesson_context["coding_lab_state"] = coding_lab
    started = time.monotonic()
    try:
        def on_user_text(text: str) -> None:
            with SessionLocal() as db:
                insight_service.record_tutor_question(
                    db, user_id, course_id, lesson_id, text, source="voice"
                )

        def on_response_finished(response_ms: int, response_status: str) -> None:
            with SessionLocal() as db:
                insight_service.record_tutor_finished(
                    db,
                    user_id,
                    course_id,
                    lesson_id,
                    response_ms,
                    source="voice",
                    status=response_status,
                )

        await VoiceSession(
            websocket=websocket,
            lesson_context=lesson_context,
            on_user_text=on_user_text,
            on_response_finished=on_response_finished,
        ).run()
    except Exception:
        logger.exception("voice: websocket session crashed")
        try:
            await _close_with_error(websocket, "voice session failed", code=1011)
        except Exception:
            pass
    finally:
        # Only bill after a real session — failed/instant closes under 5s stay free.
        elapsed = time.monotonic() - started
        if elapsed >= 5:
            elapsed_min = max(1, int(math.ceil(elapsed / 60.0)))
            try:
                with SessionLocal() as db:
                    billing_service.spend_voice_minutes(
                        db, user_id, elapsed_min, course_id=course_id
                    )
            except Exception:
                logger.exception("voice: failed to record voice minutes")


def _authorize_voice_session(*, course_id: str, lesson_id: str, user_id: str) -> None:
    with SessionLocal() as db:
        course = db.get(Course, course_id)
        lesson = db.get(Lesson, lesson_id)
        if not course or not lesson:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course or Lesson not found")
        if course.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course or Lesson not found")
        if lesson.course_id != course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lesson does not belong to specified Course",
            )


async def _close_with_error(websocket: WebSocket, detail: str, *, code: int) -> None:
    await websocket.send_json({"type": "error", "detail": detail})
    await websocket.close(code=code)

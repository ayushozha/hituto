"""GuideBridge integration: the page-control bridge for lesson capsules.

One process-wide :class:`guidebridge.AgentBridge` connects lesson-viewer tabs
(via a dedicated WebSocket, mounted in ``api/v1/agentbridge.py``) to the voice
tutor's page tools. The in-iframe half is the guidebridge iframe runtime that
``capsule/postprocess.py`` injects into every lesson artifact.

Session identity: ``{user_id}:{lesson_id}``. The authorizer derives it from the
``?access_token=`` JWT plus the course/lesson ownership check and returns it to
guidebridge, which then rejects any client whose hello claims a different
sessionId — the client's claim is verified, never trusted.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, WebSocket
from guidebridge import AgentBridge

from .core.auth import get_user_id_from_websocket
from .core.config import get_settings
from .core.db import SessionLocal
from .models import Course, Lesson

logger = logging.getLogger(__name__)


def page_session_id(user_id: str, lesson_id: str) -> str:
    """The bridge session id shared by the lesson viewer and the voice tutor."""
    return f"{user_id}:{lesson_id}"


def check_lesson_access(course_id: str, lesson_id: str, user_id: str) -> bool:
    """True when the user owns the course and the lesson belongs to it.

    Boolean twin of ``api/v1/voice.py:_authorize_voice_session`` (which keeps
    its HTTP-status granularity for the voice endpoint's error frames).
    """
    with SessionLocal() as db:
        course = db.get(Course, course_id)
        lesson = db.get(Lesson, lesson_id)
        return bool(
            course
            and lesson
            and course.user_id == user_id
            and lesson.course_id == course_id
        )


async def _authorize(ws: WebSocket):
    try:
        user_id = get_user_id_from_websocket(ws)
    except HTTPException:
        return False
    course_id = ws.path_params.get("course_id") or ""
    lesson_id = ws.path_params.get("lesson_id") or ""
    if not course_id or not lesson_id or not check_lesson_access(course_id, lesson_id, user_id):
        logger.warning("agent-bridge: rejected ws (user=%s lesson=%s)", user_id, lesson_id)
        return False
    return page_session_id(user_id, lesson_id)


bridge = AgentBridge(
    path="/courses/{course_id}/lessons/{lesson_id}/agent-bridge/ws",
    timeout_s=get_settings().voice_page_tool_timeout_s,
    authorize=_authorize,
)

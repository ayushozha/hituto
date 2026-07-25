"""Durable whiteboard sessions shared between widgets and lesson agents."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..core.db import SessionLocal
from ..models import Lesson, WhiteboardSession

MAX_ELEMENTS = 40


def _scene(elements: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(elements, list):
        return {"elements": []}
    cleaned = [item for item in elements if isinstance(item, dict) and not item.get("isDeleted")]
    return {"elements": cleaned[-MAX_ELEMENTS:]}


def create_session(
    *, lesson_id: str, user_id: str, tool_call_id: str, title: str, intent: str, elements: Any
) -> WhiteboardSession | None:
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        if lesson is None:
            return None
        session = WhiteboardSession(
            course_id=lesson.course_id,
            lesson_id=lesson_id,
            user_id=user_id,
            tool_call_id=tool_call_id,
            title=title or "Whiteboard",
            intent=intent or "",
            scene=_scene(elements),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


def sync_session(
    *, session_id: str, lesson_id: str, user_id: str, elements: Any
) -> WhiteboardSession | None:
    with SessionLocal() as db:
        session = db.get(WhiteboardSession, session_id)
        if session is None or session.lesson_id != lesson_id or session.user_id != user_id:
            return None
        session.scene = _scene(elements)
        session.revision += 1
        db.commit()
        db.refresh(session)
        return session


def latest_context(*, lesson_id: str, user_id: str) -> dict[str, Any] | None:
    """Return the newest show_whiteboard session for this lesson/user.

    Prefer created_at (not updated_at) so a recently synced older board cannot
    displace a newer board the UI is showing. Scene content for that board is
    still the latest revision via sync_session.
    """
    with SessionLocal() as db:
        session = db.scalars(
            select(WhiteboardSession)
            .where(
                WhiteboardSession.lesson_id == lesson_id,
                WhiteboardSession.user_id == user_id,
            )
            .order_by(
                WhiteboardSession.created_at.desc(),
                WhiteboardSession.id.desc(),
            )
            .limit(1)
        ).first()
        return session_context(session) if session else None


def session_context(session: WhiteboardSession) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "tool_call_id": session.tool_call_id,
        "revision": session.revision,
        "title": session.title,
        "intent": session.intent,
        "elements": (session.scene or {}).get("elements", []),
    }

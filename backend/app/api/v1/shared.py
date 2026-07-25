"""Public (unauthenticated) read-only access to a single shared lesson.

A lesson owner mints a share token (see courses.py `create_share_link`); these
routes resolve that token to exactly one lesson and serve it with NO auth. The
token IS the authorization — there is no ownership check here by design. Nothing
else (other lessons, user_id, course internals) is reachable through this router.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...schemas import SharedLessonOut
from ...capsule import artifact_csp, ensure_artifact_runtime
from ...services import course_service

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/lessons/{share_token}", response_model=SharedLessonOut)
def shared_lesson(share_token: str, db: Session = Depends(get_db)):
    """Public lesson metadata for the read-only shared view."""
    lesson = course_service.lesson_by_share_token(db, share_token)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    return SharedLessonOut(
        title=lesson.title,
        archetype=lesson.archetype,
        estimated_duration=lesson.estimated_duration,
        course_title=lesson.course.title if lesson.course else None,
    )


@router.get("/lessons/{share_token}/artifact", response_class=HTMLResponse)
def shared_lesson_artifact(share_token: str, db: Session = Depends(get_db)):
    """Serve the shared lesson's latest artifact HTML with the sandbox-safe CSP."""
    lesson = course_service.lesson_by_share_token(db, share_token)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    art = course_service.latest_artifact(db, lesson.id)
    if not art:
        raise HTTPException(404, "artifact not ready")
    return HTMLResponse(
        content=ensure_artifact_runtime(art.html),
        headers={"Content-Security-Policy": artifact_csp()},
    )

"""Courses API: create, list (cards), detail, delete, SSE progress, artifact.

Thin handlers: ownership/404 checks + response models here; logic in course_service.
"""
from __future__ import annotations

import asyncio
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...core.auth import AuthPrincipal, get_current_principal, get_current_user_id, get_user_id_from_request
from ...core.db import get_db
from ...core.progress import broker
from ...models import Course, Lesson, SourceDocument
from ...schemas.course import AppendChapter, AppendVideoSource
from ...schemas import (
    ArtifactA2UIOut,
    ArtifactReadingOut,
    ArtifactVersionOut,
    CourseCard,
    CourseDetail,
    CreateCourse,
    LessonSourcePackOut,
    OutlineOut,
    OutlineReviewRequest,
    PatchA2UISectionRequest,
    PatchHtmlSectionRequest,
    RefinementRequest,
    ReviewLessonRequest,
    SaveArtifactRequest,
    ShareLinkOut,
    UpdateCourse,
    VideoGuideOut,
)
from ...capsule import artifact_csp, ensure_artifact_runtime
from ...services import course_service, outline_service

router = APIRouter(prefix="/courses", tags=["courses"])


# Backward-compat alias for tests/importers that still call `_artifact_csp`.
_artifact_csp = artifact_csp


def _owned_course(db: Session, course_id: str, user_id: str) -> Course:
    c = db.get(Course, course_id)
    if not c or c.user_id != user_id:
        raise HTTPException(404, "course not found")
    return c


def _owned_lesson(
    db: Session, course_id: str, lesson_id: str, user_id: str
) -> tuple[Course, Lesson]:
    c = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not c or c.user_id != user_id or not lesson or lesson.course_id != course_id:
        raise HTTPException(404, "lesson not found")
    return c, lesson


@router.post("", response_model=CourseCard, status_code=201)
async def create_course(
    body: CreateCourse,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    try:
        course = course_service.create_course(
            db, principal.user_id, body, plan_slug=principal.plan_slug
        )
    except ValueError as exc:
        raise HTTPException(402, str(exc)) from exc
    return course_service.card(course)


@router.get("", response_model=list[CourseCard])
def list_courses(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return course_service.list_cards(db, user_id, q, status)


@router.get("/{course_id}", response_model=CourseDetail)
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return course_service.detail(db, _owned_course(db, course_id, user_id))


@router.get("/{course_id}/lessons/{lesson_id}/source-pack", response_model=LessonSourcePackOut | None)
def get_lesson_source_pack(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """The lesson's grounding pack for the viewer source drawer (task 46). Null for topic lessons."""
    _owned_course(db, course_id, user_id)
    return course_service.lesson_source_pack(db, lesson_id)


@router.get("/{course_id}/video-guide", response_model=VideoGuideOut | None)
def get_video_guide(
    course_id: str,
    lesson_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Timestamped private training guide for a video-grounded course."""
    course = _owned_course(db, course_id, user_id)
    if lesson_id:
        _owned_lesson(db, course_id, lesson_id, user_id)
    return course_service.video_guide(db, course, lesson_id)


@router.post("/{course_id}/videos", response_model=CourseDetail, status_code=201)
async def append_video(
    course_id: str,
    body: AppendVideoSource,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Add one analyzed video as the next chapter in an existing video course."""
    course = _owned_course(db, course_id, user_id)
    source = db.get(SourceDocument, body.source_id)
    if not source or source.user_id != user_id:
        raise HTTPException(404, "video source not found")
    try:
        course_service.append_video_source(db, course, source, description=body.description)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return course_service.detail(db, course)


@router.post("/{course_id}/chapters", response_model=CourseDetail, status_code=201)
async def append_chapter(
    course_id: str,
    body: AppendChapter,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Add a generated chapter using the course's existing design mode."""
    course = _owned_course(db, course_id, user_id)
    try:
        course_service.append_chapter(
            db,
            course,
            title=body.title,
            description=body.description,
            archetype=body.archetype,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return course_service.detail(db, course)


@router.patch("/{course_id}", response_model=CourseCard)
def update_course(
    course_id: str,
    body: UpdateCourse,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c = _owned_course(db, course_id, user_id)
    return course_service.update_course(db, c, body)


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c = _owned_course(db, course_id, user_id)
    db.delete(c)
    db.commit()


@router.post("/{course_id}/refinements", response_model=CourseCard, status_code=202)
async def refine_course(
    course_id: str,
    body: RefinementRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c = _owned_course(db, course_id, user_id)
    lesson_id = body.lesson_id
    if not lesson_id:
        first = course_service.first_lesson(db, course_id)
        lesson_id = first.id if first else None
    if not lesson_id:
        raise HTTPException(400, "No lesson found to refine")
    lesson = db.get(Lesson, lesson_id)
    course_service.start_generation(
        db,
        c,
        lesson,
        refinement=body.prompt,
        mark_course=True,
        target_id=body.target_id,
        target_html=body.target_html,
    )
    return course_service.card(c)


@router.put(
    "/{course_id}/lessons/{lesson_id}/artifact",
    response_model=ArtifactVersionOut,
)
def save_lesson_artifact(
    course_id: str,
    lesson_id: str,
    body: SaveArtifactRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Persist HTML from in-iframe Edit mode (postprocess gate, no LLM)."""
    c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    try:
        return course_service.save_lesson_html(db, c, lesson, body.html)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch(
    "/{course_id}/lessons/{lesson_id}/artifact/a2ui/sections/{section_id}",
    response_model=ArtifactA2UIOut,
)
async def patch_a2ui_section(
    course_id: str,
    lesson_id: str,
    section_id: str,
    body: PatchA2UISectionRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Replace one A2UI section subtree; re-validate and version the artifact."""
    _c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    try:
        return await course_service.patch_a2ui_section(
            db,
            lesson,
            section_id=section_id,
            root=body.root,
            title=body.title,
            instruction=body.instruction,
            insert=body.insert,
            replace_node_path=body.replace_node_path,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch(
    "/{course_id}/lessons/{lesson_id}/artifact/html/sections/{section_id}",
    response_model=ArtifactVersionOut,
)
async def patch_html_section(
    course_id: str,
    lesson_id: str,
    section_id: str,
    body: PatchHtmlSectionRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Rewrite one HTML data-lesson-section; siblings stay unchanged."""
    _c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    try:
        return await course_service.patch_html_section(
            db,
            lesson,
            section_id=section_id,
            instruction=body.instruction,
            target_html=body.target_html,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{course_id}/lessons/{lesson_id}/regenerate", response_model=CourseCard, status_code=202)
async def regenerate_lesson(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    course_service.start_generation(
        db, c, lesson, refinement=f"Regenerate lesson: {lesson.title}", mark_course=True
    )
    return course_service.card(c)


@router.post("/{course_id}/lessons/{lesson_id}/generate", response_model=CourseCard, status_code=202)
async def generate_lesson(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    course_service.start_generation(db, c, lesson)
    return course_service.card(c)


@router.post("/{course_id}/lessons/{lesson_id}/complete", response_model=CourseDetail)
def complete_lesson(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    course_service.complete_and_prefetch(db, c, lesson)
    return course_service.detail(db, c)


@router.post("/{course_id}/lessons/{lesson_id}/review", response_model=CourseDetail, status_code=202)
async def review_lesson(
    course_id: str,
    lesson_id: str,
    body: ReviewLessonRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Approve or reject a lesson paused at teacher review (HITL)."""
    c, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    try:
        course_service.review_lesson(db, c, lesson, action=body.action, message=body.message)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return course_service.detail(db, c)


@router.get("/{course_id}/outline", response_model=OutlineOut)
async def get_outline(
    course_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Current chapter-outline doc (draft or approved) for the outline editor."""
    c = _owned_course(db, course_id, user_id)
    return outline_service.get_outline(c)


@router.post("/{course_id}/outline/review", response_model=OutlineOut, status_code=202)
async def review_outline(
    course_id: str,
    body: OutlineReviewRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    """Teacher decision on the outline draft: approve, direct edit, or revise-with-feedback."""
    c = _owned_course(db, course_id, principal.user_id)
    try:
        return outline_service.review_outline(
            db, c, body, plan_slug=principal.plan_slug
        )
    except ValueError as exc:
        msg = str(exc)
        if "course credit" in msg.lower():
            raise HTTPException(402, msg) from exc
        raise HTTPException(400, msg) from exc


@router.post("/{course_id}/lessons/{lesson_id}/share", response_model=ShareLinkOut)
def create_share_link(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Mint (or return the existing) opt-in public share token for a lesson. Idempotent."""
    _, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    if not lesson.share_token:
        lesson.share_token = secrets.token_urlsafe(16)
        db.commit()
    return ShareLinkOut(share_token=lesson.share_token)


@router.delete("/{course_id}/lessons/{lesson_id}/share", status_code=204)
def revoke_share_link(
    course_id: str,
    lesson_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Revoke a lesson's public share link. Shared URLs stop working immediately."""
    _, lesson = _owned_lesson(db, course_id, lesson_id, user_id)
    if lesson.share_token:
        lesson.share_token = None
        db.commit()


@router.get("/{course_id}/versions", response_model=list[ArtifactVersionOut])
def versions(
    course_id: str,
    lesson_id: str | None = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    c = _owned_course(db, course_id, user_id)
    return course_service.artifact_versions(db, c, lesson_id)


@router.get("/{course_id}/events")
async def events(course_id: str, request: Request, db: Session = Depends(get_db)):
    """SSE stream of pipeline progress (R3)."""
    user_id = get_user_id_from_request(request)
    _owned_course(db, course_id, user_id)
    queue = broker.subscribe(course_id)

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "progress", "data": json.dumps(ev.__dict__)}
                # Only end the stream on terminal stages — a prior lesson's ready (pct=100)
                # must not close the socket for a later generation on the same course.
                if ev.stage in ("ready", "failed") and ev.pct >= 100:
                    break
        finally:
            broker.unsubscribe(course_id, queue)

    return EventSourceResponse(gen())


@router.get("/{course_id}/artifact", response_class=HTMLResponse)
def artifact(
    course_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve the latest lesson artifact HTML with sandbox-safe CSP (R5.1)."""
    user_id = get_user_id_from_request(request)
    _owned_course(db, course_id, user_id)
    art = course_service.first_lesson_latest_artifact(db, course_id)
    if not art:
        raise HTTPException(404, "artifact not ready")
    if (getattr(art, "kind", None) or "html") in ("a2ui", "reading"):
        raise HTTPException(415, "lesson uses a trusted doc — fetch /artifact/a2ui or /artifact/reading")
    return HTMLResponse(
        content=ensure_artifact_runtime(art.html or ""),
        headers={"Content-Security-Policy": _artifact_csp()},
    )


@router.get("/{course_id}/lessons/{lesson_id}/artifact", response_class=HTMLResponse)
def lesson_artifact(
    course_id: str,
    lesson_id: str,
    request: Request,
    version: int | None = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id_from_request(request)
    _owned_lesson(db, course_id, lesson_id, user_id)
    art = course_service.latest_artifact(db, lesson_id, version)
    if not art:
        raise HTTPException(404, "artifact not ready")
    if (getattr(art, "kind", None) or "html") in ("a2ui", "reading"):
        raise HTTPException(415, "lesson uses a trusted doc — fetch /artifact/a2ui or /artifact/reading")
    return HTMLResponse(
        content=ensure_artifact_runtime(art.html or ""),
        headers={"Content-Security-Policy": _artifact_csp()},
    )


@router.get("/{course_id}/lessons/{lesson_id}/artifact/a2ui", response_model=ArtifactA2UIOut)
def lesson_artifact_a2ui(
    course_id: str,
    lesson_id: str,
    request: Request,
    version: int | None = None,
    db: Session = Depends(get_db),
):
    """Serve a persisted A2UI lesson document (trusted React path — no iframe)."""
    user_id = get_user_id_from_request(request)
    _owned_lesson(db, course_id, lesson_id, user_id)
    art = course_service.latest_artifact(db, lesson_id, version)
    if not art or (getattr(art, "kind", None) or "html") != "a2ui" or not art.a2ui:
        raise HTTPException(404, "a2ui artifact not ready")
    doc = art.a2ui if isinstance(art.a2ui, dict) else {}
    return ArtifactA2UIOut(
        version=art.version,
        title=str(doc.get("title") or "Lesson"),
        intent=str(doc.get("intent") or ""),
        root=doc.get("root") or {"type": "stack", "props": {}, "children": []},
        sections=list(doc.get("sections") or []),
        checks=art.checks or {},
    )


@router.get(
    "/{course_id}/lessons/{lesson_id}/artifact/reading", response_model=ArtifactReadingOut
)
def lesson_artifact_reading(
    course_id: str,
    lesson_id: str,
    request: Request,
    version: int | None = None,
    db: Session = Depends(get_db),
):
    """Serve a persisted reading companion (trusted React path — no iframe)."""
    user_id = get_user_id_from_request(request)
    _owned_lesson(db, course_id, lesson_id, user_id)
    art = course_service.latest_artifact(db, lesson_id, version)
    if not art or (getattr(art, "kind", None) or "html") != "reading" or not art.a2ui:
        raise HTTPException(404, "reading artifact not ready")
    doc = art.a2ui if isinstance(art.a2ui, dict) else {}
    return ArtifactReadingOut(version=art.version, doc=doc, checks=art.checks or {})

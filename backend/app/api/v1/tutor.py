"""Tutor Chat API endpoint: real-time learning assistance (thin handler over tutor_service).

Also serves Path B (generate_ui) HTML capsules: the chat handler sanitizes + stores the model's
HTML and returns only a `ui_id`; the iframe fetches it from `GET .../tutor/ui/{ui_id}` with the
same strict CSP + sandbox model as lesson artifacts.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...core.auth import get_current_user_id, get_user_id_from_request
from ...core.db import get_db
from ...models import Course, Lesson
from ...a2ui import normalize_render_ui
from ...capsule import artifact_csp, ensure_artifact_runtime
from ...capsule import generative_ui
from ...tutor import stream_tutor_events
from ...tutor.client import _UI_FALLBACK
from ...schemas.tutor import (
    ChatToolCall,
    CodingLabRunRequest,
    CodingLabSyncRequest,
    TutorChatRequest,
    TutorChatResponse,
    WhiteboardSyncRequest,
)
from ...services import insight_service, tutor_service
from ...services import coding_lab_service, whiteboard_service

router = APIRouter(prefix="/courses/{course_id}/lessons/{lesson_id}/tutor", tags=["tutor"])


@router.put("/whiteboards/{session_id}")
def sync_whiteboard(
    course_id: str,
    lesson_id: str,
    session_id: str,
    body: WhiteboardSyncRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or course.user_id != user_id or not lesson or lesson.course_id != course_id:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    session = whiteboard_service.sync_session(
        session_id=session_id,
        lesson_id=lesson_id,
        user_id=user_id,
        elements=body.elements,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Whiteboard session not found")
    return whiteboard_service.session_context(session)


@router.put("/coding-labs/{session_id}")
def sync_coding_lab(
    course_id: str,
    lesson_id: str,
    session_id: str,
    body: CodingLabSyncRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or course.user_id != user_id or not lesson or lesson.course_id != course_id:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    session = coding_lab_service.sync_files(
        session_id=session_id,
        lesson_id=lesson_id,
        user_id=user_id,
        files=body.files,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Coding lab session not found")
    return coding_lab_service.session_context(session)


@router.post("/coding-labs/{session_id}/run")
def record_coding_lab_run(
    course_id: str,
    lesson_id: str,
    session_id: str,
    body: CodingLabRunRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Persist a client sandbox run/check result (AG-UI CODING_LAB_* event payload)."""
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or course.user_id != user_id or not lesson or lesson.course_id != course_id:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    session = coding_lab_service.record_run(
        session_id=session_id,
        lesson_id=lesson_id,
        user_id=user_id,
        run={
            "ok": body.ok,
            "passed": body.passed,
            "stdout": body.stdout,
            "stderr": body.stderr,
            "language": body.language,
            "event": body.event,
        },
        files=body.files,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Coding lab session not found")
    return coding_lab_service.session_context(session)


@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(
    course_id: str,
    lesson_id: str,
    body: TutorChatRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or not lesson:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    if course.user_id != user_id:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    if lesson.course_id != course_id:
        raise HTTPException(status_code=400, detail="Lesson does not belong to specified Course")

    question = next(
        (message.content for message in reversed(body.messages) if message.role == "user"), ""
    )
    insight_service.record_tutor_question(db, user_id, course_id, lesson_id, question)
    started_at = time.perf_counter()
    try:
        reply = await tutor_service.chat(db, course, lesson, body.messages)
    except Exception:
        insight_service.record_tutor_finished(
            db,
            user_id,
            course_id,
            lesson_id,
            round((time.perf_counter() - started_at) * 1000),
            status="failed",
        )
        raise
    insight_service.record_tutor_finished(
        db,
        user_id,
        course_id,
        lesson_id,
        round((time.perf_counter() - started_at) * 1000),
        status="completed",
    )

    content = reply.get("content", "")
    tc = reply.get("tool_call")
    tool_call = None
    if tc:
        name = tc.get("name")
        args = tc.get("arguments") or {}
        if name == "generate_ui":
            # Path B: sanitize the untrusted HTML, stash it, and hand back ONLY a ui_id — the raw
            # HTML never reaches the client. Fail closed to text if the security gate rejects it.
            ui_id = generative_ui.sanitize_and_store(
                args.get("html", ""), user_id=user_id, lesson_id=lesson_id
            )
            if ui_id:
                tool_call = ChatToolCall(
                    name="generate_ui",
                    arguments={
                        "title": args.get("title", "Interactive visual"),
                        "intent": args.get("intent", ""),
                        "ui_id": ui_id,
                    },
                )
            elif not content:
                content = _UI_FALLBACK
        elif name == "render_ui":
            # Fail closed: never ship an invalid A2UI tree (defense in depth vs client path).
            normalized = normalize_render_ui(args)
            if normalized:
                tool_call = ChatToolCall(name="render_ui", arguments=normalized)
            elif not content:
                content = _UI_FALLBACK
        else:
            tool_call = ChatToolCall(name=name, arguments=args)

    return TutorChatResponse(role="assistant", content=content, tool_call=tool_call)


@router.post("/chat/stream")
async def tutor_chat_stream(
    course_id: str,
    lesson_id: str,
    body: TutorChatRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Streaming tutor chat (SSE) — additive to POST /chat, which stays the fallback.

    Emits AG-UI-style frames: prose streams token-by-token; a `render_ui` tree streams its args so
    the client can mount it node-by-node; `generate_ui` is sanitized+stored server-side and only its
    `ui_id` is emitted (raw HTML never crosses the wire). The final `TOOL_CALL_END.arguments` are the
    authoritative, re-validated payload.
    """
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or not lesson or course.user_id != user_id:
        raise HTTPException(status_code=404, detail="Course or Lesson not found")
    if lesson.course_id != course_id:
        raise HTTPException(status_code=400, detail="Lesson does not belong to specified Course")

    question = next(
        (message.content for message in reversed(body.messages) if message.role == "user"), ""
    )
    insight_service.record_tutor_question(db, user_id, course_id, lesson_id, question)
    started_at = time.perf_counter()
    try:
        context, msgs = await tutor_service.build_context(db, course, lesson, body.messages)
    except Exception:
        insight_service.record_tutor_finished(
            db,
            user_id,
            course_id,
            lesson_id,
            round((time.perf_counter() - started_at) * 1000),
            status="failed",
        )
        raise

    async def gen():
        response_status = "interrupted"
        try:
            async for frame in stream_tutor_events(
                msgs,
                course_id=course_id,
                lesson_id=lesson_id,
                user_id=user_id,
                lesson_context=context,
            ):
                yield {"data": json.dumps(frame)}
            response_status = "completed"
        except Exception:
            response_status = "failed"
            raise
        finally:
            insight_service.record_tutor_finished(
                db,
                user_id,
                course_id,
                lesson_id,
                round((time.perf_counter() - started_at) * 1000),
                status=response_status,
            )

    return EventSourceResponse(gen())


@router.get("/ui/{ui_id}", response_class=HTMLResponse)
def tutor_ui(
    course_id: str,
    lesson_id: str,
    ui_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a stored generate_ui capsule with the strict artifact CSP, for the sandboxed iframe.

    Auth via `get_user_id_from_request` (accepts `?access_token=` for iframe loads). Ownership is
    re-verified against the stored entry's tags — not `ui_id` unguessability alone.
    """
    user_id = get_user_id_from_request(request)
    course = db.get(Course, course_id)
    lesson = db.get(Lesson, lesson_id)
    if not course or course.user_id != user_id or not lesson or lesson.course_id != course_id:
        raise HTTPException(404, "not found")
    html = generative_ui.get_ui_html(ui_id, user_id=user_id, lesson_id=lesson_id)
    if html is None:
        raise HTTPException(404, "not found")
    return HTMLResponse(
        content=ensure_artifact_runtime(html),
        headers={"Content-Security-Policy": artifact_csp()},
    )

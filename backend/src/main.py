from __future__ import annotations

import logging
import os
import re
import secrets
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from fastapi import Cookie, Depends, FastAPI, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import Field  # noqa: E402

from session_store import ApiModel, SessionView, SQLiteSessionStore  # noqa: E402
from tutor_service import TutorService  # noqa: E402


logging.basicConfig(level=logging.INFO)
SESSION_COOKIE = "sat_session"
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class LessonRequest(ApiModel):
    question_text: str = Field(default="", max_length=20_000)
    source_kind: str = Field(default="text", max_length=20)
    source_media_type: str = Field(default="", max_length=80)
    source_base64: str = Field(default="", max_length=6_000_000)


class ReplanRequest(ApiModel):
    student_message: str = Field(min_length=1, max_length=4_000)
    completed_beat_index: int = Field(default=0, ge=0, le=100)
    source_media_type: str = Field(default="", max_length=80)
    source_base64: str = Field(default="", max_length=6_000_000)


class CheckWorkRequest(ApiModel):
    student_work: str = Field(min_length=1, max_length=20_000)
    question_text: str = Field(default="", max_length=20_000)


class ForgetResponse(ApiModel):
    messages_erased: int


class VoiceTokenResponse(ApiModel):
    ok: bool
    access_token: str = ""
    expires_in: int = 0
    tts_model: str = ""
    message: str = ""


database_path = Path(os.environ.get("SAT_TUTOR_DB", ROOT / "backend" / "data" / "sat_tutor.db"))
if not database_path.is_absolute():
    database_path = ROOT / database_path
store = SQLiteSessionStore(
    database_path,
    daily_lesson_limit=int(os.environ.get("DAILY_LESSON_LIMIT", "40")),
    daily_check_limit=int(os.environ.get("DAILY_CHECK_LIMIT", "80")),
    burst_limit=int(os.environ.get("BURST_LIMIT", "8")),
)
service = TutorService(store)

app = FastAPI(title="SAT Live Tutor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("APP_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def browser_session(
    response: Response,
    sat_session: Annotated[str | None, Cookie()] = None,
) -> str:
    session_id = sat_session if sat_session and SESSION_PATTERN.fullmatch(sat_session) else ""
    if not session_id:
        session_id = secrets.token_urlsafe(32)
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            samesite="lax",
            secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
            max_age=60 * 60 * 24 * 365,
        )
    service.store.ensure(session_id)
    return session_id


SessionId = Annotated[str, Depends(browser_session)]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/session", response_model=SessionView)
async def get_session(session_id: SessionId) -> SessionView:
    return service.view(session_id)


@app.post("/api/lesson", response_model=SessionView)
async def start_lesson(request: LessonRequest, session_id: SessionId) -> SessionView:
    return await service.start_lesson(
        session_id,
        question_text=request.question_text,
        source_kind=request.source_kind,
        source_media_type=request.source_media_type,
        source_base64=request.source_base64,
    )


@app.post("/api/replan", response_model=SessionView)
async def replan(request: ReplanRequest, session_id: SessionId) -> SessionView:
    return await service.replan(
        session_id,
        student_message=request.student_message,
        completed_beat_index=request.completed_beat_index,
        source_media_type=request.source_media_type,
        source_base64=request.source_base64,
    )


@app.post("/api/check-work", response_model=SessionView)
async def check_work(request: CheckWorkRequest, session_id: SessionId) -> SessionView:
    return await service.check_work(
        session_id,
        student_work=request.student_work,
        question_text=request.question_text,
    )


@app.post("/api/session/reset", response_model=SessionView)
async def reset_session(session_id: SessionId) -> SessionView:
    return service.reset(session_id)


@app.delete("/api/session", response_model=ForgetResponse)
async def forget_session(session_id: SessionId) -> ForgetResponse:
    return ForgetResponse(messages_erased=service.forget(session_id))


@app.post("/api/voice-token", response_model=VoiceTokenResponse)
async def voice_token(session_id: SessionId) -> VoiceTokenResponse:
    del session_id
    return VoiceTokenResponse.model_validate(await service.voice_token())

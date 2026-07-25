"""Durable coding-lab sessions shared between widgets and lesson agents."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..core.db import SessionLocal
from ..models import CodingLabSession, Lesson

MAX_FILES = 20
MAX_FILE_CHARS = 50_000
MAX_STDOUT_CHARS = 8_000
MAX_TITLE = 200
_UNSET = object()


def _clean_files(files: Any) -> list[dict[str, str]]:
    if not isinstance(files, list):
        return []
    out: list[dict[str, str]] = []
    for item in files[:MAX_FILES]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip() or "main.txt"
        content = str(item.get("content") or "")
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]
        out.append({"path": path[:200], "content": content})
    return out


def _workspace(
    *,
    files: Any,
    last_run: Any = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(existing or {})
    base["files"] = _clean_files(files if files is not None else base.get("files"))
    if last_run is not None:
        base["last_run"] = last_run
    return base


def create_session(
    *,
    lesson_id: str,
    user_id: str,
    tool_call_id: str,
    title: str,
    language: str,
    instructions: str,
    files: Any,
    entrypoint: str | None = None,
    expected_stdout: str | None = None,
    hint: str | None = None,
) -> CodingLabSession | None:
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        if lesson is None:
            return None
        session = CodingLabSession(
            course_id=lesson.course_id,
            lesson_id=lesson_id,
            user_id=user_id,
            tool_call_id=tool_call_id,
            title=(title or "Coding Lab")[:MAX_TITLE],
            language=(language or "javascript")[:64],
            instructions=instructions or "",
            hint=hint,
            entrypoint=entrypoint,
            expected_stdout=expected_stdout,
            workspace=_workspace(files=files),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


def update_session(
    *,
    lesson_id: str,
    user_id: str,
    session_id: str | None = None,
    title: str | None = None,
    language: str | None = None,
    instructions: str | None = None,
    files: Any = None,
    entrypoint: Any = _UNSET,
    expected_stdout: Any = _UNSET,
    hint: Any = _UNSET,
) -> CodingLabSession | None:
    with SessionLocal() as db:
        session: CodingLabSession | None = None
        if session_id:
            session = db.get(CodingLabSession, session_id)
            if (
                session is None
                or session.lesson_id != lesson_id
                or session.user_id != user_id
            ):
                return None
        else:
            session = db.scalars(
                select(CodingLabSession)
                .where(
                    CodingLabSession.lesson_id == lesson_id,
                    CodingLabSession.user_id == user_id,
                )
                .order_by(
                    CodingLabSession.created_at.desc(),
                    CodingLabSession.id.desc(),
                )
                .limit(1)
            ).first()
            if session is None:
                return None

        if title is not None:
            session.title = title[:MAX_TITLE]
        if language is not None:
            session.language = language[:64]
        if instructions is not None:
            session.instructions = instructions
        if hint is not _UNSET:
            session.hint = None if hint is None else str(hint)
        if entrypoint is not _UNSET:
            session.entrypoint = None if entrypoint is None else str(entrypoint)
        if expected_stdout is not _UNSET:
            session.expected_stdout = None if expected_stdout is None else str(expected_stdout)
        session.workspace = _workspace(
            files=files if files is not None else (session.workspace or {}).get("files"),
            last_run=(session.workspace or {}).get("last_run"),
            existing=session.workspace if isinstance(session.workspace, dict) else None,
        )
        session.revision += 1
        db.commit()
        db.refresh(session)
        return session


def update_session_from_tool_args(
    *, lesson_id: str, user_id: str, args: dict[str, Any]
) -> CodingLabSession | None:
    """Apply an update tool payload while preserving omitted nullable fields.

    JSON null explicitly clears a hint/entrypoint/check. A missing key leaves the
    current value untouched, which cannot be represented with ``dict.get`` alone.
    """
    kwargs: dict[str, Any] = {}
    for key in ("title", "language", "instructions"):
        value = args.get(key)
        if value is not None:
            kwargs[key] = value
    if isinstance(args.get("files"), list):
        kwargs["files"] = args["files"]
    for source, target in (
        ("entrypoint", "entrypoint"),
        ("expectedStdout", "expected_stdout"),
        ("hint", "hint"),
    ):
        if source in args:
            kwargs[target] = args[source]
    return update_session(
        lesson_id=lesson_id,
        user_id=user_id,
        session_id=args.get("coding_lab_session_id"),
        **kwargs,
    )


def sync_files(
    *, session_id: str, lesson_id: str, user_id: str, files: Any
) -> CodingLabSession | None:
    with SessionLocal() as db:
        session = db.get(CodingLabSession, session_id)
        if session is None or session.lesson_id != lesson_id or session.user_id != user_id:
            return None
        existing = session.workspace if isinstance(session.workspace, dict) else {}
        session.workspace = _workspace(
            files=files,
            last_run=existing.get("last_run"),
            existing=existing,
        )
        session.revision += 1
        db.commit()
        db.refresh(session)
        return session


def record_run(
    *,
    session_id: str,
    lesson_id: str,
    user_id: str,
    run: dict[str, Any],
    files: Any = None,
) -> CodingLabSession | None:
    with SessionLocal() as db:
        session = db.get(CodingLabSession, session_id)
        if session is None or session.lesson_id != lesson_id or session.user_id != user_id:
            return None
        existing = session.workspace if isinstance(session.workspace, dict) else {}
        cleaned_run = {
            "ok": bool(run.get("ok")),
            "passed": run.get("passed"),
            "stdout": str(run.get("stdout") or "")[:MAX_STDOUT_CHARS],
            "stderr": str(run.get("stderr") or "")[:MAX_STDOUT_CHARS],
            "language": str(run.get("language") or session.language)[:64],
            "event": str(run.get("event") or "CODING_LAB_RUN_RESULT")[:64],
        }
        session.workspace = _workspace(
            files=files if files is not None else existing.get("files"),
            last_run=cleaned_run,
            existing=existing,
        )
        session.revision += 1
        db.commit()
        db.refresh(session)
        return session


def latest_context(*, lesson_id: str, user_id: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        session = db.scalars(
            select(CodingLabSession)
            .where(
                CodingLabSession.lesson_id == lesson_id,
                CodingLabSession.user_id == user_id,
            )
            .order_by(
                CodingLabSession.created_at.desc(),
                CodingLabSession.id.desc(),
            )
            .limit(1)
        ).first()
        return session_context(session) if session else None


def session_context(session: CodingLabSession) -> dict[str, Any]:
    workspace = session.workspace if isinstance(session.workspace, dict) else {}
    return {
        "session_id": session.id,
        "coding_lab_session_id": session.id,
        "tool_call_id": session.tool_call_id,
        "revision": session.revision,
        "title": session.title,
        "language": session.language,
        "instructions": session.instructions,
        "hint": session.hint,
        "entrypoint": session.entrypoint,
        "expectedStdout": session.expected_stdout,
        "files": workspace.get("files") or [],
        "last_run": workspace.get("last_run"),
    }


def tool_args_from_session(session: CodingLabSession) -> dict[str, Any]:
    """Arguments shape expected by the frontend CodingLab widget."""
    ctx = session_context(session)
    return {
        "title": ctx["title"],
        "language": ctx["language"],
        "instructions": ctx["instructions"],
        "files": ctx["files"],
        "entrypoint": ctx.get("entrypoint"),
        "expectedStdout": ctx.get("expectedStdout"),
        "hint": ctx.get("hint"),
        "coding_lab_session_id": session.id,
    }

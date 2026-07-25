"""Coding lab session service + tool schema smoke tests."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Course, Lesson  # noqa: F401 — register CodingLabSession via models package
from app.services import coding_lab_service
from app.tutor.tools import TOOL_DEFS
from app.tutor.tools.widgets import ShowCodingLabTool, UpdateCodingLabTool


def test_tool_defs_include_coding_lab():
    names = {name for name, _, _ in TOOL_DEFS}
    assert "show_coding_lab" in names
    assert "update_coding_lab" in names


def test_show_coding_lab_schema_accepts_files():
    tool = ShowCodingLabTool(
        title="Hello",
        language="javascript",
        instructions="Print hello",
        files=[{"path": "main.js", "content": "console.log('hello');"}],
        expectedStdout="hello",
    )
    assert tool.files[0].path == "main.js"
    assert tool.expectedStdout == "hello"


def test_update_coding_lab_tool_optional_fields():
    tool = UpdateCodingLabTool(instructions="Try again", hint="Remember semicolons")
    assert tool.files is None
    assert tool.instructions == "Try again"


def test_create_sync_run_and_update(monkeypatch, tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'coding-lab.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(coding_lab_service, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="course", user_id="user", topic="JS"))
        db.add(Lesson(id="lesson", course_id="course", title="Basics"))
        db.commit()

    created = coding_lab_service.create_session(
        lesson_id="lesson",
        user_id="user",
        tool_call_id="tc_lab_1",
        title="Hello JS",
        language="javascript",
        instructions="Print hello",
        files=[{"path": "main.js", "content": "console.log('hello');"}],
        expected_stdout="hello",
        hint="Use console.log",
    )
    assert created is not None
    ctx = coding_lab_service.session_context(created)
    assert ctx["coding_lab_session_id"] == created.id
    assert ctx["files"][0]["path"] == "main.js"

    synced = coding_lab_service.sync_files(
        session_id=created.id,
        lesson_id="lesson",
        user_id="user",
        files=[{"path": "main.js", "content": "console.log('hi');"}],
    )
    assert synced is not None
    assert synced.revision == 1

    ran = coding_lab_service.record_run(
        session_id=created.id,
        lesson_id="lesson",
        user_id="user",
        run={
            "ok": True,
            "passed": True,
            "stdout": "hi",
            "stderr": "",
            "language": "javascript",
            "event": "CODING_LAB_CHECK_RESULT",
        },
    )
    assert ran is not None
    latest = coding_lab_service.latest_context(lesson_id="lesson", user_id="user")
    assert latest is not None
    assert latest["last_run"]["passed"] is True
    assert latest["last_run"]["event"] == "CODING_LAB_CHECK_RESULT"

    updated = coding_lab_service.update_session(
        lesson_id="lesson",
        user_id="user",
        title="v2",
        instructions="new goal",
        files=[{"path": "main.js", "content": "console.log(2);"}],
        expected_stdout="2",
    )
    assert updated is not None
    args = coding_lab_service.tool_args_from_session(updated)
    assert args["title"] == "v2"
    assert args["expectedStdout"] == "2"

    cleared = coding_lab_service.update_session(
        lesson_id="lesson",
        user_id="user",
        entrypoint=None,
        expected_stdout=None,
        hint=None,
    )
    assert cleared is not None
    cleared_args = coding_lab_service.tool_args_from_session(cleared)
    assert cleared_args["entrypoint"] is None
    assert cleared_args["expectedStdout"] is None
    assert cleared_args["hint"] is None


def test_tool_update_distinguishes_omitted_from_explicit_null(monkeypatch, tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'coding-lab-clear.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(coding_lab_service, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="course", user_id="user", topic="JS"))
        db.add(Lesson(id="lesson", course_id="course", title="Basics"))
        db.commit()

    created = coding_lab_service.create_session(
        lesson_id="lesson",
        user_id="user",
        tool_call_id="tc_lab_clear",
        title="Checked exercise",
        language="javascript",
        instructions="Print hello",
        files=[{"path": "main.js", "content": "console.log('hello');"}],
        entrypoint="main.js",
        expected_stdout="hello",
        hint="Use console.log",
    )
    assert created is not None

    preserved = coding_lab_service.update_session_from_tool_args(
        lesson_id="lesson",
        user_id="user",
        args={"coding_lab_session_id": created.id, "instructions": "Try another approach"},
    )
    assert preserved is not None
    assert preserved.entrypoint == "main.js"
    assert preserved.expected_stdout == "hello"
    assert preserved.hint == "Use console.log"

    cleared = coding_lab_service.update_session_from_tool_args(
        lesson_id="lesson",
        user_id="user",
        args={
            "coding_lab_session_id": created.id,
            "entrypoint": None,
            "expectedStdout": None,
            "hint": None,
        },
    )
    assert cleared is not None
    assert cleared.entrypoint is None
    assert cleared.expected_stdout is None
    assert cleared.hint is None

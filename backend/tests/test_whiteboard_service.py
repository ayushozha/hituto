from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Course, Lesson
from app.services import whiteboard_service


def test_whiteboard_session_persists_and_reloads(monkeypatch, tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(whiteboard_service, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="course", user_id="user", topic="Watches"))
        db.add(Lesson(id="lesson", course_id="course", title="Escapement"))
        db.commit()

    created = whiteboard_service.create_session(
        lesson_id="lesson",
        user_id="user",
        tool_call_id="tc_board",
        title="Board",
        intent="Test rectangle",
        elements=[{"id": "rect", "type": "rectangle"}],
    )
    assert created is not None
    assert created.revision == 0

    updated = whiteboard_service.sync_session(
        session_id=created.id,
        lesson_id="lesson",
        user_id="user",
        elements=[
            {"id": "rect", "type": "rectangle", "boundElements": [{"id": "label"}]},
            {"id": "label", "type": "text", "text": "PERSISTED", "containerId": "rect"},
        ],
    )
    assert updated is not None
    assert updated.revision == 1

    context = whiteboard_service.latest_context(lesson_id="lesson", user_id="user")
    assert context is not None
    assert context["session_id"] == created.id
    assert context["elements"][1]["text"] == "PERSISTED"


def test_latest_context_prefers_newest_created_board(monkeypatch, tmp_path) -> None:
    """A recently synced older board must not beat a newer show_whiteboard session."""
    from datetime import datetime, timedelta, timezone

    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard-order.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(whiteboard_service, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="course", user_id="user", topic="Watches"))
        db.add(Lesson(id="lesson", course_id="course", title="Escapement"))
        db.commit()

    older = whiteboard_service.create_session(
        lesson_id="lesson",
        user_id="user",
        tool_call_id="tc_old",
        title="Older board",
        intent="old",
        elements=[{"id": "old", "type": "text", "text": "OLD"}],
    )
    newer = whiteboard_service.create_session(
        lesson_id="lesson",
        user_id="user",
        tool_call_id="tc_new",
        title="Newer board",
        intent="new",
        elements=[{"id": "new", "type": "text", "text": "NEW"}],
    )
    assert older is not None and newer is not None

    # Simulate the older board being edited after the newer one was created.
    with session_factory() as db:
        from app.models import WhiteboardSession

        old_row = db.get(WhiteboardSession, older.id)
        new_row = db.get(WhiteboardSession, newer.id)
        assert old_row is not None and new_row is not None
        base = datetime.now(timezone.utc)
        old_row.created_at = base - timedelta(minutes=5)
        old_row.updated_at = base + timedelta(minutes=1)  # more recent sync
        new_row.created_at = base
        new_row.updated_at = base  # older than old_row.updated_at
        db.commit()

    context = whiteboard_service.latest_context(lesson_id="lesson", user_id="user")
    assert context is not None
    assert context["session_id"] == newer.id
    assert context["elements"][0]["text"] == "NEW"

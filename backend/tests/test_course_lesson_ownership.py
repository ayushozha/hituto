import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1 import courses
from app.core.db import Base
from app.models import Course, Lesson
from app.schemas.course import RefinementRequest


@pytest.fixture
def mismatched_course_and_lesson(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lesson-ownership.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        db.add_all(
            [
                Course(id="owned-course", user_id="alice", topic="Owned", status="ready"),
                Course(id="foreign-course", user_id="bob", topic="Private", status="ready"),
                Lesson(
                    id="owned-lesson",
                    course_id="owned-course",
                    title="Owned lesson",
                    status="ready",
                ),
                Lesson(
                    id="foreign-lesson",
                    course_id="foreign-course",
                    title="Private lesson",
                    status="ready",
                ),
            ]
        )
        db.commit()
        yield db


def _assert_lesson_not_found(exc: pytest.ExceptionInfo[HTTPException]) -> None:
    assert exc.value.status_code == 404
    assert exc.value.detail == "lesson not found"


def test_source_pack_rejects_lesson_from_another_course(
    mismatched_course_and_lesson, monkeypatch
) -> None:
    monkeypatch.setattr(
        courses.course_service,
        "lesson_source_pack",
        lambda *_args, **_kwargs: pytest.fail("foreign lesson reached the service"),
    )

    with pytest.raises(HTTPException) as exc:
        courses.get_lesson_source_pack(
            course_id="owned-course",
            lesson_id="foreign-lesson",
            db=mismatched_course_and_lesson,
            user_id="alice",
        )

    _assert_lesson_not_found(exc)


async def test_refinement_rejects_lesson_from_another_course(
    mismatched_course_and_lesson, monkeypatch
) -> None:
    monkeypatch.setattr(
        courses.course_service,
        "start_generation",
        lambda *_args, **_kwargs: pytest.fail("foreign lesson reached generation"),
    )

    with pytest.raises(HTTPException) as exc:
        await courses.refine_course(
            course_id="owned-course",
            body=RefinementRequest(prompt="Make this clearer", lesson_id="foreign-lesson"),
            db=mismatched_course_and_lesson,
            user_id="alice",
        )

    _assert_lesson_not_found(exc)


def test_versions_rejects_lesson_from_another_course(
    mismatched_course_and_lesson, monkeypatch
) -> None:
    monkeypatch.setattr(
        courses.course_service,
        "artifact_versions",
        lambda *_args, **_kwargs: pytest.fail("foreign lesson reached the service"),
    )

    with pytest.raises(HTTPException) as exc:
        courses.versions(
            course_id="owned-course",
            lesson_id="foreign-lesson",
            db=mismatched_course_and_lesson,
            user_id="alice",
        )

    _assert_lesson_not_found(exc)

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Course, Lesson, LessonSourcePack, SourceDocument
from app.services import course_service


@pytest.mark.parametrize("design_mode", ["studio", "page", "slide"])
def test_append_chapter_inherits_course_design_mode(
    design_mode, monkeypatch, tmp_path
):
    engine = create_engine(f"sqlite:///{tmp_path / f'{design_mode}-chapter.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    started: list[str] = []

    def record_generation(_db, _course, lesson, **_kwargs):
        started.append(lesson.id)
        lesson.status = "generating"
        _db.commit()
        return True

    monkeypatch.setattr(course_service, "start_generation", record_generation)

    with session_factory() as db:
        course = Course(
            id=f"{design_mode}-course",
            user_id="dev",
            topic="How systems learn",
            title="How systems learn",
            status="ready",
            knobs={"design_mode": design_mode, "difficulty": "intermediate"},
        )
        first = Lesson(
            id=f"{design_mode}-lesson-one",
            course_id=course.id,
            ordinal=0,
            title="The first idea",
            objective="Understand the starting point.",
            completed=True,
            status="ready",
        )
        db.add_all([course, first])
        db.commit()

        lesson = course_service.append_chapter(
            db,
            course,
            title="Put the idea into practice",
            description="Apply the core idea to a realistic worked example.",
            archetype="explainer",
        )

        assert lesson.ordinal == 1
        assert lesson.module_ordinal is None
        assert lesson.module_title is None
        assert lesson.objective == "Apply the core idea to a realistic worked example."
        assert lesson.status == "generating"
        assert started == [lesson.id]
        assert course.knobs["design_mode"] == design_mode
        assert course_service.detail(db, course).design_mode == design_mode


def test_append_chapter_keeps_source_grounding(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source-chapter.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(course_service, "start_generation", lambda *_args, **_kwargs: True)

    with session_factory() as db:
        source = SourceDocument(
            id="source-one",
            user_id="dev",
            filename="guide.pdf",
            title="System guide",
            source_type="textbook",
            status="ready",
        )
        course = Course(
            id="source-course",
            user_id="dev",
            topic="System guide",
            title="System guide",
            status="ready",
            knobs={"design_mode": "page", "source_document_id": source.id},
        )
        first = Lesson(
            id="source-lesson-one",
            course_id=course.id,
            ordinal=0,
            title="First chapter",
            objective="Read the first chapter.",
            status="ready",
            module_ordinal=0,
            module_title="Chapter 1: First chapter",
        )
        db.add_all([source, course, first])
        db.commit()

        lesson = course_service.append_chapter(
            db,
            course,
            title="New grounded chapter",
            description="Connect the source material to a worked example.",
        )

        assert lesson.module_ordinal == 1
        assert lesson.module_title == "Chapter 2: New grounded chapter"
        pack = db.scalars(
            select(LessonSourcePack).where(LessonSourcePack.lesson_id == lesson.id)
        ).one()
        assert pack.source_document_id == source.id
        assert pack.retrieval_query.startswith("New grounded chapter.")


def test_generic_chapter_flow_rejects_video_course(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'video-chapter.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        course = Course(
            id="video-course",
            user_id="dev",
            topic="Video course",
            status="ready",
            knobs={"design_mode": "page", "video_sync": True},
        )
        db.add(course)
        db.commit()

        with pytest.raises(ValueError, match="video chapter flow"):
            course_service.append_chapter(
                db,
                course,
                title="Another video",
                description="Use the synchronized video flow.",
            )

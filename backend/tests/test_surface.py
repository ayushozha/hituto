"""Lesson surface protocol (specs/design_agents §6) — per-kind digests + capabilities.

Includes the regression the module exists for: A2UI artifacts store ``html=""`` so the
old HTML-only digest grounded the voice tutor on an empty string.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Artifact, Course, Lesson, SourceDocument
from app.surface import build_surface
from app.voice import grounding


def _db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'surface.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed(db, *, course_knobs=None):
    course = Course(id="c1", user_id="u1", topic="Gears", knobs=course_knobs or {})
    lesson = Lesson(id="l1", course_id="c1", ordinal=0, title="Gear ratios")
    db.add_all([course, lesson])
    db.commit()
    return course, lesson


A2UI_DOC = {
    "title": "Gear ratios",
    "intent": "quiz",
    "root": {
        "type": "column",
        "children": [
            {"type": "text", "props": {"text": "A gear ratio compares tooth counts."}},
            {
                "type": "quiz",
                "props": {
                    "question": "What does a 2:1 ratio mean?",
                    "options": ["Twice the torque", "Half the teeth"],
                },
            },
        ],
    },
}


def test_a2ui_artifact_grounds_with_a_real_digest(tmp_path) -> None:
    factory = _db(tmp_path)
    with factory() as db:
        course, lesson = _seed(db)
        db.add(Artifact(lesson_id="l1", version=1, kind="a2ui", html="", a2ui=A2UI_DOC))
        db.commit()
        surface = build_surface(db, course, lesson)
    assert surface.kind == "a2ui"
    assert "gear ratio compares tooth counts" in surface.digest.lower()
    assert "2:1" in surface.digest
    assert surface.capabilities.page_control is False


def test_html_capsule_surface_has_outline_and_page_control(tmp_path) -> None:
    factory = _db(tmp_path)
    html = (
        "<html><body>"
        '<section id="s-a" data-lesson-section="intro" data-lesson-title="Intro">Hello gears</section>'
        '<section data-lesson-section="ratios">Ratios body</section>'
        "</body></html>"
    )
    with factory() as db:
        course, lesson = _seed(db)
        db.add(Artifact(lesson_id="l1", version=3, kind="html", html=html, checks={"passed": True}))
        db.commit()
        surface = build_surface(db, course, lesson)
    assert surface.kind == "capsule"
    assert surface.artifact_version == 3
    assert [(s.id, s.title) for s in surface.outline] == [("intro", "Intro"), ("ratios", "")]
    assert surface.capabilities.page_control is True
    assert surface.capabilities.sections is True
    assert "Hello gears" in surface.digest


def test_studio_checks_resolve_studio_kind(tmp_path) -> None:
    factory = _db(tmp_path)
    with factory() as db:
        course, lesson = _seed(db)
        db.add(
            Artifact(
                lesson_id="l1",
                version=1,
                kind="html",
                html="<html><body>specimen</body></html>",
                checks={"presentation": "studio"},
            )
        )
        db.commit()
        assert build_surface(db, course, lesson).kind == "studio"


def test_video_source_yields_seekable_surface_with_checkpoint_digest(tmp_path) -> None:
    factory = _db(tmp_path)
    with factory() as db:
        db.add(
            SourceDocument(
                id="src1",
                user_id="u1",
                filename="gears.mp4",
                source_type="video",
                source_map={
                    "video": {
                        "duration_seconds": 90,
                        "checkpoints": [
                            {"title": "Why gears exist", "prompt": "Watch the chain path"}
                        ],
                    }
                },
            )
        )
        course, lesson = _seed(db, course_knobs={"source_document_id": "src1"})
        surface = build_surface(db, course, lesson)
    assert surface.kind == "video"
    assert surface.capabilities.seek is True
    assert surface.capabilities.page_control is False
    assert "Why gears exist" in surface.digest


def test_bare_lesson_yields_empty_capsule_surface(tmp_path) -> None:
    factory = _db(tmp_path)
    with factory() as db:
        course, lesson = _seed(db)
        surface = build_surface(db, course, lesson)
    assert surface.kind == "capsule"
    assert surface.digest == ""
    assert surface.capabilities.page_control is False


def test_voice_grounding_now_digests_a2ui_lessons(monkeypatch, tmp_path) -> None:
    factory = _db(tmp_path)
    with factory() as db:
        _seed(db)
        db.add(Artifact(lesson_id="l1", version=1, kind="a2ui", html="", a2ui=A2UI_DOC))
        db.commit()
    monkeypatch.setattr(grounding, "SessionLocal", factory)
    ctx = grounding.load_lesson_context("c1", "l1")
    assert ctx is not None
    # The bug this module fixes: this digest used to be "" for A2UI lessons.
    assert "2:1" in ctx["artifact_digest"]
    assert ctx["surface_kind"] == "a2ui"
    assert ctx["surface_capabilities"]["whiteboard"] is True

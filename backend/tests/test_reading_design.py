"""Reading design agent (specs/design_agents step 4): routing, authoring, surfaces."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.db import Base
from app.coursegen import graph
from app.coursegen.designs.base import AuthorContext
from app.coursegen.designs.reading import (
    ReadingAgent,
    ReadingAnnotations,
    validate_reading_doc,
)
from app.coursegen.presentation import resolve_presentation
from app.models import Artifact, Course, Lesson
from app.surface import build_surface

PACK = [
    {
        "id": "ch1",
        "chapter_id": "chap-one",
        "section_title": "The Lever",
        "text": "A lever amplifies force.\n\nArchimedes described this trade-off in detail.",
    },
    {"id": "ch2", "section_title": "The Wheel", "text": "Wheels reduce friction dramatically."},
]


@pytest.fixture
def reading_enabled(monkeypatch):
    monkeypatch.setenv("READING_DESIGN_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_routing_is_flag_gated_and_fails_closed(monkeypatch) -> None:
    plan = {"title": "Machines", "archetype": "explainer", "source_pack": PACK}
    # Flag off: explicit and auto both resolve to page.
    monkeypatch.setenv("READING_DESIGN_ENABLED", "0")
    get_settings.cache_clear()
    try:
        assert resolve_presentation(plan, {"design_mode": "reading"}) == "page"
        assert resolve_presentation(plan, {}) == "page"
    finally:
        get_settings.cache_clear()


def test_routing_picks_reading_for_grounded_prose(reading_enabled) -> None:
    plan = {"title": "Machines", "archetype": "explainer", "source_pack": PACK}
    assert resolve_presentation(plan, {}) == "reading"
    assert resolve_presentation(plan, {"design_mode": "reading"}) == "reading"
    # No source pack → nothing to read, even explicitly.
    assert resolve_presentation({"title": "Machines"}, {"design_mode": "reading"}) == "page"
    # Simulations keep their app-like designs.
    assert (
        resolve_presentation(
            {"title": "Machines", "archetype": "simulation", "source_pack": PACK}, {}
        )
        == "page"
    )


class _FakePlannerLLM:
    async def generate_json(self, system: str, user: str, schema):
        assert "chap-one" in user  # annotator sees the real section ids
        return ReadingAnnotations.model_validate(
            {
                "intent": "See how simple machines trade force for distance.",
                "sections": [
                    {
                        "id": "chap-one",
                        "objective": "Explain mechanical advantage",
                        "notes": ["Archimedes: give me a place to stand."],
                        "check_question": "What does a lever amplify?",
                        "check_answer": "Force, at the cost of distance.",
                    }
                ],
                "glossary": [{"term": "lever", "definition": "a rigid beam on a fulcrum"}],
            }
        )


async def test_reading_agent_annotates_verbatim_prose(monkeypatch) -> None:
    import app.providers.registry as registry

    monkeypatch.setattr(registry, "get_coursegen_planner_llm", lambda: _FakePlannerLLM())
    ctx = AuthorContext(
        course_id="c1",
        lesson_id="l1",
        attempt=1,
        plan={"title": "Machines", "subtitle": "how they work", "source_pack": PACK},
        knobs={},
        state={},
        llm=None,
    )
    out = await ReadingAgent().author(ctx)
    assert out.kind == "reading"
    doc = out.a2ui
    assert doc["title"] == "Machines"
    # Source prose is verbatim — the model never rewrites it.
    assert doc["sections"][0]["body_md"].startswith("A lever amplifies force.")
    assert doc["sections"][0]["objective"] == "Explain mechanical advantage"
    assert doc["sections"][0]["check"]["question"] == "What does a lever amplify?"
    assert doc["sections"][1]["notes"] == []  # unannotated section still ships
    assert doc["glossary"][0]["term"] == "lever"
    assert validate_reading_doc(doc) is not None


async def test_reading_agent_without_sources_delegates_to_page(monkeypatch) -> None:
    from app.coursegen.designs import page as page_module

    async def fake_page_author(self, ctx):
        return "PAGE-FALLBACK"

    monkeypatch.setattr(page_module.PageAgent, "author", fake_page_author)
    ctx = AuthorContext(
        course_id="c1", lesson_id="l1", attempt=1, plan={"title": "X"}, knobs={}, state={}, llm=None
    )
    assert await ReadingAgent().author(ctx) == "PAGE-FALLBACK"


async def test_post_process_validates_reading_docs() -> None:
    good = {
        "title": "Machines",
        "sections": [{"id": "a", "title": "A", "body_md": "prose"}],
    }
    out = await graph.post_process(
        {"course_id": "c1", "artifact_kind": "reading", "a2ui": good}
    )
    assert out["checks"]["passed"] is True
    assert out["artifact_kind"] == "reading"

    bad = await graph.post_process(
        {"course_id": "c1", "artifact_kind": "reading", "a2ui": {"nope": True}}
    )
    assert bad["checks"]["passed"] is False


def test_surface_for_reading_artifact(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reading.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    doc = {
        "kind": "reading",
        "title": "Machines",
        "intent": "trade force for distance",
        "sections": [
            {
                "id": "chap-one",
                "title": "The Lever",
                "objective": "Explain mechanical advantage",
                "body_md": "A lever amplifies force.",
                "notes": [{"anchor": "", "text": "Archimedes said so."}],
                "check": None,
            }
        ],
        "glossary": [],
    }
    with factory() as db:
        db.add(Course(id="c1", user_id="u1", topic="Machines", knobs={}))
        lesson = Lesson(id="l1", course_id="c1", ordinal=0, title="Machines")
        db.add(lesson)
        db.add(Artifact(lesson_id="l1", version=1, kind="reading", html="", a2ui=doc))
        db.commit()
        course = db.get(Course, "c1")
        surface = build_surface(db, course, lesson)
    assert surface.kind == "reading"
    assert "lever amplifies force" in surface.digest.lower()
    assert [s.id for s in surface.outline] == ["chap-one"]
    assert surface.capabilities.page_control is False
    assert surface.capabilities.sections is True

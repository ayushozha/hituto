"""fast_gen Phase 2: plan ∥ research fan-out in interpret + research short-circuit."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.core.progress import broker
from app.coursegen import graph
from app.models import Course, Lesson


class _FakeSearch:
    async def search(self, q: str, n: int = 4):
        return [{"url": "https://example.com/gears", "title": q, "text": f"About {q}"}]


async def test_parallel_interpret_merges_research_and_emits_skeleton(
    monkeypatch, tmp_path
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'gen.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(graph, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="c1", user_id="u1", topic="Gears", knobs={}))
        db.add(
            Lesson(
                id="l1",
                course_id="c1",
                ordinal=0,
                title="Gear ratios",
                objective="Understand ratios",
                archetype="explainer",
            )
        )
        db.commit()

    async def fake_plan(**kwargs):
        return {
            "title": kwargs["lesson_title"],
            "subtitle": kwargs["objective"],
            "archetype": kwargs["archetype"],
            "sections": [{"id": "s1", "icon": "school", "title": "Intro"}],
            "facts": [],
        }

    monkeypatch.setattr(graph, "build_lesson_plan", fake_plan)
    monkeypatch.setattr(graph, "get_search", lambda: _FakeSearch())

    q = broker.subscribe("c1")
    try:
        out = await graph.interpret(
            {"course_id": "c1", "lesson_id": "l1", "topic": "Gears", "knobs": {}}
        )
        events = []
        while not q.empty():
            events.append(q.get_nowait())
    finally:
        broker.unsubscribe("c1", q)

    # Research ran concurrently with planning and merged into the plan/state.
    assert out["research_done"] is True
    assert out["plan"]["facts"][0]["source_url"] == "https://example.com/gears"
    assert out["citations"][0]["source_url"] == "https://example.com/gears"

    # The skeleton frame carried the section outline for the shell iframe.
    skeleton = next(e for e in events if e.stage == "skeleton")
    assert skeleton.data["lesson_id"] == "l1"
    assert skeleton.data["sections"] == [{"id": "s1", "icon": "school", "title": "Intro"}]

    # The research node is a no-op for states interpret already researched.
    assert await graph.research({**out, "course_id": "c1", "lesson_id": "l1"}) == {}

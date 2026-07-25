"""fast_gen Phase 3: background mesh jobs — generate-time join and studio late-join."""
import asyncio
import importlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.coursegen.agents.roles as roles
import app.coursegen.studio_manifest as studio_manifest
import app.coursegen.studio_renderer as studio_renderer
from app.core.db import Base
from app.core.progress import broker
from app.coursegen import assets
from app.models import Artifact, Course, Lesson

# `app.capsule.__init__` re-exports the postprocess *function*, shadowing the submodule
# attribute — resolve the module itself for monkeypatching.
capsule_postprocess = importlib.import_module("app.capsule.postprocess")

_CATALOG = [{"path": "/build/mesh/beetle.glb", "cache_key": "k1beetle"}]


async def test_take_ready_consumes_a_finished_mesh_exactly_once(monkeypatch) -> None:
    async def fast_mesh(**kwargs):
        return None, list(_CATALOG)

    monkeypatch.setattr(roles, "run_mesh_stage", fast_mesh)
    monkeypatch.setattr(assets, "_POLL_S", 0.01)
    monkeypatch.setattr(assets, "_LATE_JOIN_WAIT_S", 0.2)

    assets.start_mesh_job(
        course_id="c1",
        lesson_id="l-take",
        concept="Beetle anatomy",
        archetype="explainer",
        knobs={},
        specialist_name=None,
        topic="Beetles",
    )
    task = assets._jobs["l-take"].task
    for _ in range(100):
        if assets._jobs["l-take"].done:
            break
        await asyncio.sleep(0.01)

    ready = assets.take_ready("l-take")
    assert ready == (None, _CATALOG)
    assert assets.take_ready("l-take") is None  # single-consume
    assert assets.awaiting_join("l-take") is False
    await task  # job exits promptly once merged and cleans up its registry entry
    assert "l-take" not in assets._jobs


class _FakeManifest:
    mode = "specimen"

    def model_dump(self):
        return {"schema_version": "2.0", "mode": "specimen"}


async def test_slow_mesh_late_joins_a_new_studio_artifact_version(
    monkeypatch, tmp_path
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'assets.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(assets, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(Course(id="c2", user_id="u1", topic="Beetles", knobs={}))
        db.add(Lesson(id="l-late", course_id="c2", ordinal=0, title="Beetle anatomy"))
        db.add(
            Artifact(
                lesson_id="l-late",
                version=1,
                kind="html",
                html="<html>fallback</html>",
                checks={"passed": True, "presentation": "studio", "mesh_pending": True},
            )
        )
        db.commit()

    gate = asyncio.Event()

    async def slow_mesh(**kwargs):
        await gate.wait()
        return None, list(_CATALOG)

    monkeypatch.setattr(roles, "run_mesh_stage", slow_mesh)
    monkeypatch.setattr(assets, "_POLL_S", 0.01)
    monkeypatch.setattr(assets, "_LATE_JOIN_WAIT_S", 2.0)
    monkeypatch.setattr(
        studio_manifest, "build_studio_manifest", lambda plan, knobs: _FakeManifest()
    )
    monkeypatch.setattr(
        studio_renderer,
        "render_studio_manifest",
        lambda manifest: "<html><body>studio /build/mesh/beetle.glb</body></html>",
    )
    monkeypatch.setattr(
        capsule_postprocess, "postprocess", lambda html: (html, {"passed": True, "failed": []})
    )

    q = broker.subscribe("c2")
    try:
        assets.start_mesh_job(
            course_id="c2",
            lesson_id="l-late",
            concept="Beetle anatomy",
            archetype="explainer",
            knobs={"design_mode": "studio"},
            specialist_name=None,
            topic="Beetles",
        )
        task = assets._jobs["l-late"].task
        await asyncio.sleep(0)  # let the job start and block on the gate

        # v1 already persisted with the fallback → persist authorizes the late-join.
        assert assets.awaiting_join("l-late") is True
        assets.enable_late_join(
            "l-late",
            course_id="c2",
            plan={"title": "Beetle anatomy", "studio_mode": "specimen", "mesh_fallback": True},
            knobs={"design_mode": "studio"},
        )
        gate.set()
        await task

        events = []
        while not q.empty():
            events.append(q.get_nowait())
    finally:
        broker.unsubscribe("c2", q)

    with session_factory() as db:
        latest = db.scalars(
            select(Artifact)
            .where(Artifact.lesson_id == "l-late")
            .order_by(Artifact.version.desc())
            .limit(1)
        ).first()
    assert latest.version == 2  # new version, v1 never overwritten
    assert latest.checks["mesh_late_join"] is True
    # Catalog scratch path rewritten to the served mesh URL by the real inliner.
    assert "/mesh?key=k1beetle" in latest.html

    mesh_ready = next(e for e in events if e.stage == "mesh_ready")
    assert mesh_ready.data == {"lesson_id": "l-late", "version": 2}
    assert "l-late" not in assets._jobs

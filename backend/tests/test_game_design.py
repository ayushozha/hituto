"""GameManifest design: routing, build/render, fail-closed agent."""
from __future__ import annotations

from app.capsule.postprocess import postprocess
from app.core.config import get_settings
from app.coursegen.designs.base import AuthorContext
from app.coursegen.designs.game import GameAgent
from app.coursegen.game_manifest import build_game_manifest, prepare_game_plan
from app.coursegen.game_renderer import game_artifact_metadata, render_game_manifest
from app.coursegen.presentation import resolve_presentation
import pytest


@pytest.fixture
def game_enabled(monkeypatch):
    monkeypatch.setenv("GAME_DESIGN_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_routing_is_flag_gated_and_fails_closed(monkeypatch) -> None:
    plan = {"title": "Call Stack Museum", "archetype": "game"}
    monkeypatch.setenv("GAME_DESIGN_ENABLED", "0")
    get_settings.cache_clear()
    try:
        assert resolve_presentation(plan, {"design_mode": "game"}) == "page"
        assert resolve_presentation(plan, {}) == "page"
    finally:
        get_settings.cache_clear()


def test_routing_picks_game_for_archetype(game_enabled) -> None:
    plan = {"title": "Call Stack Museum", "archetype": "game"}
    assert resolve_presentation(plan, {}) == "game"
    assert resolve_presentation(plan, {"design_mode": "game"}) == "game"
    # Explicit page still wins over archetype.
    assert resolve_presentation(plan, {"design_mode": "page"}) == "page"
    # Game beats studio needs_3d when archetype is game.
    assert resolve_presentation({**plan, "needs_3d": True}, {}) == "game"


def test_prepare_and_build_manifest_from_sections() -> None:
    plan = prepare_game_plan(
        {
            "title": "Recursion Galleries",
            "objective": "Visit every room in the museum.",
            "sections": [
                {"title": "Base case", "objective": "What stops the recursion?"},
                {"title": "Recursive step", "objective": "What smaller problem?"},
                {"title": "Unwinding", "objective": "What happens on the way back?"},
            ],
        }
    )
    assert plan["presentation"] == "game"
    assert plan["game_mode"] == "toon-gallery"
    manifest = build_game_manifest(plan)
    assert manifest.mode == "toon-gallery"
    assert len(manifest.stations) == 3
    assert manifest.stations[0].src.startswith("/game-kits/toon/")
    assert manifest.stations[0].character == "soldier"
    assert all(s.src.endswith(".gltf") for s in manifest.stations)


def test_stack_builder_from_call_stack_topic() -> None:
    plan = prepare_game_plan(
        {"title": "Call Stack Kitchen", "objective": "Learn push and pop."},
        {"game_mode": "stack-builder"},
    )
    assert plan["game_mode"] == "stack-builder"
    manifest = build_game_manifest(plan, {"game_mode": "stack-builder"})
    assert manifest.mode == "stack-builder"
    assert len(manifest.frames) == 3
    assert manifest.challenge is not None
    assert manifest.challenge.push_order == ["main", "cook", "mix"]
    assert manifest.challenge.pop_order == ["mix", "cook", "main"]

    html = render_game_manifest(manifest)
    cleaned, checks = postprocess(html)
    assert checks.get("passed")
    assert 'content="stack-builder"' in cleaned or "stack-builder" in cleaned
    assert "Push main" in cleaned or "stack-actions" in cleaned
    assert "btn-pop" in cleaned
    meta = game_artifact_metadata(cleaned)
    assert meta.get("game_mode") == "stack-builder"


def test_build_manifest_fills_defaults_without_sections() -> None:
    manifest = build_game_manifest({"title": "Chaos Game"})
    assert len(manifest.stations) >= 2
    assert "Chaos Game" in manifest.goal or "Visit" in manifest.goal


def test_render_passes_capsule_gate_and_emits_metadata() -> None:
    manifest = build_game_manifest(
        {
            "title": "Stack Walk",
            "sections": [
                {"title": "Push", "objective": "Frames go on the stack."},
                {"title": "Pop", "objective": "Frames come off the stack."},
            ],
        }
    )
    html = render_game_manifest(manifest)
    assert 'name="hituto-presentation" content="game"' in html
    assert "game-runtime" not in html  # inlined, not a separate fetch
    assert "/game-kits/toon/Character_Soldier.gltf" in html
    assert "three@0.147" in html
    assert "GLTFLoader" in html
    assert "WebGLRenderer" in html or "THREE.WebGLRenderer" in html

    cleaned, checks = postprocess(html)
    assert "unsafe parent/top window access" not in checks.get("failed", [])
    assert "hituto-presentation" in cleaned
    meta = game_artifact_metadata(cleaned)
    assert meta.get("presentation") == "game"
    assert meta.get("game_mode") == "toon-gallery"


async def test_game_agent_stamps_manifest(monkeypatch) -> None:
    emitted: list[tuple[str, str, int]] = []

    async def emit(stage: str, detail: str, pct: int) -> None:
        emitted.append((stage, detail, pct))

    ctx = AuthorContext(
        course_id="c1",
        lesson_id="l1",
        attempt=1,
        plan={
            "title": "Gallery",
            "sections": [
                {"title": "A", "objective": "First idea."},
                {"title": "B", "objective": "Second idea."},
            ],
        },
        knobs={},
        state={},
        llm=None,
        emit=emit,
    )
    out = await GameAgent().author(ctx)
    assert out.kind == "html"
    assert out.plan["game_manifest"]["mode"] == "toon-gallery"
    assert 'content="game"' in out.html
    assert emitted and emitted[0][0] == "generating"


async def test_game_agent_fails_closed_to_page(monkeypatch) -> None:
    from app.coursegen.designs import page as page_module
    from app.coursegen.designs.base import DesignOutput
    import app.coursegen.game_manifest as gm

    def boom(plan, knobs=None):
        raise ValueError("invalid game plan")

    monkeypatch.setattr(gm, "build_game_manifest", boom)

    async def fake_page_author(self, ctx):
        return DesignOutput(kind="html", html="<html>page-fallback</html>", plan=ctx.plan)

    monkeypatch.setattr(page_module.PageAgent, "author", fake_page_author)

    ctx = AuthorContext(
        course_id="c1",
        lesson_id="l1",
        attempt=1,
        plan={"title": "X"},
        knobs={},
        state={},
        llm=None,
    )
    out = await GameAgent().author(ctx)
    assert out.html == "<html>page-fallback</html>"

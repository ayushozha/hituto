"""Design-agent registry (specs/design_agents §4): dispatch + agent outputs."""
from app.coursegen.designs import (
    AuthorContext,
    DesignOutput,
    PageAgent,
    StudioAgent,
    get_design_agent,
)


def test_registry_dispatch_and_page_fallback() -> None:
    assert isinstance(get_design_agent("studio"), StudioAgent)
    assert isinstance(get_design_agent("page"), PageAgent)
    assert isinstance(get_design_agent("slide"), PageAgent)  # shell variant, same agent
    # Fail-closed: unknown/empty modes go to the universal page agent.
    assert isinstance(get_design_agent("holodeck"), PageAgent)
    assert isinstance(get_design_agent(None), PageAgent)
    assert isinstance(get_design_agent("  STUDIO "), StudioAgent)


async def test_studio_agent_stamps_manifest_into_plan(monkeypatch) -> None:
    from app.coursegen.designs import studio as studio_module

    class _FakeManifest:
        mode = "specimen"

        def model_dump(self):
            return {"schema_version": "2.0", "mode": "specimen"}

    import app.coursegen.studio_manifest as sm
    import app.coursegen.studio_renderer as sr

    monkeypatch.setattr(sm, "build_studio_manifest", lambda plan, knobs: _FakeManifest())
    monkeypatch.setattr(sr, "render_studio_manifest", lambda m: "<html>studio</html>")

    emitted: list[tuple[str, str, int]] = []

    async def emit(stage: str, detail: str, pct: int) -> None:
        emitted.append((stage, detail, pct))

    ctx = AuthorContext(
        course_id="c1",
        lesson_id="l1",
        attempt=1,
        plan={"title": "Beetle"},
        knobs={"design_mode": "studio"},
        state={},
        llm=None,
        emit=emit,
    )
    out = await studio_module.StudioAgent().author(ctx)
    assert isinstance(out, DesignOutput)
    assert out.kind == "html"
    assert out.html == "<html>studio</html>"
    assert out.plan["studio_mode"] == "specimen"
    assert out.plan["studio_manifest"]["mode"] == "specimen"
    assert emitted and emitted[0][0] == "generating"


async def test_page_agent_whole_doc_path_with_stub_llm() -> None:
    class _StubLLM:
        # Old-style stub without on_delta — the agent must stay buffered-compatible.
        async def generate_html(self, system: str, user: str) -> str:
            return "<html><body>page lesson</body></html>"

    ctx = AuthorContext(
        course_id="c1",
        lesson_id="l1",
        attempt=1,
        plan={"title": "Gears", "archetype": "explainer", "sections": []},
        knobs={},
        state={},
        llm=_StubLLM(),
    )
    out = await PageAgent().author(ctx)
    assert out.kind == "html"
    assert "page lesson" in out.html

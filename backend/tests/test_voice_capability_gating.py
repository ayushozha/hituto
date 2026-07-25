"""Capability-gated voice tools (specs/design_agents §6, rollout step 3)."""
from app.voice.agent_langchain import (
    BRIDGE_TOOL_NAMES,
    PAGE_TOOL_NAMES,
    _openai_tool_specs,
    realtime_tool_specs,
)
from app.voice.grounding import build_instructions


def _bridge_names(specs: list[dict]) -> set[str]:
    return {s["function"]["name"] for s in specs} & BRIDGE_TOOL_NAMES


def test_capsule_surface_gets_page_tools_and_app_action() -> None:
    names = _bridge_names(_openai_tool_specs({"page_control": True, "seek": False}))
    assert PAGE_TOOL_NAMES <= names
    assert "app_action" in names


def test_video_surface_gets_seek_tools_only() -> None:
    names = _bridge_names(_openai_tool_specs({"page_control": False, "seek": True}))
    assert names == {"observe_page", "app_action"}
    # No cursor/page tools without an iframe runtime to receive them.
    assert "click" not in names and "highlight" not in names


def test_a2ui_surface_gets_no_bridge_tools_but_keeps_widgets() -> None:
    specs = _openai_tool_specs({"page_control": False, "seek": False, "whiteboard": True})
    assert _bridge_names(specs) == set()
    widget_names = {s["function"]["name"] for s in specs}
    assert "create_quiz" in widget_names and "show_whiteboard" in widget_names


def test_missing_capabilities_keeps_legacy_page_toolset() -> None:
    assert _bridge_names(_openai_tool_specs(None)) == PAGE_TOOL_NAMES
    flat = realtime_tool_specs(None)
    assert {s["name"] for s in flat} & BRIDGE_TOOL_NAMES == PAGE_TOOL_NAMES


def test_instructions_follow_capabilities() -> None:
    base = {
        "lesson_title": "Gears on film",
        "course_title": "Bikes",
        "lesson_objective": "watch",
        "lesson_archetype": "explainer",
        "artifact_digest": "",
    }
    video = build_instructions(
        {**base, "surface_kind": "video", "surface_capabilities": {"page_control": False, "seek": True}}
    )
    assert "# Video Controls" in video
    assert "# Page Control" not in video

    capsule = build_instructions(
        {**base, "surface_capabilities": {"page_control": True, "seek": False}}
    )
    assert "# Page Control" in capsule
    assert "# Video Controls" not in capsule

    legacy = build_instructions(base)  # no capabilities → legacy page block stays
    assert "# Page Control" in legacy
from app.coursegen.agents.lesson_agent import _brief
from app.coursegen.agents.roles.capsule_author import _fallback_tree, capsule_author_subagent
from app.coursegen.prompt import SYSTEM, build_user_prompt


def _plan() -> dict:
    return {
        "title": "Loop Engineering",
        "archetype": "explainer",
        "difficulty": "intermediate",
        "sections": [{"title": "The loop", "objective": "Trace one iteration."}],
        "interactions": [{"type": "slider", "purpose": "Change iteration count"}],
        "facts": [],
        "knobs": {"presentation": "page"},
    }


def test_graph_prompt_contains_current_hituto_design_contract() -> None:
    assert "hituto-generated-lesson-design" in SYSTEM
    assert "paper:'#FAFAFA'" in SYSTEM
    assert "fixed full-height documentation sidebar" in SYSTEM
    assert "Bricolage Grotesque:opsz" not in SYSTEM


def test_deep_capsule_author_receives_brand_skill_before_page_shell() -> None:
    prompt = capsule_author_subagent(design="page")["system_prompt"]

    brand_index = prompt.index("Shared Hi Tuto lesson design")
    shell_index = prompt.index("Page shell — REQUIRED")
    assert brand_index < shell_index
    assert "#FAFAFA" in prompt
    assert "Never build a fixed full-height documentation sidebar" in prompt


def test_page_brief_starts_with_first_section_without_heading_or_navigation() -> None:
    prompt = build_user_prompt(_plan())

    assert "Start directly with the first learning section" in prompt
    assert "Do not generate a page title" in prompt
    assert "section navigation" in prompt
    assert "Include a fixed left-rail" not in prompt


def test_deep_page_brief_and_a2ui_fallback_do_not_repeat_host_title() -> None:
    brief = _brief("course-1", _plan(), "Loop Engineering", "page")
    assert "Start /build/capsule.html directly with the first content section" in brief
    assert "no title/intro header" in brief

    tree = _fallback_tree(_plan())
    children = tree["root"]["children"]
    assert children[0]["props"]["text"] == "The loop"
    assert all(node.get("props", {}).get("text") != "Loop Engineering" for node in children)

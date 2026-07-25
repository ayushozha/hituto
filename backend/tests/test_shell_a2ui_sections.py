"""Server-owned zinc shell + A2UI section assembly / patch."""
from app.capsule.shell import assemble_generate_ui, extract_body_inner, lesson_shell
from app.coursegen.a2ui_sections import assemble_a2ui_doc, patch_a2ui_section


def test_assemble_generate_ui_wraps_fragment() -> None:
    html = assemble_generate_ui('<canvas id="c"></canvas><button>Go</button>')
    assert html.startswith("<!DOCTYPE html>")
    assert "cdn.tailwindcss.com" in html
    assert "#FAFAFA" in html  # zinc paper
    assert "#FDF1E7" not in html  # no cream
    assert 'max-width: 100%' in html or "max-width:100%" in html
    assert '<canvas id="c"></canvas>' in html


def test_assemble_generate_ui_extracts_body_from_full_doc() -> None:
    doc = "<!DOCTYPE html><html><body><p class='x'>hi</p></body></html>"
    assert extract_body_inner(doc) == "<p class='x'>hi</p>"
    out = assemble_generate_ui(doc)
    assert "<p class='x'>hi</p>" in out
    assert out.count("<!DOCTYPE html>") == 1


def test_lesson_shell_zinc() -> None:
    head, tail = lesson_shell({})
    assert "#16A34A" in head  # lime
    assert "#18181B" in head  # ink
    assert tail.endswith("</html>")


def test_assemble_and_patch_a2ui_section() -> None:
    plan = {"title": "Gears", "subtitle": "Learn ratios"}
    roots = [
        (
            "intro",
            "Intro",
            {
                "type": "stack",
                "props": {"direction": "vertical", "gap": "md"},
                "children": [
                    {"type": "heading", "props": {"text": "Intro", "level": 2}, "children": []},
                    {"type": "text", "props": {"text": "Hello"}, "children": []},
                ],
            },
        ),
        (
            "quiz",
            "Check",
            {
                "type": "stack",
                "props": {"direction": "vertical", "gap": "md"},
                "children": [
                    {"type": "heading", "props": {"text": "Check", "level": 2}, "children": []},
                ],
            },
        ),
    ]
    doc = assemble_a2ui_doc(plan, roots)
    assert doc["title"] == "Gears"
    assert len(doc["sections"]) == 2
    assert doc["root"]["type"] == "stack"

    new_root = {
        "type": "stack",
        "props": {"direction": "vertical", "gap": "md"},
        "children": [
            {"type": "heading", "props": {"text": "Intro v2", "level": 2}, "children": []},
            {"type": "text", "props": {"text": "Updated"}, "children": []},
        ],
    }
    patched = patch_a2ui_section(doc, "intro", new_root)
    assert patched is not None
    intro = next(s for s in patched["sections"] if s["id"] == "intro")
    texts = [
        c["props"]["text"]
        for c in intro["root"]["children"]
        if c.get("type") == "text"
    ]
    assert "Updated" in texts

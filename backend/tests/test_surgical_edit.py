"""Surgical A2UI insert + HTML section splice (specs/a2ui_surgical_edit)."""
from app.a2ui import INSERTABLE_TYPES, normalize_ui_node
from app.coursegen.a2ui_sections import (
    assemble_a2ui_doc,
    insert_node_into_section_root,
    patch_a2ui_section,
    replace_node_at_path,
    _fallback_insert_node,
)
from app.coursegen.html_sections import (
    extract_section_outer,
    list_section_ids,
    replace_section_outer,
    stamp_section_attrs,
)


def test_insert_quiz_preserves_sibling_section() -> None:
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
            "practice",
            "Practice",
            {
                "type": "stack",
                "props": {"direction": "vertical", "gap": "md"},
                "children": [
                    {"type": "heading", "props": {"text": "Practice", "level": 2}, "children": []},
                ],
            },
        ),
    ]
    doc = assemble_a2ui_doc(plan, roots)
    practice = next(s for s in doc["sections"] if s["id"] == "practice")
    intro_before = next(s for s in doc["sections"] if s["id"] == "intro")
    quiz = normalize_ui_node(_fallback_insert_node("quiz", "gear ratios"))
    assert quiz and quiz["type"] == "quiz"
    new_root = insert_node_into_section_root(practice["root"], quiz, placement="append")
    assert new_root is not None
    patched = patch_a2ui_section(doc, "practice", new_root)
    assert patched is not None
    intro_after = next(s for s in patched["sections"] if s["id"] == "intro")
    practice_after = next(s for s in patched["sections"] if s["id"] == "practice")
    assert intro_after["root"] == intro_before["root"]
    types = [c.get("type") for c in practice_after["root"]["children"]]
    assert "quiz" in types


def test_insert_map_normalizes() -> None:
    node = normalize_ui_node(_fallback_insert_node("map", "Oakland valuation"))
    assert node is not None
    assert node["type"] == "map"
    assert node["props"]["listings"]
    assert "map" in INSERTABLE_TYPES


def test_unknown_insert_type_rejected() -> None:
    assert "spaceship" not in INSERTABLE_TYPES
    assert normalize_ui_node({"type": "spaceship", "props": {}, "children": []}) is None


def test_replace_node_at_path() -> None:
    root = {
        "type": "stack",
        "props": {"direction": "vertical", "gap": "md"},
        "children": [
            {"type": "heading", "props": {"text": "A", "level": 2}, "children": []},
            {"type": "text", "props": {"text": "old"}, "children": []},
        ],
    }
    new = {"type": "text", "props": {"text": "new"}, "children": []}
    out = replace_node_at_path(root, [1], new)
    assert out is not None
    assert out["children"][1]["props"]["text"] == "new"
    assert out["children"][0]["props"]["text"] == "A"


def test_html_section_splice_preserves_sibling() -> None:
    html = """<!DOCTYPE html><html><body>
<section id="section-intro" data-lesson-section="intro"><h2>Intro</h2><p>A</p></section>
<section id="section-practice" data-lesson-section="practice"><h2>Practice</h2><p>B</p></section>
</body></html>"""
    assert list_section_ids(html) == ["intro", "practice"]
    practice = extract_section_outer(html, "practice")
    assert practice and "Practice" in practice
    new = stamp_section_attrs(
        '<section><h2>Practice v2</h2><p>Updated</p><svg></svg></section>',
        "practice",
        "Practice",
    )
    merged = replace_section_outer(html, "practice", new)
    assert merged is not None
    assert 'data-lesson-section="intro"' in merged
    assert ">A<" in merged or ">A</p>" in merged
    assert "Updated" in merged
    assert extract_section_outer(merged, "intro") == extract_section_outer(html, "intro")

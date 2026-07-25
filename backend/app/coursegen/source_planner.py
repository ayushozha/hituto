"""Source-grounded course planner — teaching_map chapters → capsules.

Legacy heading-only documents are upgraded via `ensure_knowledge_tree` before this
runs. If only section titles remain, build a minimal synthetic teaching map.
"""
from __future__ import annotations

_LESSONS_PER_CHAPTER = 3

_MODE_VERB = {
    "paper_walkthrough": "Understand how the source presents",
    "textbook_chapter": "Build intuition for",
    "exam_prep": "Be able to answer exam questions about",
    "code_lab": "Implement and experiment with",
    "math_lab": "Work through the math of",
}


def plan_from_teaching_map(
    teaching_map: dict,
    *,
    title: str,
    difficulty: str = "intermediate",
    lesson_count: int = 6,
    mode: str = "paper_walkthrough",
    selected_outline_nodes: list[str] | None = None,
) -> dict:
    """1:1 teaching chapter → lesson by default; clamp to lesson_count."""
    chapters_in = list((teaching_map or {}).get("chapters") or [])
    if selected_outline_nodes is not None:
        allowed = set(selected_outline_nodes)
        filtered = []
        for ch in chapters_in:
            nodes = list(ch.get("source_node_ids") or [])
            if nodes and all(n in allowed for n in nodes):
                filtered.append(ch)
            elif not nodes:
                continue
            elif any(n in allowed for n in nodes):
                slim = dict(ch)
                slim["source_node_ids"] = [n for n in nodes if n in allowed]
                filtered.append(slim)
        chapters_in = filtered

    if not chapters_in:
        raise ValueError("teaching_map has no usable chapters for planning")

    lesson_count = max(1, min(12, lesson_count))
    chapters_in = chapters_in[:lesson_count]

    lessons = []
    lesson_scopes: dict[str, dict] = {}
    for i, ch in enumerate(chapters_in):
        cid = str(ch.get("id") or f"ch-{i + 1}")
        node_ids = list(ch.get("source_node_ids") or [])
        if not node_ids:
            raise ValueError(f"teaching chapter {cid} has empty source_node_ids")
        title_l = str(ch.get("title") or cid)
        lessons.append(
            {
                "concept_id": cid,
                "title": title_l,
                "objective": (
                    f"{_MODE_VERB.get(mode, 'Build intuition for')} “{title_l}” "
                    f"from the source. {(ch.get('summary') or '')[:160]}"
                ).strip(),
                "archetype": "explainer",
                "source_query": title_l,
                "chapter_ids": [cid],
            }
        )
        lesson_scopes[str(i)] = {
            "chapter_ids": [cid],
            "covers": (ch.get("summary") or "")[:240],
            "avoid": "",
        }

    roadmap_chapters: list[dict] = []
    for i in range(0, len(lessons), _LESSONS_PER_CHAPTER):
        group = lessons[i : i + _LESSONS_PER_CHAPTER]
        roadmap_chapters.append(
            {"title": f"Chapter {len(roadmap_chapters) + 1}: {group[0]['title']}", "lessons": group}
        )

    return {
        "title": title,
        "mode": mode,
        "difficulty": difficulty,
        "chapters": roadmap_chapters,
        "lesson_scopes": lesson_scopes,
        "planner": "teaching_map",
        "document_summary": (teaching_map or {}).get("document_summary") or "",
        "thesis": (teaching_map or {}).get("thesis"),
    }


def _synthetic_map_from_sections(sections: list[str], title: str) -> dict:
    """Last-resort planner input when lazy upgrade produced no map but headings exist."""
    chapters = []
    for i, name in enumerate(sections or []):
        cid = f"ch-sec-{i + 1}"
        chapters.append(
            {
                "id": cid,
                "order": i + 1,
                "title": name,
                "summary": name,
                "source_node_ids": [f"sec-{i + 1}"],
            }
        )
    if not chapters:
        chapters = [
            {
                "id": "ch-overview",
                "order": 1,
                "title": "Overview",
                "summary": title or "Overview",
                "source_node_ids": ["sec-overview"],
            }
        ]
    return {
        "status": "fallback",
        "document_kind": "unknown",
        "document_summary": title or "Document overview.",
        "thesis": None,
        "chapters": chapters,
    }


def plan_source_course(
    source_map: dict,
    *,
    title: str,
    difficulty: str = "intermediate",
    lesson_count: int = 6,
    mode: str = "paper_walkthrough",
    use_teaching_map: bool | None = None,
    selected_outline_nodes: list[str] | None = None,
) -> dict:
    """Plan from teaching_map only. `use_teaching_map=False` builds a section synthetic map."""
    tm = (source_map or {}).get("teaching_map")
    if use_teaching_map is False or not (tm and tm.get("chapters")):
        # Synthetic map from section titles (tests / emergency). Not concept_dag.
        tm = _synthetic_map_from_sections(
            list((source_map or {}).get("sections") or []), title
        )
        # Attach matching outline nodes so validation / materialize can work in tests.
        if not (source_map or {}).get("document_outline"):
            nodes = []
            for i, ch in enumerate(tm["chapters"]):
                nid = ch["source_node_ids"][0]
                nodes.append(
                    {
                        "id": nid,
                        "parent_id": None,
                        "order": i + 1,
                        "title": ch["title"],
                        "level": 1,
                        "markdown_start": 0,
                        "markdown_end": 0,
                        "element_ids": [],
                        "token_count": 1,
                    }
                )
            # Mutating caller's map is intentional for synthetic path in-memory only.
            source_map = dict(source_map or {})
            source_map["document_outline"] = {"version": 1, "nodes": nodes}

    return plan_from_teaching_map(
        tm,
        title=title,
        difficulty=difficulty,
        lesson_count=lesson_count,
        mode=mode,
        selected_outline_nodes=selected_outline_nodes,
    )

"""Per-section A2UI authoring with progressive SSE frames (fast_gen Mode A).

Structured lessons stream validated UiNode trees into the host ``A2UIRenderer`` instead of
skipping the generation theater. Fail-closed: bad section → interactive quiz/steps fallback;
all sections bad → None (caller falls back to whole-doc A2UI or HTML).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

from ..a2ui import INSERTABLE_TYPES, normalize_render_ui, normalize_ui_node
from ..core.config import get_settings
from ..core.progress import ProgressEvent, broker

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")

_SECTION_SYSTEM = """You author ONE Hi Tuto A2UI section as JSON only.
Emit a single JSON object: {"title": str, "root": UiNode}.
UiNode shape (STRICT):
  {"type": "<one of below>", "props": { ... }, "children": [UiNode, ...]}
Never put text/title/steps/questions on the node itself — always inside props.

Types + required props:
- stack   props: {direction?: "vertical"|"horizontal", gap?: "sm"|"md"|"lg"} + children
- heading props: {text: str, level?: 1-3}
- text    props: {text: str}   (SHORT — max ~2 sentences; never a wall of prose)
- callout props: {text: str, variant?: "info"|"warning"|"success"|"danger"}
- math    props: {latex: str, display?: bool}
- steps   props: {steps: [{title: str, detail?: str}]}
- quiz    props: {topic?: str, questions: [{type:"mcq", title, prompt, explanation, options:[str], correctAnswer:"0"|"1"|..., hints?:[str]}]}
- table   props: {headers: [str], rows: [[str]], caption?: str}
- chart   props: {kind?: "bar"|"line", labels: [str], series: [{label?: str, values: [num]}]}
- slider  props: {label: str, min?, max?, step?, value?, unit?, readouts?: [{label?, expr, unit?}]}
- diagram props: {nodes: [{id, label?}], edges: [{from, to, label?}], direction?: "TB"|"LR"}
- map     props: {title?, center?: {lat,lng}, listings?: [...], prediction?: {...}}
- embed   props: {title: str, slot_id?, caption?}  (do NOT invent html — server fills gated HTML)

HARD RULES (fail if broken):
1. root MUST be a vertical stack with a heading (section title).
2. MUST include AT LEAST ONE interactive or visual widget from:
   quiz | slider | chart | steps | diagram | math | table | callout
3. NEVER ship heading+text only. Essays belong in textbooks — this is an interactive lesson surface.
4. Keep trees SMALL: depth ≤ 6, ≤ 40 nodes. Prefer 1 quiz (2–3 MCQs) OR 1 slider OR 1 chart OR 1 steps list.
5. chart MUST be type "chart" with props.labels AND props.series — never type "bar"/"line" as the node type.
6. No HTML. No markdown fences. No giant paragraphs.

Good minimal shape example:
{"title":"Why blue sky?",
 "root":{"type":"stack","props":{"direction":"vertical","gap":"md"},"children":[
   {"type":"heading","props":{"text":"Why blue sky?","level":2},"children":[]},
   {"type":"callout","props":{"text":"Shorter wavelengths scatter more.","variant":"info"},"children":[]},
   {"type":"chart","props":{"kind":"bar","labels":["violet","blue","green","red"],
     "series":[{"label":"scatter","values":[1.0,0.7,0.3,0.1]}]},"children":[]},
   {"type":"quiz","props":{"topic":"Scatter check","questions":[{
     "type":"mcq","title":"Q1","prompt":"Which color scatters most?",
     "options":["Red","Green","Blue"],"correctAnswer":"2",
     "explanation":"Blue/violet scatter most (1/λ⁴).","hints":["Think wavelength."]}]},"children":[]}
 ]}}
"""


_INTERACTIVE_TYPES = frozenset(
    {"quiz", "slider", "chart", "steps", "diagram", "math", "table", "callout", "map", "embed"}
)


def _collect_types(node: dict | None) -> set[str]:
    found: set[str] = set()
    if not isinstance(node, dict):
        return found
    t = node.get("type")
    if isinstance(t, str):
        found.add(t)
    for child in node.get("children") or []:
        found |= _collect_types(child if isinstance(child, dict) else None)
    return found


def _is_interactive(root: dict | None) -> bool:
    return bool(_collect_types(root) & _INTERACTIVE_TYPES)


def _slug(section: dict, index: int) -> str:
    raw = str(section.get("id") or f"part-{index + 1}")
    slug = re.sub(r"[^a-z0-9-]", "-", raw.lower()).strip("-")
    return slug or f"part-{index + 1}"


def _clean(content: str) -> str:
    content = _THINK.sub("", content or "").strip()
    return _FENCE.sub("", content).strip()


def _fallback_section(plan: dict, index: int) -> dict[str, Any]:
    section = (plan.get("sections") or [])[index]
    title = str(section.get("title") or f"Part {index + 1}")
    body = re.sub(r"<[^>]+>", "", section.get("body") or section.get("objective") or "")
    blurb = (body.strip() or f"Key idea for {title}.")[:280]
    children: list[dict] = [
        {"type": "heading", "props": {"text": title, "level": 2}, "children": []},
        {
            "type": "callout",
            "props": {"text": blurb, "variant": "info"},
            "children": [],
        },
        {
            "type": "steps",
            "props": {
                "steps": [
                    {"title": "Notice", "detail": f"What stands out about {title}?"},
                    {"title": "Connect", "detail": "Link this idea to what you already know."},
                    {"title": "Check", "detail": "Answer the quick quiz below."},
                ]
            },
            "children": [],
        },
        {
            "type": "quiz",
            "props": {
                "topic": title,
                "questions": [
                    {
                        "type": "mcq",
                        "title": "Quick check",
                        "prompt": f"What is the main takeaway of “{title}”?",
                        "options": [
                            blurb[:80] or "The core idea of this section",
                            "An unrelated fact",
                            "None of the above",
                        ],
                        "correctAnswer": "0",
                        "explanation": blurb or "Re-read the callout above.",
                        "hints": ["Skim the callout."],
                    }
                ],
            },
            "children": [],
        },
    ]
    return {
        "type": "stack",
        "props": {"direction": "vertical", "gap": "md", "sectionId": _slug(section, index)},
        "children": children,
    }


def _enrich_if_text_only(root: dict, title: str) -> dict:
    """If the LLM returned essay-only nodes, inject interactive widgets."""
    if _is_interactive(root):
        return root
    children = list(root.get("children") or []) if root.get("type") == "stack" else [root]
    children.append(
        {
            "type": "callout",
            "props": {
                "text": f"Try the controls below to lock in “{title}”.",
                "variant": "info",
            },
            "children": [],
        }
    )
    children.append(
        {
            "type": "quiz",
            "props": {
                "topic": title,
                "questions": [
                    {
                        "type": "mcq",
                        "title": "Check",
                        "prompt": f"Which best matches “{title}”?",
                        "options": [
                            "I can explain the key idea",
                            "I only memorized a phrase",
                            "I am unsure",
                        ],
                        "correctAnswer": "0",
                        "explanation": "Interactive practice beats passive reading.",
                        "hints": ["Skim the section once more."],
                    }
                ],
            },
            "children": [],
        }
    )
    return {
        "type": "stack",
        "props": {"direction": "vertical", "gap": "md"},
        "children": children,
    }


def assemble_a2ui_doc(plan: dict, section_roots: list[tuple[str, str, dict]]) -> dict[str, Any]:
    """Build a persisted A2UI document from ordered (section_id, title, root) tuples."""
    children = []
    sections_meta = []
    for sid, title, root in section_roots:
        node = dict(root)
        props = dict(node.get("props") or {})
        props["sectionId"] = sid
        node["props"] = props
        children.append(node)
        sections_meta.append({"id": sid, "title": title, "root": node})
    doc = {
        "title": plan.get("title") or "Lesson",
        "intent": (plan.get("subtitle") or plan.get("objective") or "")[:200],
        "root": {
            "type": "stack",
            "props": {"direction": "vertical", "gap": "lg"},
            "children": children,
        },
    }
    normalized = normalize_render_ui(doc)
    if not normalized:
        return {**doc, "sections": sections_meta}
    # Preserve section index for edit — normalize_render_ui only keeps title/intent/root.
    return {**normalized, "sections": sections_meta}


def a2ui_sections_eligible(plan: dict, state: dict) -> bool:
    """Multi-section structured lessons can stream A2UI section trees."""
    if state.get("previous_html") or state.get("target_html"):
        return False
    sections = plan.get("sections") or []
    return len(sections) >= 2


async def author_a2ui_sections(
    *,
    plan: dict,
    course_id: str,
    lesson_id: str,
    attempt: int = 1,
    on_section_done: Callable[[str, bool], Awaitable[None]] | None = None,
) -> dict[str, Any] | None:
    """Author all plan sections as A2UI trees; stream each via ``a2ui_section`` SSE.

    Returns the assembled normalized document, or None if every section degraded.
    """
    from ..providers.registry import get_coursegen_llm

    sections = plan.get("sections") or []
    if not sections:
        return None
    settings = get_settings()
    sem = asyncio.Semaphore(max(1, settings.gen_section_concurrency))
    llm = get_coursegen_llm()

    async def one(index: int) -> tuple[str, str, dict, bool]:
        section = sections[index]
        slug = _slug(section, index)
        title = str(section.get("title") or f"Part {index + 1}")
        user = (
            f"Lesson: {plan.get('title')}\n"
            f"Archetype: {plan.get('archetype') or 'explainer'}\n"
            f"Difficulty: {plan.get('difficulty') or 'intermediate'}\n"
            f"Section {index + 1}/{len(sections)} id={slug} title={title}\n"
            f"Objective: {section.get('objective') or ''}\n"
            f"Draft: {section.get('body') or ''}\n"
            f"Facts: {json.dumps(plan.get('facts') or [])[:800]}\n"
            "Emit JSON {title, root} for THIS section only.\n"
            "REQUIRED: include quiz OR slider OR chart OR steps OR diagram "
            "(not heading/text alone)."
        )
        async with sem:
            for _try in (1, 2):
                try:
                    raw = await llm.generate_html(_SECTION_SYSTEM, user)
                    data = json.loads(_clean(raw))
                    root = data.get("root") or data
                    if isinstance(root, dict):
                        root = _enrich_if_text_only(root, title)
                    normalized = normalize_render_ui(
                        {
                            "title": data.get("title") or title,
                            "intent": title,
                            "root": root,
                        }
                    )
                    if normalized and normalized.get("root"):
                        tree = normalized["root"]
                        if not _is_interactive(tree):
                            raise ValueError("section is text-only; need interactive widgets")
                        await broker.publish(
                            course_id,
                            ProgressEvent(
                                stage="a2ui_section",
                                detail=f"Section ready: {title}",
                                pct=min(88, 55 + int(30 * (index + 1) / max(len(sections), 1))),
                                data={
                                    "lesson_id": lesson_id,
                                    "section_id": slug,
                                    "title": title,
                                    "root": tree,
                                    "attempt": attempt,
                                    "index": index,
                                    "total": len(sections),
                                },
                            ),
                        )
                        return slug, title, tree, True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("A2UI section %s failed (try %s): %s", slug, _try, exc)
                    user += (
                        "\n\nREPAIR: emit ONLY valid JSON {title, root}. "
                        "MUST include quiz/slider/chart/steps — never heading+text only."
                    )
        tree = _fallback_section(plan, index)
        await broker.publish(
            course_id,
            ProgressEvent(
                stage="a2ui_section",
                detail=f"Section draft: {title}",
                pct=min(88, 55 + int(30 * (index + 1) / max(len(sections), 1))),
                data={
                    "lesson_id": lesson_id,
                    "section_id": slug,
                    "title": title,
                    "root": tree,
                    "attempt": attempt,
                    "index": index,
                    "total": len(sections),
                    "fallback": True,
                },
            ),
        )
        return slug, title, tree, False

    results = await asyncio.gather(*(one(i) for i in range(len(sections))))
    if on_section_done:
        for slug, _title, _root, ok in results:
            await on_section_done(slug, ok)
    if not any(ok for *_rest, ok in results):
        return None
    ordered = [(slug, title, root) for slug, title, root, _ok in results]
    return assemble_a2ui_doc(plan, ordered)


def patch_a2ui_section(doc: dict, section_id: str, root: dict) -> dict[str, Any] | None:
    """Replace one section's subtree; re-normalize. None if invalid."""
    sections = list(doc.get("sections") or [])
    if not sections and doc.get("root"):
        # Legacy whole-tree doc: wrap as a single editable section.
        sections = [{"id": "main", "title": doc.get("title") or "Lesson", "root": doc["root"]}]
    found = False
    new_sections = []
    for sec in sections:
        sid = str(sec.get("id") or "")
        if sid == section_id:
            normalized = normalize_render_ui(
                {
                    "title": sec.get("title") or section_id,
                    "intent": sec.get("title") or "",
                    "root": root,
                }
            )
            if not normalized or not normalized.get("root"):
                return None
            node = dict(normalized["root"])
            props = dict(node.get("props") or {})
            props["sectionId"] = sid
            node["props"] = props
            new_sections.append({"id": sid, "title": sec.get("title") or sid, "root": node})
            found = True
        else:
            new_sections.append(sec)
    if not found:
        return None
    plan_like = {"title": doc.get("title"), "subtitle": doc.get("intent")}
    assembled = assemble_a2ui_doc(
        plan_like,
        [(str(s["id"]), str(s.get("title") or s["id"]), s["root"]) for s in new_sections],
    )
    return assembled


async def rewrite_a2ui_section_with_instruction(
    *,
    section_id: str,
    title: str,
    current_root: dict,
    instruction: str,
) -> dict | None:
    """LLM-rewrite one section tree via the lesson-edit agent."""
    from ..lesson_edit import rewrite_a2ui_section

    return await rewrite_a2ui_section(
        section_id=section_id,
        title=title,
        current_root=current_root,
        instruction=instruction,
    )


def _fallback_insert_node(node_type: str, hint: str) -> dict[str, Any]:
    """Deterministic catalogue node when the LLM fails."""
    h = (hint or "").strip()[:400]
    t = node_type.lower().strip()
    if t == "quiz":
        return {
            "type": "quiz",
            "props": {
                "topic": h or "Quick check",
                "questions": [
                    {
                        "type": "mcq",
                        "title": "Question 1",
                        "prompt": h or "Which statement is true?",
                        "explanation": "Review the section above.",
                        "options": ["Option A", "Option B", "Option C"],
                        "correctAnswer": "0",
                        "hints": ["Re-read the key idea."],
                    }
                ],
            },
            "children": [],
        }
    if t == "map":
        return {
            "type": "map",
            "props": {
                "title": h or "Neighborhood valuation lab",
                "center": {"lat": 37.8, "lng": -122.3},
                "zoom": 11,
                "listings": [
                    {
                        "id": "h1",
                        "lat": 37.8044,
                        "lng": -122.2712,
                        "label": "Oakland craftsman",
                        "beds": 3,
                        "baths": 2,
                        "sqft": 1600,
                        "list_price": 980000,
                    },
                    {
                        "id": "h2",
                        "lat": 37.7749,
                        "lng": -122.4194,
                        "label": "SF condo",
                        "beds": 2,
                        "baths": 1,
                        "sqft": 920,
                        "list_price": 1150000,
                    },
                ],
                "prediction": {
                    "mode": "linear_demo",
                    "features": ["sqft", "beds", "baths"],
                    "student_inputs": ["sqft", "beds"],
                },
                "copy": {"task": h or "Adjust features and compare your estimate to list price."},
            },
            "children": [],
        }
    if t == "embed":
        return {
            "type": "embed",
            "props": {
                "title": h or "Interactive demo",
                "slot_id": "demo",
                "caption": "Practice sim",
                "html": "",
            },
            "children": [],
        }
    if t == "callout":
        return {
            "type": "callout",
            "props": {"text": h or "Key takeaway", "variant": "info"},
            "children": [],
        }
    if t == "chart":
        return {
            "type": "chart",
            "props": {
                "kind": "bar",
                "caption": h or "Sample chart",
                "labels": ["A", "B", "C"],
                "series": [{"label": "Values", "values": [3, 5, 2]}],
            },
            "children": [],
        }
    if t == "steps":
        return {
            "type": "steps",
            "props": {
                "steps": [
                    {"title": "Step 1", "detail": h or "Start here"},
                    {"title": "Step 2", "detail": "Check your work"},
                ]
            },
            "children": [],
        }
    if t == "table":
        return {
            "type": "table",
            "props": {
                "caption": h or "Reference",
                "headers": ["Item", "Value"],
                "rows": [["Example", "1"], ["Example", "2"]],
            },
            "children": [],
        }
    if t == "slider":
        return {
            "type": "slider",
            "props": {
                "label": h or "Adjust",
                "min": 0,
                "max": 100,
                "step": 1,
                "value": 50,
                "unit": "",
                "readouts": [{"label": "2×", "expr": "2*x", "unit": ""}],
            },
            "children": [],
        }
    if t == "diagram":
        return {
            "type": "diagram",
            "props": {
                "caption": h or "Flow",
                "nodes": [{"id": "a", "label": "Start"}, {"id": "b", "label": "End"}],
                "edges": [{"from": "a", "to": "b"}],
                "direction": "LR",
            },
            "children": [],
        }
    if t == "math":
        return {"type": "math", "props": {"latex": "E = mc^2", "display": True}, "children": []}
    if t == "heading":
        return {"type": "heading", "props": {"text": h or "New section", "level": 2}, "children": []}
    return {"type": "text", "props": {"text": h or "New note."}, "children": []}


def _ensure_embed_html(node: dict[str, Any]) -> dict[str, Any]:
    """Fill gated placeholder HTML for embed nodes that lack it."""
    if (node.get("type") or "") != "embed":
        return node
    props = dict(node.get("props") or {})
    if (props.get("html") or "").strip():
        return node
    from ..capsule.postprocess import postprocess
    from ..capsule.shell import assemble_generate_ui

    title = str(props.get("title") or "Interactive demo")
    caption = str(props.get("caption") or "")
    body = (
        f'<section data-lesson-section="{props.get("slot_id") or "embed"}" class="p-6">'
        f'<h2 class="text-xl font-bold text-ink">{title}</h2>'
        f'<p class="mt-2 text-ink-soft">{caption or "Adjust the control to explore the idea."}</p>'
        f'<label class="mt-4 block text-sm font-semibold">Practice value'
        f'<input id="demo-range" type="range" min="0" max="100" value="40" class="mt-1 w-full"/>'
        f'</label>'
        f'<p class="mt-2 text-sm">Value: <span id="demo-out">40</span></p>'
        f'<script>(function(){{var r=document.getElementById("demo-range");'
        f'var o=document.getElementById("demo-out");'
        f'if(r&&o)r.addEventListener("input",function(){{o.textContent=r.value;}});}})();</script>'
        f"</section>"
    )
    assembled = assemble_generate_ui(body)
    gated, checks = postprocess(assembled)
    if checks.get("passed"):
        props["html"] = gated
    else:
        props["html"] = ""
    out = dict(node)
    out["props"] = props
    return out


async def author_insert_node(*, node_type: str, hint: str = "") -> dict[str, Any] | None:
    """Produce one validated catalogue node for slash-insert via lesson-edit agent."""
    t = (node_type or "").lower().strip()
    if t not in INSERTABLE_TYPES:
        return None
    from ..lesson_edit import author_catalogue_insert

    node = await author_catalogue_insert(node_type=t, hint=hint)
    if node:
        return _ensure_embed_html(node)
    fallback = normalize_ui_node(_fallback_insert_node(t, hint))
    return _ensure_embed_html(fallback) if fallback else None


def _get_child(node: dict, index: int) -> dict | None:
    kids = node.get("children")
    if not isinstance(kids, list) or index < 0 or index >= len(kids):
        return None
    child = kids[index]
    return child if isinstance(child, dict) else None


def replace_node_at_path(root: dict, path: list[int], new_node: dict) -> dict | None:
    """Replace a subtree addressed by child indices. Returns new root or None."""
    if not path:
        return normalize_ui_node(new_node)
    cloned = json.loads(json.dumps(root))
    cur = cloned
    for idx in path[:-1]:
        nxt = _get_child(cur, idx)
        if nxt is None:
            return None
        cur = nxt
    kids = cur.get("children")
    if not isinstance(kids, list) or path[-1] < 0 or path[-1] >= len(kids):
        return None
    normalized = normalize_ui_node(new_node)
    if not normalized:
        return None
    kids[path[-1]] = normalized
    return normalize_ui_node(cloned) or cloned


def insert_node_into_section_root(
    root: dict,
    node: dict,
    *,
    placement: str = "append",
    index: int | None = None,
) -> dict | None:
    """Splice a validated node into a section root (promotes non-stacks to stack)."""
    normalized_node = normalize_ui_node(node)
    if not normalized_node:
        return None
    base = dict(root) if isinstance(root, dict) else {}
    if (base.get("type") or "") != "stack":
        base = {
            "type": "stack",
            "props": {"direction": "vertical", "gap": "md"},
            "children": [base] if base.get("type") else [],
        }
    children = list(base.get("children") or [])
    place = (placement or "append").lower()
    if place == "prepend":
        children.insert(0, normalized_node)
    elif place == "index" and index is not None:
        i = max(0, min(len(children), int(index)))
        children.insert(i, normalized_node)
    else:
        children.append(normalized_node)
    base["children"] = children
    return normalize_ui_node(base) or base


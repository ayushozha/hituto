"""Lesson-edit agent LLM calls — one unit in, one unit out."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from ..a2ui import INSERTABLE_TYPES, normalize_render_ui, normalize_ui_node
from ..providers.registry import get_lesson_edit_llm
from .prompts import A2UI_INSERT_SYSTEM, A2UI_SECTION_SYSTEM, HTML_SECTION_SYSTEM

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json|html)?\s*|\s*```$", re.MULTILINE)
_CLASS_RE = re.compile(r"""class\s*=\s*["']([^"']+)["']""", re.I)


def _clean(content: str) -> str:
    content = _THINK.sub("", content or "").strip()
    return _FENCE.sub("", content).strip()


def style_fingerprint(html: str, *, limit: int = 24) -> str:
    """Compact class-token digest from a fragment (sibling style hint — not full HTML)."""
    counts: Counter[str] = Counter()
    for block in _CLASS_RE.findall(html or ""):
        for tok in block.split():
            tok = tok.strip()
            if len(tok) >= 2:
                counts[tok] += 1
    if not counts:
        return ""
    top = [t for t, _ in counts.most_common(limit)]
    return " ".join(top)


async def rewrite_html_section(
    *,
    section_id: str,
    current_html: str,
    instruction: str,
    target_snippet: str | None = None,
    sibling_style_hint: str | None = None,
) -> str | None:
    """Rewrite one section outerHTML. Does **not** receive the full lesson document."""
    llm = get_lesson_edit_llm()
    user_parts = [
        f"Section id={section_id}",
        f"Edit instruction: {instruction}",
        "Return the full updated <section> for THIS id only.",
        "Match the look of CURRENT SECTION HTML (classes, structure, visuals).",
    ]
    if sibling_style_hint:
        user_parts.append(
            f"Sibling style tokens (match these if you must add classes): {sibling_style_hint}"
        )
    snippet = (target_snippet or "").strip()
    if snippet:
        user_parts.append(f"Clicked subtree hint:\n```html\n{snippet[:4000]}\n```")
    user_parts.append(f"CURRENT SECTION HTML:\n```html\n{(current_html or '')[:14000]}\n```")
    user = "\n\n".join(user_parts)
    try:
        raw = await llm.generate_html(HTML_SECTION_SYSTEM, user)
        text = _clean(raw)
        start = text.lower().find("<section")
        end = text.lower().rfind("</section>")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + len("</section>")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("lesson_edit HTML rewrite failed: %s", exc)
        return None


async def rewrite_a2ui_section(
    *,
    section_id: str,
    title: str,
    current_root: dict,
    instruction: str,
) -> dict | None:
    """Rewrite one A2UI section root JSON — not the whole lesson doc."""
    llm = get_lesson_edit_llm()
    user = (
        f"Section id={section_id} title={title}\n"
        f"Edit instruction: {instruction}\n"
        f"CURRENT section root JSON (edit in place; minimal diff):\n"
        f"{json.dumps(current_root)[:8000]}\n"
        "Emit JSON {title, root} for the UPDATED section only."
    )
    try:
        raw = await llm.generate_html(A2UI_SECTION_SYSTEM, user)
        data = json.loads(_clean(raw))
        normalized = normalize_render_ui(
            {
                "title": data.get("title") or title,
                "intent": title,
                "root": data.get("root") or data,
            }
        )
        if normalized and normalized.get("root"):
            return normalized["root"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("lesson_edit A2UI rewrite failed: %s", exc)
    return None


async def author_catalogue_insert(*, node_type: str, hint: str = "") -> dict[str, Any] | None:
    """Author one allowlisted catalogue node for slash-insert."""
    t = (node_type or "").lower().strip()
    if t not in INSERTABLE_TYPES:
        return None
    llm = get_lesson_edit_llm()
    user = (
        f"Requested type: {t}\n"
        f"User hint: {hint or '(none — invent a small teaching example)'}\n"
        f"Emit ONLY one node JSON with type={t}."
    )
    try:
        raw = await llm.generate_html(A2UI_INSERT_SYSTEM, user)
        data = json.loads(_clean(raw))
        if isinstance(data, dict) and data.get("root"):
            data = data["root"]
        if isinstance(data, dict) and data.get("type") != t:
            data["type"] = t
        node = normalize_ui_node(data if isinstance(data, dict) else None)
        if node:
            return node
    except Exception as exc:  # noqa: BLE001
        logger.warning("lesson_edit catalogue insert failed (%s): %s", t, exc)
    return None

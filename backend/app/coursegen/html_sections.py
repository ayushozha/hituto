"""Surgical HTML section patch — splice one ``data-lesson-section`` fragment.

Used by Viewer targeted refine so sibling sections stay byte-stable
(specs/a2ui_surgical_edit).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..capsule.postprocess import postprocess

logger = logging.getLogger(__name__)

_SECTION_OPEN = re.compile(
    r"<section\b[^>]*\bdata-lesson-section\s*=\s*[\"']([^\"']+)[\"'][^>]*>",
    re.I,
)


def list_section_ids(html: str) -> list[str]:
    return [m.group(1) for m in _SECTION_OPEN.finditer(html or "")]


def extract_section_outer(html: str, section_id: str) -> str | None:
    """Return the outerHTML of the first matching section, or None."""
    if not html or not section_id:
        return None
    # Find opening tag for this id
    pat = re.compile(
        rf"(<section\b[^>]*\bdata-lesson-section\s*=\s*[\"']{re.escape(section_id)}[\"'][^>]*>)",
        re.I,
    )
    m = pat.search(html)
    if not m:
        return None
    start = m.start()
    # Walk forward counting nested <section> … </section>
    i = m.end()
    depth = 1
    lower = html.lower()
    while i < len(html) and depth > 0:
        next_open = lower.find("<section", i)
        next_close = lower.find("</section>", i)
        if next_close == -1:
            return None
        if next_open != -1 and next_open < next_close:
            depth += 1
            i = next_open + 8
        else:
            depth -= 1
            i = next_close + len("</section>")
            if depth == 0:
                return html[start:i]
    return None


def replace_section_outer(html: str, section_id: str, new_outer: str) -> str | None:
    old = extract_section_outer(html, section_id)
    if old is None:
        return None
    return html.replace(old, new_outer, 1)


def stamp_section_attrs(fragment: str, slug: str, title: str | None = None) -> str:
    """Ensure a <section> fragment carries data-lesson-section / id."""
    text = fragment.strip()
    if not text.lower().startswith("<section"):
        return (
            f'<section id="section-{slug}" data-lesson-section="{slug}" '
            f'data-section-id="{slug}"'
            + (f' data-lesson-title="{title}"' if title else "")
            + f">{text}</section>"
        )
    # Inject/replace attributes on the opening tag
    def _fix_open(m: re.Match[str]) -> str:
        tag = m.group(0)
        if re.search(r"\bdata-lesson-section\s*=", tag, re.I):
            tag = re.sub(
                r'\bdata-lesson-section\s*=\s*["\'][^"\']*["\']',
                f'data-lesson-section="{slug}"',
                tag,
                count=1,
                flags=re.I,
            )
        else:
            tag = tag[:-1] + f' data-lesson-section="{slug}">'
        if not re.search(r"\bdata-section-id\s*=", tag, re.I):
            tag = tag[:-1] + f' data-section-id="{slug}">'
        if not re.search(r"\bid\s*=", tag, re.I):
            tag = tag[:-1] + f' id="section-{slug}">'
        if title and not re.search(r"\bdata-lesson-title\s*=", tag, re.I):
            tag = tag[:-1] + f' data-lesson-title="{title}">'
        return tag

    return re.sub(r"<section\b[^>]*>", _fix_open, text, count=1, flags=re.I)


async def rewrite_html_section_with_instruction(
    *,
    section_id: str,
    current_html: str,
    instruction: str,
    target_snippet: str | None = None,
    sibling_style_hint: str | None = None,
) -> str | None:
    """LLM-rewrite one section via the lesson-edit agent; stamp attrs; None on failure."""
    from ..lesson_edit import rewrite_html_section

    fragment = await rewrite_html_section(
        section_id=section_id,
        current_html=current_html,
        instruction=instruction,
        target_snippet=target_snippet,
        sibling_style_hint=sibling_style_hint,
    )
    if not fragment:
        return None
    return stamp_section_attrs(fragment, section_id)


def splice_and_gate(full_html: str, section_id: str, new_section_html: str) -> tuple[str, dict[str, Any]] | None:
    """Replace one section in the document and run the capsule gate."""
    stamped = stamp_section_attrs(new_section_html, section_id)
    merged = replace_section_outer(full_html, section_id, stamped)
    if merged is None:
        return None
    gated, checks = postprocess(merged)
    return gated, checks

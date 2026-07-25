"""Per-kind plain-text digesters for lesson surfaces (specs/design_agents §6).

Absorbs the old ``tutor/digest.py`` (which now re-exports from here) and adds digesters
for artifact kinds the HTML-only path grounded on nothing: A2UI trees (whose artifacts
store ``html=""`` — the voice empty-digest bug) and video guides.
"""
from __future__ import annotations

import re
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
ARTIFACT_DIGEST_CHARS = 4000

# Structural / non-content props that would only add noise to a grounding digest.
_A2UI_SKIP_KEYS = frozenset(
    {"type", "id", "kind", "variant", "icon", "color", "size", "align", "href", "src"}
)


def html_to_text(html: str, limit: int = ARTIFACT_DIGEST_CHARS) -> str:
    """Strip tags/scripts/styles from artifact HTML down to a capped plain-text digest."""
    if not html:
        return ""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = _TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit]


def a2ui_to_text(doc: dict | None, limit: int = ARTIFACT_DIGEST_CHARS) -> str:
    """Walk a validated A2UI document collecting human-readable text content."""
    if not doc:
        return ""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if sum(len(p) for p in parts) > limit * 2:
            return
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in _A2UI_SKIP_KEYS:
                    continue
                walk(value)

    for top in ("title", "intent"):
        value = doc.get(top)
        if isinstance(value, str):
            parts.append(value)
    walk(doc.get("root") or {})
    text = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return _WS_RE.sub(" ", text).strip()[:limit]


def reading_to_text(doc: dict | None, limit: int = ARTIFACT_DIGEST_CHARS) -> str:
    """Digest a ReadingDoc: intent + per-section objective, notes, and prose head."""
    if not doc:
        return ""
    parts: list[str] = [str(doc.get("title") or ""), str(doc.get("intent") or "")]
    for section in doc.get("sections") or []:
        parts.append(str(section.get("title") or ""))
        parts.append(str(section.get("objective") or ""))
        parts.append(str(section.get("body_md") or "")[:400])
        for note in section.get("notes") or []:
            parts.append(str(note.get("text") or ""))
    for term in doc.get("glossary") or []:
        parts.append(f"{term.get('term')}: {term.get('definition')}")
    text = " ".join(p.strip() for p in parts if p and p.strip())
    return _WS_RE.sub(" ", text).strip()[:limit]


def video_guide_to_text(video: dict | None, limit: int = ARTIFACT_DIGEST_CHARS) -> str:
    """Digest a source_map['video'] block: checkpoint titles/prompts in order."""
    if not video:
        return ""
    parts: list[str] = []
    for checkpoint in video.get("checkpoints") or []:
        if not isinstance(checkpoint, dict):
            continue
        for value in checkpoint.values():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return _WS_RE.sub(" ", " ".join(parts)).strip()[:limit]


_SECTION_RE = re.compile(
    r"<section\b[^>]*\bdata-lesson-section=[\"']([^\"']+)[\"'][^>]*>",
    re.I,
)
_SECTION_TITLE_RE = re.compile(r"\bdata-lesson-title=[\"']([^\"']*)[\"']", re.I)


def html_outline(html: str) -> list[tuple[str, str]]:
    """(section_id, title) pairs from data-lesson-section markup, in document order."""
    if not html:
        return []
    outline: list[tuple[str, str]] = []
    for match in _SECTION_RE.finditer(html):
        title_match = _SECTION_TITLE_RE.search(match.group(0))
        outline.append((match.group(1), title_match.group(1) if title_match else ""))
    return outline

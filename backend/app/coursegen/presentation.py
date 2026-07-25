"""Resolve capsule presentation (studio / page / slide / reading / game) from knobs + plan."""
from __future__ import annotations

import re
from typing import Any

_SPATIAL_RE = re.compile(
    r"\b(cell|organelle|membrane|anatomy|molecule|protein|atom|circuit|machine|"
    r"cross-?section|3d|three-?d|spatial|organ|tissue|neuron|bacteria)\b",
    re.I,
)


def resolve_presentation(plan: dict[str, Any] | None = None, knobs: dict[str, Any] | None = None) -> str:
    """Return concrete design mode / capsule shell: studio | page | slide | reading | game.

    Explicit knobs/plan win. ``auto`` picks studio for spatial/3D lessons, game for
    ``archetype=game`` when flag-gated, reading for prose-heavy document-grounded
    chapters (flag-gated), else page. Reads ``design_mode`` (preferred) or legacy
    ``presentation``.
    """
    from ..core.config import get_settings

    plan = plan or {}
    knobs = knobs or {}
    settings = get_settings()
    reading_enabled = settings.reading_design_enabled
    game_enabled = settings.game_design_enabled
    raw = (
        plan.get("design_mode")
        or plan.get("presentation")
        or knobs.get("design_mode")
        or knobs.get("presentation")
        or "auto"
    )
    raw = str(raw).strip().lower()
    if raw in ("studio", "page", "slide"):
        return raw
    if raw == "reading":
        # Fail closed to page when the design is off or there is nothing to read.
        return "reading" if reading_enabled and plan.get("source_pack") else "page"
    if raw == "game":
        return "game" if game_enabled else "page"

    archetype = str(plan.get("archetype") or knobs.get("archetype") or "").lower()
    # Prefer the game gallery over Studio when the lesson is explicitly a mini-game.
    if game_enabled and archetype == "game":
        return "game"

    if plan.get("needs_3d") or knobs.get("needs_3d") is True:
        return "studio"

    hay = " ".join(
        str(x)
        for x in (
            plan.get("title"),
            plan.get("subtitle"),
            knobs.get("subject"),
            plan.get("topic"),
        )
        if x
    )
    if _SPATIAL_RE.search(hay):
        return "studio"
    if (
        reading_enabled
        and plan.get("source_pack")
        and archetype in ("explainer", "narrative")
    ):
        return "reading"
    return "page"


def knobs_design_mode(knobs: dict[str, Any] | None) -> str:
    """Return the requested design mode from course knobs (design_mode or legacy presentation)."""
    knobs = knobs or {}
    return str(knobs.get("design_mode") or knobs.get("presentation") or "auto").strip().lower() or "auto"

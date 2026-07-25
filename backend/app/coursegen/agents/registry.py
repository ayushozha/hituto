"""Subject specialist registry — topic → specialist routing (maths + science).

Other subjects (advanced-maths, chemistry, history, health) can be added later
via registry entries + skills; unmatched topics use role subagents only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Specialist:
    name: str
    subjects: tuple[str, ...]
    description: str
    extra_tools: tuple[str, ...] = ()
    match: Callable[[str], bool] | None = None


def _maths_match(topic: str) -> bool:
    t = (topic or "").lower()
    return bool(
        re.search(
            r"\b(math|algebra|calculus|geometry|trigonometry|probability|statistics|"
            r"linear algebra|derivative|integral|equation|matrix|vector)\b",
            t,
        )
    )


def _science_match(topic: str) -> bool:
    t = (topic or "").lower()
    return bool(
        re.search(
            r"\b(physics|biology|chemistry|science|mechanics|optics|thermodynamics|"
            r"genetics|ecology|astronomy|force|energy|atom|molecule|cell)\b",
            t,
        )
    )


SPECIALISTS: list[Specialist] = [
    Specialist(
        name="maths-specialist",
        subjects=("maths",),
        description="Math pedagogy, KaTeX checks, symbolic clarity.",
        extra_tools=("check_katex",),
        match=_maths_match,
    ),
    Specialist(
        name="science-specialist",
        subjects=("science",),
        description="Science pedagogy, lab/viz guidance.",
        extra_tools=("run_viz_lab", "run_simulation", "generate_mesh"),
        match=_science_match,
    ),
]


def resolve_specialist(topic: str, *, subject_knob: str | None = None) -> Specialist | None:
    """Return the first matching specialist, or None (role subagents only)."""
    if subject_knob:
        key = subject_knob.strip().lower().replace("_", "-")
        for s in SPECIALISTS:
            if key in s.subjects or key == s.name:
                return s
    for s in SPECIALISTS:
        if s.match and s.match(topic or ""):
            return s
    return None

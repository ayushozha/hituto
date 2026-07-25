"""Deterministic subject validators (Phase 2.8 stubs)."""
from __future__ import annotations

import re


_KATEX_FORBIDDEN = re.compile(r"[<>]|\\write|\\input|\\include")


def check_katex(latex: str) -> dict:
    """Lightweight KaTeX safety/shape check — not a full TeX parser.

    Returns {passed, failed, normalized}.
    """
    failed: list[str] = []
    text = (latex or "").strip()
    if not text:
        failed.append("empty latex")
    if len(text) > 4000:
        failed.append("latex too long")
    if _KATEX_FORBIDDEN.search(text):
        failed.append("forbidden latex token")
    # Unbalanced $ or \\( \\) is a soft signal only for display math wrappers.
    if text.count("$") % 2 != 0:
        failed.append("unbalanced $ delimiters")
    return {"passed": not failed, "failed": failed, "normalized": text}


_ELEM = re.compile(r"([A-Z][a-z]?)(\d*)")


def _atom_counts(side: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    # Strip coefficients like "2H2O" → rough parse of element tokens only.
    for m in _ELEM.finditer(side.replace(" ", "")):
        el, n = m.group(1), m.group(2)
        counts[el] = counts.get(el, 0) + (int(n) if n else 1)
    return counts


def balance_equation(left: str, right: str) -> dict:
    """Stub chemical-equation balance check by element counts (ignores coefficients).

    Real balancing lands with the chemistry specialist; this catches obvious mismatches.
    """
    failed: list[str] = []
    if not (left or "").strip() or not (right or "").strip():
        return {"passed": False, "failed": ["empty side"], "left": {}, "right": {}}
    l_counts = _atom_counts(left)
    r_counts = _atom_counts(right)
    if not l_counts or not r_counts:
        failed.append("could not parse elements")
    keys = set(l_counts) | set(r_counts)
    for k in keys:
        if l_counts.get(k, 0) != r_counts.get(k, 0):
            failed.append(f"element {k}: left={l_counts.get(k, 0)} right={r_counts.get(k, 0)}")
    return {"passed": not failed, "failed": failed, "left": l_counts, "right": r_counts}

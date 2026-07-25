"""Grounding validation (tasks.md #34, #37).

Deterministic, offline-testable checks over a source-grounded artifact: citation coverage,
foreign citations, and verbatim-copy detection (R7, R9.3). Plus a repair brief fed back into the
bounded generate->validate loop. The model-assisted unsupported-claim reviewer (#35) and
quiz/formula support checks (#36) layer on top once generate_json (MiniMax) lands.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Citation markers the grounded prompt asks for, e.g. [S1a2b3c4d p.3 ...]
_CITE_RE = re.compile(r"\[S([0-9a-fA-F]{6,})\b")
_COPY_WINDOW_WORDS = 18  # a verbatim run this long (≈a sentence) counts as a copied passage


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text or "")).lower().strip()


def check_grounding(html: str, source_pack: list[dict], citations: list[dict] | None = None) -> dict:
    """Deterministic grounding verdict. `failed` lists hard violations (block + retry)."""
    failed: list[str] = []
    pack_ids = {p.get("id") for p in source_pack if p.get("id")}
    pack_ids_lower = {p.lower() for p in pack_ids}
    norm_html = _norm(html)

    if not source_pack:
        failed.append("empty source pack")

    # Citation coverage — how many provided source ids are actually referenced.
    cited = {pid for pid in pack_ids if pid and pid.lower() in norm_html}
    citation_count = len(cited)
    if pack_ids and citation_count == 0:
        failed.append("no source citations")

    # Foreign citations — [S<id>] markers that match no provided source id.
    foreign = sorted({m for m in _CITE_RE.findall(html or "") if pack_ids and m.lower() not in pack_ids_lower})
    if foreign:
        failed.append(f"foreign citation(s): {', '.join(foreign[:3])}")

    # Copied passages — a long verbatim run lifted from any chunk (no long verbatim, R9.3).
    copied: list[str] = []
    for p in source_pack:
        words = _norm(p.get("text", "")).split()
        for i in range(0, max(0, len(words) - _COPY_WINDOW_WORDS) + 1, _COPY_WINDOW_WORDS):
            window = " ".join(words[i : i + _COPY_WINDOW_WORDS])
            if len(window) > 80 and window in norm_html:
                copied.append(p.get("id"))
                break
    if copied:
        failed.append(f"copied passage from {', '.join(str(c) for c in copied[:3])}")

    return {
        "passed": not failed,
        "failed": failed,
        "citation_count": citation_count,
        "cited_ids": sorted(cited),
        "foreign": foreign,
        "copied": [c for c in copied if c],
        "unsupported_claims": [],  # populated by the model reviewer (#35) when available
    }


def build_repair_brief(grounding: dict) -> str:
    """Turn a failed grounding verdict into a concise repair instruction for the next attempt."""
    failed = grounding.get("failed", [])
    parts: list[str] = []
    if "no source citations" in failed:
        parts.append("Cite the provided source excerpts inline using [S<id> p.<page>] markers.")
    if any(f.startswith("foreign citation") for f in failed):
        parts.append("Remove citations that don't match a provided source id; cite only given excerpts.")
    if any(f.startswith("copied passage") for f in failed):
        parts.append("Do NOT copy source text verbatim — paraphrase the idea and cite it instead.")
    if "empty source pack" in failed:
        parts.append("State that source coverage is insufficient rather than inventing content.")
    unsupported = grounding.get("unsupported_claims") or []
    if unsupported:
        parts.append(
            "Remove or qualify these unsupported claims (cite a source excerpt for each): "
            + "; ".join(unsupported[:5])
            + "."
        )
    answers = grounding.get("unsupported_answers") or []
    if answers:
        parts.append(
            "Correct these quiz answers / formulas / code outputs to match the source (or cite one): "
            + "; ".join(answers[:5])
            + "."
        )
    return " ".join(parts) or "Improve source grounding and add [S<id> p.<page>] citations."


class GroundingReview(BaseModel):
    """Structured output of the model-assisted reviewer (tasks.md #35, #36)."""

    unsupported_claims: list[str] = []
    # quiz answers, formulas/equations, or code expected-outputs not supported by the source (#36)
    unsupported_answers: list[str] = []
    notes: str = ""


async def review_grounding(html: str, source_pack: list[dict]) -> GroundingReview:
    """Model-assisted unsupported-claim review via generate_json (tasks.md #35).

    Returns an empty review (no-op) on the offline stub or any failure — it never blocks
    generation, it only feeds soft findings into the bounded repair loop / low-confidence badge.
    """
    from ..providers.registry import get_coursegen_review_llm

    if not source_pack:
        return GroundingReview()
    excerpts = "\n\n".join(f"[S{p.get('id')}] {(p.get('text') or '')[:600]}" for p in source_pack)
    system = (
        "You are a strict fact-checker for a learning lesson grounded in a source document. Given the "
        "SOURCE EXCERPTS and the LESSON TEXT:\n"
        "- `unsupported_claims`: substantive factual claims (definitions, results, numbers) NOT "
        "supported by the excerpts. Ignore pedagogical framing, transitions, and generic advice.\n"
        "- `unsupported_answers`: any quiz answers, formulas/equations, or code expected-outputs in "
        "the lesson that contradict or aren't supported by the excerpts.\n"
        "Be precise and conservative — only flag things you are confident are unsupported."
    )
    user = f"SOURCE EXCERPTS:\n{excerpts}\n\nLESSON TEXT:\n{_norm(html)[:6000]}"
    try:
        return await get_coursegen_review_llm().generate_json(system, user, GroundingReview)
    except Exception:
        return GroundingReview()

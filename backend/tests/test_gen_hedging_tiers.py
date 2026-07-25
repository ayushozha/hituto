"""fast_gen Phase 6 (hedged retries) and Phase 7 (per-stage model tiers)."""
from app.core.config import get_settings
from app.coursegen.designs import page


class _HedgeLLM:
    """Repair-prompted calls (marked by the repair suffix) return one output; fresh
    rewrites another. Lets tests steer which branch passes the gate."""

    def __init__(self, repair_out: str, fresh_out: str, repair_raises: bool = False):
        self.repair_out = repair_out
        self.fresh_out = fresh_out
        self.repair_raises = repair_raises

    async def generate_html(self, system: str, user: str, on_delta=None) -> str:
        if "REPAIR ATTEMPT" in user:
            if self.repair_raises:
                raise RuntimeError("repair branch exploded")
            return self.repair_out
        return self.fresh_out


async def test_hedged_repair_picks_the_gate_passing_candidate(monkeypatch) -> None:
    monkeypatch.setattr(page, "postprocess", lambda h: (h, {"passed": "GOOD" in h}))
    llm = _HedgeLLM(repair_out="BAD page", fresh_out="GOOD page")
    out = await page._hedged_repair(llm, "user --- REPAIR ATTEMPT 2 ---", "user", None, None)
    assert out == "GOOD page"


async def test_hedged_repair_prefers_repair_when_both_pass(monkeypatch) -> None:
    monkeypatch.setattr(page, "postprocess", lambda h: (h, {"passed": "GOOD" in h}))
    llm = _HedgeLLM(repair_out="GOOD repair", fresh_out="GOOD fresh")
    out = await page._hedged_repair(llm, "user --- REPAIR ATTEMPT 2 ---", "user", None, None)
    assert out == "GOOD repair"


async def test_hedged_repair_survives_a_crashed_branch(monkeypatch) -> None:
    monkeypatch.setattr(page, "postprocess", lambda h: (h, {"passed": True}))
    llm = _HedgeLLM(repair_out="", fresh_out="GOOD fresh", repair_raises=True)
    out = await page._hedged_repair(llm, "user --- REPAIR ATTEMPT 2 ---", "user", None, None)
    assert out == "GOOD fresh"


async def test_hedged_repair_keeps_repair_when_neither_passes(monkeypatch) -> None:
    monkeypatch.setattr(page, "postprocess", lambda h: (h, {"passed": False}))
    llm = _HedgeLLM(repair_out="repair try", fresh_out="fresh try")
    out = await page._hedged_repair(llm, "user --- REPAIR ATTEMPT 2 ---", "user", None, None)
    assert out == "repair try"  # loop's exhaustion logic stays in charge


def test_planner_and_review_tiers_fall_back_through_coursegen(monkeypatch) -> None:
    # Pin every layer explicitly — the developer's backend/.env may set COURSEGEN_LLM_*,
    # which pydantic-settings reads even when the process env var is deleted.
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "big-author-model")
    monkeypatch.setenv("COURSEGEN_LLM_MODEL", "mid-coursegen-model")
    monkeypatch.setenv("COURSEGEN_PLANNER_LLM_MODEL", "small-planner-model")
    monkeypatch.setenv("COURSEGEN_REVIEW_LLM_MODEL", "")
    get_settings.cache_clear()
    try:
        from app.providers.registry import (
            get_coursegen_llm,
            get_coursegen_planner_llm,
            get_coursegen_review_llm,
        )

        assert get_coursegen_planner_llm().model == "small-planner-model"
        # No review override → falls through the coursegen tier.
        assert get_coursegen_review_llm().model == "mid-coursegen-model"
        assert get_coursegen_llm().model == "mid-coursegen-model"
    finally:
        get_settings.cache_clear()

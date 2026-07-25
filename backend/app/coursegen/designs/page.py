"""Page design agent (specs/design_agents §3): the HTML/A2UI capsule author.

Covers the ``page`` and ``slide`` shells and serves as the universal fallback design.
Authoring strategy, in preference order (each fail-closed to the next):

1. Section fan-out (fast_gen §4.2) — parallel per-section HTML streamed into the
   shell iframe (SVG/canvas-first), assembled against the server-owned document shell.
2. A2UI document (opt-in ``COURSEGEN_A2UI_LESSONS``) — trusted tree for eligible
   archetypes when HTML fan-out did not run or failed.
3. Whole-document HTML — streaming Mode B; repair attempts optionally hedge a
   repair-prompted generation against a fresh rewrite (fast_gen §2.4).
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from ...capsule.postprocess import postprocess
from ...core.config import get_settings
from ..prompt import SYSTEM, build_generation_repair_suffix, build_user_prompt
from ..sections import author_sections, sections_eligible
from .base import AuthorContext, DesignOutput

logger = logging.getLogger(__name__)


async def _hedged_repair(llm, repair_user: str, fresh_user: str, stream_cb, emit) -> str:
    """fast_gen §2.4 (GEN_HEDGED_RETRIES): race the repair-prompted attempt against a
    fresh rewrite; the deterministic capsule gate picks the winner. The full gate (and
    Playwright/grounding) still runs on the winner in post_process — this selection only
    avoids burning a whole serial round-trip on a repair that was going to fail anyway.
    Streaming follows the repair branch only, so the theater shows one coherent stream.
    """

    async def _run(user: str, cb) -> str:
        if cb is not None:
            out = await llm.generate_html(SYSTEM, user, on_delta=cb.on_delta)
            await cb.flush(final=True)
            return out
        return await llm.generate_html(SYSTEM, user)

    repair_res, fresh_res = await asyncio.gather(
        _run(repair_user, stream_cb),
        _run(fresh_user, None),
        return_exceptions=True,
    )
    candidates: list[tuple[str, str]] = []
    for res, label in ((repair_res, "repair"), (fresh_res, "fresh")):
        if isinstance(res, BaseException):
            logger.warning("hedged %s attempt failed: %s", label, res)
        elif res:
            candidates.append((res, label))
    if not candidates:
        if isinstance(repair_res, BaseException):
            raise repair_res
        raise RuntimeError("hedged repair produced no candidates")
    for res, label in candidates:
        try:
            _, checks = postprocess(res)
        except Exception:  # noqa: BLE001 — selection only; post_process is authoritative
            continue
        if checks.get("passed"):
            if emit is not None:
                await emit("generating", f"Repair race won by the {label} attempt", 72)
            return res
    return candidates[0][0]  # neither passed the quick gate — keep repair; loop decides


class PageAgent:
    mode = "page"

    async def author(self, ctx: AuthorContext) -> DesignOutput:
        settings = get_settings()
        plan = ctx.plan
        state = ctx.state
        attempt = ctx.attempt
        archetype = plan.get("archetype") or ctx.knobs.get("archetype") or "explainer"

        # 1) HTML section fan-out — live gen_fragment streaming (default path).
        if attempt == 1 and sections_eligible(plan, state):
            await ctx.progress("generating", "Authoring sections in parallel…", 60)

            async def _section_done(slug: str, ok: bool) -> None:
                if not ok:
                    await ctx.progress(
                        "generating", f"(section '{slug}' used draft fallback)", 68
                    )

            try:
                html = await author_sections(
                    plan=plan,
                    llm=ctx.llm,
                    streamer_factory=ctx.streamer_factory,
                    on_section_done=_section_done,
                )
            except Exception as exc:  # noqa: BLE001 — fall back to next strategy
                logger.warning("section fan-out failed; falling back: %s", exc)
                html = None
            if html:
                return DesignOutput(kind="html", html=html, plan=plan)
            await ctx.progress(
                "generating", "Section fan-out unavailable — trying next author path…", 58
            )

        # 2) Opt-in A2UI (COURSEGEN_A2UI_LESSONS) when HTML fan-out did not produce a doc.
        from ..agents.roles.capsule_author import a2ui_eligible, author_a2ui_lesson
        from ..a2ui_sections import a2ui_sections_eligible, author_a2ui_sections

        if a2ui_eligible(str(archetype), enabled=settings.coursegen_a2ui_lessons):
            await ctx.progress("generating", f"Authoring A2UI lesson (attempt {attempt})…", 60)
            if attempt == 1 and a2ui_sections_eligible(plan, state):

                async def _a2ui_section_done(slug: str, ok: bool) -> None:
                    if not ok:
                        await ctx.progress(
                            "generating", f"(A2UI section '{slug}' used draft fallback)", 68
                        )

                try:
                    doc = await author_a2ui_sections(
                        plan=plan,
                        course_id=ctx.course_id,
                        lesson_id=ctx.lesson_id,
                        attempt=attempt,
                        on_section_done=_a2ui_section_done,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("A2UI section fan-out failed: %s", exc)
                    doc = None
                if doc:
                    return DesignOutput(kind="a2ui", a2ui=doc, html="", plan=plan)
            doc = await author_a2ui_lesson(plan)
            if doc:
                return DesignOutput(kind="a2ui", a2ui=doc, html="", plan=plan)
            await ctx.progress("generating", "A2UI authoring failed — falling back to HTML…", 58)

        # 3) Whole-document HTML (Mode B stream / hedged repair).
        await ctx.progress("generating", f"Generating lesson HTML (attempt {attempt})…", 60)
        plan_for_prompt = dict(plan)
        if state.get("target_html"):
            plan_for_prompt["target_id"] = state.get("target_id")
            plan_for_prompt["target_html"] = state.get("target_html")
        user = build_user_prompt(plan_for_prompt, state.get("previous_html"))
        repair = state.get("grounding_repair")
        if repair:
            user += f"\n\nGROUNDING REPAIR (fix these from the prior attempt): {repair}"
        fresh_user = user  # keeps grounding guidance, drops the prior-HTML repair suffix
        is_repair = attempt > 1 and bool(state.get("html"))
        if is_repair:
            failed = state.get("checks", {}).get("failed", [])
            user += build_generation_repair_suffix(state["html"], failed, attempt)

        stream_cb = ctx.streamer_factory(None) if ctx.streamer_factory else None
        supports_stream = "on_delta" in inspect.signature(ctx.llm.generate_html).parameters
        if is_repair and settings.gen_hedged_retries:
            html = await _hedged_repair(
                ctx.llm, user, fresh_user, stream_cb if supports_stream else None, ctx.emit
            )
        elif stream_cb is not None and supports_stream:
            html = await ctx.llm.generate_html(SYSTEM, user, on_delta=stream_cb.on_delta)
            await stream_cb.flush(final=True)
        else:
            html = await ctx.llm.generate_html(SYSTEM, user)
        return DesignOutput(kind="html", html=html, plan=plan)

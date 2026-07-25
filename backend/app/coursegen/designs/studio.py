"""Studio design agent (specs/design_agents §3): deterministic manifest → templates.

No LLM here — the plan (already prepared by ``prepare_studio_plan`` in asset_plan)
fills a validated :class:`StudioManifest`, rendered through server-owned templates.
The manifest/renderer/catalog modules stay at their current paths for now; this agent
is the dispatch seam the folder moves can happen behind later.
"""
from __future__ import annotations

from .base import AuthorContext, DesignOutput


class StudioAgent:
    mode = "studio"

    async def author(self, ctx: AuthorContext) -> DesignOutput:
        from ..studio_manifest import build_studio_manifest
        from ..studio_renderer import render_studio_manifest

        await ctx.progress("generating", f"Building Studio v2 (attempt {ctx.attempt})…", 60)
        manifest = build_studio_manifest(ctx.plan, ctx.knobs)
        plan = {
            **ctx.plan,
            "studio_mode": manifest.mode,
            "studio_manifest": manifest.model_dump(),
        }
        return DesignOutput(kind="html", html=render_studio_manifest(manifest), plan=plan)

"""Game design agent: deterministic GameManifest → server template.

No LLM HTML — mirrors Studio. Invalid/failed builds fall closed to the page agent.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from .base import AuthorContext, DesignOutput

logger = logging.getLogger(__name__)


class GameAgent:
    mode = "game"

    async def author(self, ctx: AuthorContext) -> DesignOutput:
        from ..game_manifest import build_game_manifest
        from ..game_renderer import render_game_manifest

        await ctx.progress("generating", f"Building game stage (attempt {ctx.attempt})…", 60)
        try:
            manifest = build_game_manifest(ctx.plan, ctx.knobs)
            html = render_game_manifest(manifest)
        except (ValidationError, ValueError, OSError) as exc:
            logger.warning("game design failed closed to page: %s", exc)
            from .page import PageAgent

            return await PageAgent().author(ctx)

        plan = {
            **ctx.plan,
            "presentation": "game",
            "archetype": "game",
            "game_mode": manifest.mode,
            "game_manifest": manifest.model_dump(),
        }
        return DesignOutput(kind="html", html=html, plan=plan)

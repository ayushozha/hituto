"""Design-family agent registry (specs/design_agents §4-5).

``get_design_agent(mode)`` maps a resolved design mode to its authoring agent.
Unknown modes fall back to the page agent — the universal renderer — mirroring the
pipeline's fail-closed rule. ``resolve_presentation`` (``coursegen/presentation.py``)
remains the single router that produces the mode.
"""
from __future__ import annotations

from .base import AuthorContext, DesignAgent, DesignOutput
from .game import GameAgent
from .page import PageAgent
from .reading import ReadingAgent
from .studio import StudioAgent

__all__ = [
    "AuthorContext",
    "DesignAgent",
    "DesignOutput",
    "GameAgent",
    "PageAgent",
    "ReadingAgent",
    "StudioAgent",
    "get_design_agent",
]

_PAGE = PageAgent()
_REGISTRY: dict[str, DesignAgent] = {
    "page": _PAGE,
    "slide": _PAGE,  # a slide is a capsule shell variant, not an authoring strategy
    "studio": StudioAgent(),
    "reading": ReadingAgent(),
    "game": GameAgent(),
}


def get_design_agent(mode: str | None) -> DesignAgent:
    return _REGISTRY.get(str(mode or "").strip().lower(), _PAGE)

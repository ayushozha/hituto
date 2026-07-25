"""LangSmith Studio / Agent Server graph factories.

Used by ``langgraph.json`` + ``langgraph dev`` so Studio can connect to the
local Agent Server (default ``http://127.0.0.1:2024``).

See: https://docs.langchain.com/oss/python/langgraph/studio
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.tracing import configure_tracing
from app.coursegen.state import GenState
from app.tutor.agent import build_tutor_graph


def _wire_coursegen(g: StateGraph) -> None:
    """Same topology as ``coursegen.graph.build_graph`` (no checkpointer)."""
    from app.coursegen.graph import (
        _after_post,
        asset_plan,
        generate,
        interpret,
        persist,
        post_process,
        research,
    )

    g.add_node("interpret", interpret)
    g.add_node("research", research)
    g.add_node("asset_plan", asset_plan)
    g.add_node("generate", generate)
    g.add_node("post_process", post_process)
    g.add_node("persist", persist)

    g.add_edge(START, "interpret")
    g.add_edge("interpret", "research")
    g.add_edge("research", "asset_plan")
    g.add_edge("asset_plan", "generate")
    g.add_edge("generate", "post_process")
    g.add_conditional_edges(
        "post_process", _after_post, {"generate": "generate", "persist": "persist"}
    )
    g.add_edge("persist", END)


async def make_coursegen_graph(_config: dict[str, Any] | None = None):
    """Compiled coursegen graph for Studio (Agent Server owns the checkpointer)."""
    configure_tracing()
    g = StateGraph(GenState)
    _wire_coursegen(g)
    return g.compile()


def make_tutor_graph(_config: dict[str, Any] | None = None):
    """Compiled tutor graph for Studio."""
    configure_tracing()
    return build_tutor_graph()

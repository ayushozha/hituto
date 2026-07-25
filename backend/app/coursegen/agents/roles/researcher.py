"""researcher subagent — gathers grounded facts for a lesson (coursegen-agent §4)."""
from __future__ import annotations


def researcher_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: a web-search researcher (subject skills layered in later)."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import web_search

    return {
        "name": "researcher",
        "description": "Gather grounded, citable facts about the lesson topic via web search.",
        "system_prompt": load_agent_prompt(
            "researcher",
            "You are the researcher. Use web_search to gather 3-6 grounded facts for the lesson. "
            "Return a concise fact list with source URLs; never invent citations or page numbers.",
        ),
        "tools": [web_search],
    }

"""viz_engineer subagent — server-side plots/traces via the sandbox (coursegen-agent §4)."""
from __future__ import annotations


def viz_engineer_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: runs the viz lab and writes the compute manifest."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import run_viz_lab_tool

    return {
        "name": "viz_engineer",
        "description": "Run the visualization lab and write /build/compute/manifest.json.",
        "system_prompt": load_agent_prompt(
            "viz_engineer",
            "You are the viz engineer. Optionally read /build/dataset.json, call run_viz_lab_tool "
            "for the concept, and write the returned manifest JSON to /build/compute/manifest.json. "
            "Plots run server-side and the capsule embeds them as images — never run Python in the "
            "learner iframe.",
        ),
        "tools": [run_viz_lab_tool],
    }

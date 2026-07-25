"""animation_coder subagent — authors 2D canvas animation modules (course-authoring-flow §5).

The coder WRITES JavaScript; it never executes it. Its output runs only inside the
CSP-locked sandboxed lesson iframe after the capsule gate. Heavy math is precomputed
server-side via `run_viz_lab` (Python) and embedded as data — never computed live.
"""
from __future__ import annotations


def animation_coder_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: writes animation modules to /build/anim/*.js."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import capsule_checks, run_viz_lab_tool

    return {
        "name": "animation_coder",
        "description": (
            "Write self-contained 2D <canvas> animation modules (requestAnimationFrame, "
            "parameter-driven) to /build/anim/<name>.js for the capsule author to inline."
        ),
        "system_prompt": load_agent_prompt(
            "animation_coder",
            "You are the animation coder. Write ONE self-contained vanilla-JS module per "
            "animation to /build/anim/<name>.js via write_file. Contract: define "
            "`function initAnim(canvas, controls)` that starts a requestAnimationFrame loop, "
            "reads parameters from the passed controls, and supports pause/reset. Rules: no "
            "external libraries or imports; deterministic given the same inputs; if the "
            "animation needs computed data, call run_viz_lab (server-side Python) and embed "
            "the returned values as constants — never compute heavy math per-frame; never use "
            "window.parent, window.top, localStorage, fetch, or eval. The capsule author "
            "inlines your module into a <script> block, so it must be plain browser JS.",
        ),
        "tools": [run_viz_lab_tool, capsule_checks],
    }

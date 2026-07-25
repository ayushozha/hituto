"""Subject specialist subagents for the lesson Deep Agent (coursegen-agent §6).

A specialist is consulted for plan review + domain QA. Its registry `extra_tools` names are bound
to real @tools here, and its guidance comes from prompts/agents/<subject>_specialist.md.
"""
from __future__ import annotations


def specialist_subagent(spec) -> dict:
    """Build a Deep Agent subagent dict from a registry `Specialist`."""
    from .prompt_loader import load_agent_prompt
    from .tools import tool_by_name

    subject = spec.subjects[0] if spec.subjects else "general"
    tools = [t for t in (tool_by_name(n) for n in spec.extra_tools) if t is not None]
    return {
        "name": spec.name.replace("-", "_"),
        "description": spec.description,
        "system_prompt": load_agent_prompt(
            f"{subject}_specialist",
            f"You are the {spec.name}. Review the lesson plan and the authored capsule for {subject} "
            "accuracy and pedagogy, using your tools to verify claims. Advise the author with specific "
            "corrections; do not rewrite the capsule yourself.",
        ),
        "tools": tools,
    }


def routed_specialist_subagent(topic: str, subject_knob: str | None = None) -> dict | None:
    """Return the specialist subagent for a topic, or None when no specialist matches."""
    from .registry import resolve_specialist

    spec = resolve_specialist(topic, subject_knob=subject_knob)
    return specialist_subagent(spec) if spec else None

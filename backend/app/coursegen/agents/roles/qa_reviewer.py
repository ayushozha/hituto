"""qa_reviewer subagent — validates the authored capsule (coursegen-agent §4)."""
from __future__ import annotations


def qa_reviewer_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: runs the capsule security + quality gate and reports."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import capsule_checks

    return {
        "name": "qa_reviewer",
        "description": "Validate the authored capsule against the security + quality gate.",
        "system_prompt": load_agent_prompt(
            "qa_reviewer",
            "You are the QA reviewer. Read /build/capsule.html, run capsule_checks on its content, "
            "and report whether it passed. If it failed, list the specific problems for the author "
            "to fix. Do not rewrite the capsule yourself.",
        ),
        "tools": [capsule_checks],
    }

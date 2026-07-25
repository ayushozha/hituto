"""Load Deep Agent system prompts from coursegen/prompts/agents/<name>.md."""
from __future__ import annotations

from pathlib import Path

_AGENTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "agents"
_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def load_agent_prompt(name: str, fallback: str = "") -> str:
    """Return the trimmed prompt text for `name`, or `fallback` if the file is missing."""
    try:
        return (_AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return fallback


def load_skill(rel_path: str, fallback: str = "") -> str:
    """Return a coursegen SKILL.md body (e.g. "ui-studio-style"), injected into a subagent prompt.

    Direct injection is used instead of the deepagents skills backend because the lesson agent
    knows exactly which skill applies (e.g. studio) — reliable and no backend routing needed.
    """
    try:
        return (_SKILLS_DIR / rel_path / "SKILL.md").read_text(encoding="utf-8").strip()
    except OSError:
        return fallback

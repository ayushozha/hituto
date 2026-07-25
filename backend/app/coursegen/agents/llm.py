"""Shared LangChain chat-model factory for coursegen Deep Agents.

The coursegen provider getter returns a custom `OpenAICompatLLM` (generate_html /
generate_json), which is NOT a LangChain `BaseChatModel`. Deep Agents need a real
chat model, so orchestrator + syllabus planner build one via this factory. Tests
monkeypatch `chat_model` to return `tests.fakes.FakeChatModel`.

Tiering (env-driven):
- heavy=True  → COURSEGEN_LLM_* (fallback LLM_*) — orchestrator, researcher,
  capsule_author, qa_reviewer
- heavy=False → LLM_* — other role/specialist subagents
"""
from __future__ import annotations

from ...core.config import get_settings

# Subagents that share the heavy/thinking model with the orchestrator.
_HEAVY_SUBAGENT_NAMES = frozenset({"researcher", "capsule_author", "qa_reviewer"})


def chat_model(*, heavy: bool = False):
    """OpenAI-compatible `ChatOpenAI` for coursegen Deep Agents (env-configured)."""
    from langchain_openai import ChatOpenAI

    s = get_settings()
    if heavy:
        model = s.resolved_coursegen_llm_model()
        base_url = s.resolved_coursegen_llm_base_url()
        api_key = s.resolved_coursegen_llm_api_key()
        key_hint = "COURSEGEN_LLM_API_KEY / LLM_API_KEY"
    else:
        model = s.llm_model
        base_url = s.llm_base_url
        api_key = s.llm_api_key
        key_hint = "LLM_API_KEY"
    if not api_key:
        raise RuntimeError(f"{key_hint} not set — coursegen Deep Agents need a chat model")
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.3,
        max_tokens=s.llm_max_tokens,
    )


def assign_subagent_models(subagents: list[dict]) -> list[dict]:
    """Attach per-subagent models: heavy roles → COURSEGEN; everyone else → LLM_*."""
    heavy = chat_model(heavy=True)
    normal = chat_model(heavy=False)
    for sa in subagents:
        name = (sa.get("name") or "").replace("-", "_")
        sa["model"] = heavy if name in _HEAVY_SUBAGENT_NAMES else normal
    return subagents

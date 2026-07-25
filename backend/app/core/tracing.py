"""Optional LangSmith tracing for LangGraph + custom httpx LLM calls.

Opt-in via LANGSMITH_TRACING=true and LANGSMITH_API_KEY. When disabled (default),
decorated call sites are no-ops for network and tests never phone home.

Filter in the LangSmith UI by tag ``agent:coursegen`` | ``agent:tutor`` | ``agent:voice``
| ``agent:rag`` (see ``agent_run_config`` / decorator tags).
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from .config import get_settings
from .logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_CONFIGURED = False

# Stable tag prefix so the LangSmith UI can filter one agent at a time.
AGENT_TAGS = {
    "coursegen": ("agent:coursegen", "coursegen"),
    "tutor": ("agent:tutor", "tutor"),
    "voice": ("agent:voice", "voice"),
    "rag": ("agent:rag", "rag"),
}


def configure_tracing() -> None:
    """Sync Settings → LANGSMITH_* env vars before the first graph/LLM invoke.

    The LangSmith / LangGraph SDKs read process env. When tracing is enabled and a
    key is present we export those vars; otherwise we force tracing off so a stale
    shell export cannot leak traces from a misconfigured process.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    s = get_settings()
    if s.langsmith_tracing and s.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_TRACING_V2"] = "true"
        os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = s.langsmith_project or "hituto"
        logger.info(
            "LangSmith tracing enabled (project=%s)",
            os.environ["LANGSMITH_PROJECT"],
        )
        return

    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING_V2"] = "false"
    # Leave any key/project already in the environment alone; with tracing false
    # the SDK will not send runs.


def agent_run_config(
    agent: str,
    *,
    run_name: str,
    extra_tags: list[str] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    """LangGraph / RunnableConfig with stable agent tags for LangSmith filters."""
    base = list(AGENT_TAGS.get(agent, (f"agent:{agent}", agent)))
    if extra_tags:
        base.extend(extra_tags)
    meta = {"agent": agent, **{k: v for k, v in metadata.items() if v is not None}}
    return {
        "run_name": run_name,
        "tags": base,
        "metadata": meta,
    }


def traceable_run(
    name: str,
    *,
    run_type: str = "chain",
    tags: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    process_inputs: Callable[[dict], dict] | None = None,
    process_outputs: Callable[[Any], Any] | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a function as a LangSmith run when tracing is on.

    Always applies ``langsmith.traceable``; the SDK no-ops network when
    ``LANGSMITH_TRACING`` is not ``true``. Safe to use at import time in tests.
    """
    from langsmith import traceable

    def decorator(fn: F) -> F:
        return traceable(
            name=name,
            run_type=run_type,
            tags=list(tags or ()),
            metadata=dict(metadata or {}),
            process_inputs=process_inputs,
            process_outputs=process_outputs,
        )(fn)  # type: ignore[return-value]

    return decorator


def llm_traceable(
    name: str,
    *,
    tags: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a function as a LangSmith LLM run when tracing is on."""
    return traceable_run(name, run_type="llm", tags=tags, metadata=metadata)

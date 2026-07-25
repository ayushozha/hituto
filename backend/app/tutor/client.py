"""Tutor LLM client — OpenAI-compatible tool chat (sync + stream)."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from ..a2ui import normalize_render_ui
from ..core.tracing import llm_traceable
from ..providers import registry
from .tools import _TOOL_DEFS

logger = logging.getLogger(__name__)

_UI_FALLBACK = (
    "I tried to build an interactive for that, but it didn't come together — ask me and I'll "
    "explain it instead."
)

_TUTOR_TAGS = ["agent:tutor", "tutor"]


def _tutor_endpoint() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) via `get_tutor_llm()` (TUTOR_LLM_* → LLM_*)."""
    # Call through the registry *module* so conftest monkeypatches on get_tutor_llm apply.
    llm = registry.get_tutor_llm()
    if not llm.api_key:
        raise RuntimeError("TUTOR_LLM_API_KEY / LLM_API_KEY not set")
    return llm.base_url, llm.api_key, llm.model


@llm_traceable("tutor_chat", tags=_TUTOR_TAGS, metadata={"agent": "tutor", "surface": "post"})
async def _openai_tool_chat(system_prompt: str, history: List[Dict[str, str]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """OpenAI-compatible function calling (the single live tutor path). Returns (content, tool_call).

    Endpoint from TUTOR_LLM_* (falls back to LLM_*). Traced inputs are system_prompt + history
    (no Authorization headers).
    """
    import httpx

    base_url, api_key, model = _tutor_endpoint()
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": model_cls.model_json_schema(),
            },
        }
        for name, desc, model_cls in _TOOL_DEFS
    ]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, *history],
        "temperature": 0.4,
        "tools": tools,
        "tool_choice": "auto",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    choice = data["choices"][0]["message"]
    content = choice.get("content") or ""
    tool_call = None
    if choice.get("tool_calls"):
        # Map the OpenAI tool-call format to our single-tool_call schema.
        func = choice["tool_calls"][0]["function"]
        try:
            name = func["name"]
            args = json.loads(func["arguments"])
        except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
            logger.warning("Could not parse tool call arguments: %s", parse_err)
        else:
            if name == "render_ui":
                # Fail closed: invalid A2UI is dropped so the client never mounts a bad tree.
                # Spec allows falling through to generate_ui on a later turn; this turn → text.
                normalized = normalize_render_ui(args)
                if normalized:
                    tool_call = {"name": name, "arguments": normalized}
                elif not content:
                    content = _UI_FALLBACK
            else:
                tool_call = {"name": name, "arguments": args}
    return content, tool_call


@llm_traceable(
    "tutor_chat_stream",
    tags=["agent:tutor", "tutor", "stream"],
    metadata={"agent": "tutor", "surface": "sse"},
)
async def _openai_tool_chat_stream(
    system_prompt: str, history: List[Dict[str, str]]
) -> AsyncIterator[Dict[str, Any]]:
    """Streaming variant of `_openai_tool_chat` (OpenAI-compatible `stream:true`).

    Yields low-level deltas the orchestrator turns into AG-UI frames:
      {"type": "text", "delta": str}         — assistant prose token(s)
      {"type": "tool_start", "name": str}    — a tool call began
      {"type": "tool_args", "delta": str}    — raw JSON-argument fragment (accumulate)
      {"type": "tool_end"}                   — the (single) tool call finished
    Only one tool call is expected per turn (tool_choice=auto, we take the first).
    """
    import httpx

    base_url, api_key, model = _tutor_endpoint()
    tools = [
        {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": model_cls.model_json_schema()},
        }
        for name, desc, model_cls in _TOOL_DEFS
    ]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, *history],
        "temperature": 0.4,
        "tools": tools,
        "tool_choice": "auto",
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    cur_tool: Optional[str] = None
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{base_url}/chat/completions", headers=headers, json=payload
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield {"type": "text", "delta": text}
                for tc in delta.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    if name and cur_tool != name:
                        cur_tool = name
                        yield {"type": "tool_start", "name": name}
                    frag = fn.get("arguments")
                    if frag:
                        yield {"type": "tool_args", "delta": frag}
    if cur_tool is not None:
        yield {"type": "tool_end"}

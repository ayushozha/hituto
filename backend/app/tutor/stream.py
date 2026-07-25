"""Tutor SSE / AG-UI-style streaming frames."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from ..a2ui import normalize_render_ui
from ..core.tracing import traceable_run
from . import client
from .client import _UI_FALLBACK as _UI_STREAM_FALLBACK
from .prompts_util import _build_system_prompt, _flatten_history

logger = logging.getLogger(__name__)


def _finalize_tool_args(
    name: str,
    args: Dict[str, Any],
    *,
    user_id: str,
    lesson_id: str,
    tool_call_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Apply the SAME security/validation as the non-stream path to a completed tool call.

    render_ui → validated+normalized tree (None if invalid). generate_ui → sanitize+store the
    untrusted HTML and return only {title, intent, ui_id} (None if the gate rejects it); the raw
    HTML never leaves the server. Any other widget → args unchanged.
    """
    if name == "render_ui":
        return normalize_render_ui(args)
    if name == "generate_ui":
        from ..capsule import generative_ui  # lazy: keep store import local to tool path

        ui_id = generative_ui.sanitize_and_store(
            args.get("html", ""), user_id=user_id, lesson_id=lesson_id
        )
        if not ui_id:
            return None
        return {
            "title": args.get("title", "Interactive visual"),
            "intent": args.get("intent", ""),
            "ui_id": ui_id,
        }
    if name == "show_whiteboard" and tool_call_id:
        from ..services import whiteboard_service

        session = whiteboard_service.create_session(
            lesson_id=lesson_id,
            user_id=user_id,
            tool_call_id=tool_call_id,
            title=str(args.get("title") or "Whiteboard"),
            intent=str(args.get("intent") or ""),
            elements=args.get("elements"),
        )
        if session is not None:
            return {**args, "whiteboard_session_id": session.id}
    if name == "show_coding_lab" and tool_call_id:
        from ..services import coding_lab_service

        files = args.get("files")
        session = coding_lab_service.create_session(
            lesson_id=lesson_id,
            user_id=user_id,
            tool_call_id=tool_call_id,
            title=str(args.get("title") or "Coding Lab"),
            language=str(args.get("language") or "javascript"),
            instructions=str(args.get("instructions") or ""),
            files=files,
            entrypoint=args.get("entrypoint"),
            expected_stdout=args.get("expectedStdout"),
            hint=args.get("hint"),
        )
        if session is not None:
            return coding_lab_service.tool_args_from_session(session)
    if name == "update_coding_lab":
        from ..services import coding_lab_service

        session = coding_lab_service.update_session_from_tool_args(
            lesson_id=lesson_id,
            user_id=user_id,
            args=args,
        )
        if session is not None:
            return coding_lab_service.tool_args_from_session(session)
    return args


@traceable_run(
    "tutor_stream",
    tags=["agent:tutor", "tutor", "stream"],
    metadata={"agent": "tutor", "surface": "sse"},
)
async def stream_tutor_events(
    messages: List[Dict[str, Any]],
    *,
    course_id: str,
    lesson_id: str,
    user_id: str,
    lesson_context: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    """Yield AG-UI-style frames for the streaming tutor endpoint (additive to POST /chat).

    Frame types (our own envelope — AG-UI-shaped, NOT the ag-ui package, per the v1 non-goal):
      RUN_STARTED
      TEXT_MESSAGE_CONTENT  {delta}
      TOOL_CALL_START       {toolCallId, toolCallName}
      TOOL_CALL_ARGS        {toolCallId, delta}   — render_ui ONLY
      TOOL_CALL_END         {toolCallId, toolCallName, arguments}
      RUN_FINISHED
      RUN_ERROR             {detail}

    generate_ui NEVER streams arg deltas — its raw HTML is sanitized+stored at the end and only a
    ui_id is emitted, so untrusted markup never reaches the client (same rule as the POST path).
    """
    # Attach dynamic ids onto the current LangSmith run (no-op when tracing is off).
    try:
        from langsmith import get_current_run_tree

        rt = get_current_run_tree()
        if rt is not None:
            rt.metadata = {
                **(rt.metadata or {}),
                "agent": "tutor",
                "course_id": course_id,
                "lesson_id": lesson_id,
            }
    except Exception:  # noqa: BLE001
        pass

    system_prompt = _build_system_prompt(lesson_context)
    history = _flatten_history(messages)

    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    args_buf: List[str] = []
    saw_text = False

    yield {"type": "RUN_STARTED"}
    try:
        # Call through the client *module* so tests can monkeypatch client._openai_tool_chat_stream.
        async for ev in client._openai_tool_chat_stream(system_prompt, history):
            kind = ev["type"]
            if kind == "text":
                saw_text = True
                yield {"type": "TEXT_MESSAGE_CONTENT", "delta": ev["delta"]}
            elif kind == "tool_start":
                tool_name = ev["name"]
                tool_call_id = f"tc_{uuid.uuid4().hex[:8]}"
                args_buf = []
                yield {
                    "type": "TOOL_CALL_START",
                    "toolCallId": tool_call_id,
                    "toolCallName": tool_name,
                }
            elif kind == "tool_args":
                args_buf.append(ev["delta"])
                # Stream deltas ONLY for render_ui (a safe JSON tree). Never for generate_ui HTML.
                if tool_name == "render_ui":
                    yield {"type": "TOOL_CALL_ARGS", "toolCallId": tool_call_id, "delta": ev["delta"]}
            elif kind == "tool_end":
                raw = "".join(args_buf).strip()
                try:
                    parsed = json.loads(raw) if raw else {}
                except ValueError:
                    parsed = {}
                final_args = _finalize_tool_args(
                    tool_name or "",
                    parsed,
                    user_id=user_id,
                    lesson_id=lesson_id,
                    tool_call_id=tool_call_id,
                )
                if final_args is None and tool_name in ("render_ui", "generate_ui") and not saw_text:
                    # Fail-closed: the widget was dropped and nothing was said — say something.
                    yield {"type": "TEXT_MESSAGE_CONTENT", "delta": _UI_STREAM_FALLBACK}
                yield {
                    "type": "TOOL_CALL_END",
                    "toolCallId": tool_call_id,
                    "toolCallName": tool_name,
                    "arguments": final_args,
                }
                tool_name = None
        yield {"type": "RUN_FINISHED"}
    except Exception:
        logger.exception("Tutor stream failed")
        yield {"type": "RUN_ERROR", "detail": "The tutor stream was interrupted. Please try again."}

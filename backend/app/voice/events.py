"""AG-UI event helpers shared by the voice WebSocket and tests.

Wire format is AG-UI's tool-call event *types* in UPPER_SNAKE, carried as JSON frames:

  Agent → App (show a widget):   TOOL_CALL_START → TOOL_CALL_ARGS (delta) → TOOL_CALL_END
  App → Agent (learner acted):   TOOL_CALL_RESULT
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

AG_UI_TOPIC = "ag-ui"


def build_tool_call_frames(tool_call_id: str, name: str, arguments: Dict[str, Any]) -> List[dict]:
    """Encode a single tool call as the START → ARGS → END frame sequence.

    Args are sent as one ``delta`` (not streamed chunk-by-chunk); the frontend accumulates
    deltas by ``toolCallId`` and JSON.parses on END.
    """
    return [
        {"type": "TOOL_CALL_START", "toolCallId": tool_call_id, "toolCallName": name},
        {"type": "TOOL_CALL_ARGS", "toolCallId": tool_call_id, "delta": json.dumps(arguments)},
        {"type": "TOOL_CALL_END", "toolCallId": tool_call_id},
    ]


def encode_frame(frame: dict) -> bytes:
    return json.dumps(frame).encode("utf-8")


# Page control moved to the GuideBridge SDK (its own WebSocket + iframe runtime);
# the PAGE_OBSERVE_*/PAGE_ACTION_* frame family no longer exists on the voice socket.


def parse_tool_result(raw: Any) -> Optional[Dict[str, Any]]:
    """Return the decoded ``content`` of a TOOL_CALL_RESULT frame, else None.

    Accepts bytes/str/dict. The frame's ``content`` is itself a JSON string
    (e.g. ``{"toolName":"create_quiz","score":4,"total":5}``); it's parsed when possible,
    otherwise returned as ``{"raw": <content>}`` so the caller always gets a dict.
    """
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        frame = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(frame, dict) or frame.get("type") != "TOOL_CALL_RESULT":
        return None
    content = frame.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            content = {"raw": content}
    if not isinstance(content, dict):
        content = {"raw": content}
    content.setdefault("toolCallId", frame.get("toolCallId"))
    return content


def build_result_instructions(result: Dict[str, Any]) -> str:
    """Turn a widget result into a spoken-reply nudge for the instructor.

    Fed to ``session.generate_reply(instructions=...)`` so the model reacts to what the
    learner just did instead of ignoring it.
    """
    tool = result.get("toolName") or result.get("tool") or "an activity"
    score, total = result.get("score"), result.get("total")
    if score is not None and total is not None:
        return (
            f"The learner just completed the {tool} widget and scored {score} out of {total}. "
            "React briefly and specifically — acknowledge the score, and if they missed items, "
            "offer to revisit the weakest concept. Keep it to one or two short spoken sentences."
        )
    detail = json.dumps({k: v for k, v in result.items() if k != "toolCallId"})[:400]
    return (
        f"The learner just interacted with the {tool} widget. Result: {detail}. "
        "React briefly and specifically in one or two short spoken sentences."
    )


def make_data_handler(
    session: Any, pending: Optional[Dict[str, Any]] = None
) -> Callable[[Any], None]:
    """Build a small inbound frame callback for legacy AG-UI unit tests.

    Handles ``TOOL_CALL_RESULT`` (widget results) → nudge the instructor to react
    aloud. (``pending`` is retained for signature compatibility; page-control
    frames now ride GuideBridge's own WebSocket, not this one.)

    ⚠️ ``session.generate_reply()`` is SYNCHRONOUS — it returns a SpeechHandle, not a
    coroutine. Call it directly; wrapping it in ``asyncio.create_task(...)`` raises
    ``TypeError: a coroutine was expected``. Guarded by test_voice.py.
    """

    def handler(packet: Any) -> None:
        data = getattr(packet, "data", packet)
        topic = getattr(packet, "topic", None)
        if topic not in (None, AG_UI_TOPIC):
            return
        result = parse_tool_result(data)
        if result is None:
            return
        try:
            session.generate_reply(instructions=build_result_instructions(result))
        except Exception:  # never let a malformed frame kill the session
            logger.exception("voice: failed to react to widget result")

    return handler

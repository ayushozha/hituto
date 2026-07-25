"""Typed JSON protocol for the browser <-> voice-agent WebSocket.

Audio frames are binary PCM16 mono from the browser and binary PCM audio back from TTS.
Everything else is a small JSON frame with a `type` field.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

AG_UI_TOPIC = "ag-ui"


class ClientFrame(BaseModel):
    type: str
    requestId: Optional[str] = None
    toolCallId: Optional[str] = None
    content: Any = None
    action: Optional[Dict[str, Any]] = None


class ServerFrame(BaseModel):
    type: str
    text: Optional[str] = None
    speaker: Optional[Literal["learner", "instructor"]] = None
    final: Optional[bool] = None
    requestId: Optional[str] = None
    toolCallId: Optional[str] = None
    toolCallName: Optional[str] = None
    delta: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    content: Any = None
    detail: Optional[str] = None
    sampleRate: Optional[int] = None


def encode_frame(frame: dict | ServerFrame) -> str:
    if isinstance(frame, ServerFrame):
        frame = frame.model_dump(exclude_none=True)
    return json.dumps(frame, separators=(",", ":"))


def decode_frame(raw: str) -> ClientFrame:
    return ClientFrame.model_validate_json(raw)


def session_ready(*, sample_rate: int, tts_sample_rate: int) -> dict:
    return {
        "type": "session.ready",
        "sampleRate": sample_rate,
        "ttsSampleRate": tts_sample_rate,
    }


def transcript_frame(text: str, *, final: bool) -> dict:
    return {"type": "stt.final" if final else "stt.partial", "speaker": "learner", "text": text}


def agent_final(text: str) -> dict:
    return {"type": "agent.final", "speaker": "instructor", "text": text, "final": True}


def agent_delta(text: str) -> dict:
    return {"type": "agent.delta", "speaker": "instructor", "text": text, "final": False}


def error_frame(detail: str) -> dict:
    return {"type": "error", "detail": detail}


def closed_frame(detail: str = "closed") -> dict:
    return {"type": "session.closed", "detail": detail}


def tts_start(*, sample_rate: int) -> dict:
    return {"type": "tts.start", "sampleRate": sample_rate}


def tts_done() -> dict:
    return {"type": "tts.done"}


def tts_interrupt() -> dict:
    """Tell the browser to stop and discard any queued/playing tutor audio (barge-in)."""
    return {"type": "tts.interrupt"}


def build_tool_call_frames(tool_call_id: str, name: str, arguments: Dict[str, Any]) -> list[dict]:
    """AG-UI-compatible widget call frames consumed by the existing React code path."""
    return [
        {"type": "TOOL_CALL_START", "toolCallId": tool_call_id, "toolCallName": name},
        {"type": "TOOL_CALL_ARGS", "toolCallId": tool_call_id, "delta": json.dumps(arguments)},
        {"type": "TOOL_CALL_END", "toolCallId": tool_call_id},
    ]


def parse_json_content(content: Any) -> Dict[str, Any]:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return {"raw": content}
    if isinstance(content, dict):
        return content
    return {"raw": content}

"""Tutor public façade — text tutor chat + SSE streaming."""
from __future__ import annotations

from .agent import run_tutor_chat
from .stream import stream_tutor_events
from .tools import GenerateUiTool, TOOL_DEFS, _TOOL_DEFS

__all__ = [
    "GenerateUiTool",
    "TOOL_DEFS",
    "_TOOL_DEFS",
    "run_tutor_chat",
    "stream_tutor_events",
]

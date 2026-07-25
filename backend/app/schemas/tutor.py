"""Tutor chat request/response schemas (the API contract for /tutor/chat)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    tool_call: Optional[ChatToolCall] = None
    # Client-authored context. It is never executed and is labeled untrusted in the model prompt.
    whiteboard_state: Optional[Dict[str, Any]] = None
    coding_lab_state: Optional[Dict[str, Any]] = None


class TutorChatRequest(BaseModel):
    messages: List[ChatMessage]


class WhiteboardSyncRequest(BaseModel):
    elements: List[Dict[str, Any]]


class CodingLabSyncRequest(BaseModel):
    files: List[Dict[str, Any]]


class CodingLabRunRequest(BaseModel):
    """Client-reported sandbox run / check result (AG-UI CODING_LAB_* payload)."""

    ok: bool = True
    passed: Optional[bool] = None
    stdout: str = ""
    stderr: str = ""
    language: Optional[str] = None
    event: str = "CODING_LAB_RUN_RESULT"
    files: Optional[List[Dict[str, Any]]] = None


class TutorChatResponse(BaseModel):
    role: str = "assistant"
    content: str
    tool_call: Optional[ChatToolCall] = None

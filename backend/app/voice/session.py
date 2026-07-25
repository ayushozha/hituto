"""Active voice WebSocket session implementation."""
from __future__ import annotations

from .openai_realtime_session import OpenAIRealtimeVoiceSession

VoiceSession = OpenAIRealtimeVoiceSession

__all__ = ["OpenAIRealtimeVoiceSession", "VoiceSession"]

"""Deepgram Flux streaming STT adapter."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urlencode

from ..core.config import get_settings
from .deepgram_ws import connect_websocket

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    final: bool


class DeepgramSTT:
    """Streams PCM16 audio to Deepgram and yields partial/final transcripts."""

    def __init__(self):
        self._ws = None
        self._last_partial = ""

    async def connect(self) -> None:
        settings = get_settings()
        params = urlencode(
            {
                "model": settings.deepgram_stt_model,
                "encoding": "linear16",
                "sample_rate": str(settings.voice_sample_rate),
            }
        )
        self._ws = await connect_websocket(
            f"wss://api.deepgram.com/v2/listen?{params}",
            headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
        )

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is None or not chunk:
            return
        await self._ws.send(chunk)

    async def finalize_turn(self) -> None:
        # Flux (/v2/listen) detects end-of-turn on its own and has no manual finalize —
        # "Finalize" is a v1-only message and sending it on v2 can trigger a fatal error.
        # The client's audio.stop is just a hint; turn boundaries come from Flux EndOfTurn.
        return

    async def events(self) -> AsyncIterator[TranscriptEvent]:
        if self._ws is None:
            raise RuntimeError("DeepgramSTT.connect() must be called first")
        async for raw in self._ws:
            if isinstance(raw, bytes):
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            event = self._parse_event(data)
            if event is not None:
                yield event

    def _parse_event(self, data: dict) -> TranscriptEvent | None:
        # Flux (v2) messages are {"type": "TurnInfo", "event": "Update|EndOfTurn|...",
        # "transcript": "..."}; the turn boundary lives in `event`, NOT `type`. v1 messages
        # instead carry is_final/speech_final. Read both so either protocol works, but Flux
        # is the live path — reading `type` for the turn signal made `final` always False.
        event_name = str(data.get("event") or "")
        msg_type = str(data.get("type") or "")
        transcript = _extract_transcript(data)
        final = bool(
            data.get("is_final")
            or data.get("speech_final")
            or data.get("turn_is_formatted")
            or event_name == "EndOfTurn"
            or msg_type in {"EndOfTurn", "UtteranceEnd"}
        )
        if transcript:
            # Clear the buffer on a final so a later empty EndOfTurn can't re-emit stale text.
            self._last_partial = "" if final else transcript
            return TranscriptEvent(text=transcript, final=final)
        if final and self._last_partial:
            text = self._last_partial
            self._last_partial = ""
            return TranscriptEvent(text=text, final=True)
        return None

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await asyncio.wait_for(self._ws.send(json.dumps({"type": "CloseStream"})), timeout=1)
        except Exception:
            pass
        try:
            await self._ws.close()
        except Exception:
            pass
        self._ws = None


def _extract_transcript(data: dict) -> str:
    if isinstance(data.get("transcript"), str):
        return data["transcript"].strip()
    channel = data.get("channel")
    if isinstance(channel, dict):
        alternatives = channel.get("alternatives")
        if isinstance(alternatives, list) and alternatives:
            transcript = alternatives[0].get("transcript")
            if isinstance(transcript, str):
                return transcript.strip()
    return ""

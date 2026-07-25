"""Deepgram streaming TTS adapter."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

from ..core.config import get_settings
from .deepgram_ws import connect_websocket

logger = logging.getLogger(__name__)


class DeepgramTTS:
    """Generate PCM audio chunks for a text response."""

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        settings = get_settings()
        params = urlencode(
            {
                "model": settings.deepgram_tts_model,
                "encoding": "linear16",
                "sample_rate": str(settings.voice_tts_sample_rate),
                "container": "none",
            }
        )
        ws = await connect_websocket(
            f"wss://api.deepgram.com/v1/speak?{params}",
            headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
        )
        try:
            await ws.send(json.dumps({"type": "Speak", "text": cleaned}))
            await ws.send(json.dumps({"type": "Flush"}))
            async for raw in ws:
                if isinstance(raw, bytes):
                    yield raw
                    continue
                if _is_done(raw):
                    break
        finally:
            try:
                await asyncio.wait_for(ws.send(json.dumps({"type": "Close"})), timeout=1)
            except Exception:
                logger.debug("voice: Deepgram TTS close ignored", exc_info=True)
            try:
                await ws.close()
            except Exception:
                pass


def _is_done(raw: str) -> bool:
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    event_type = str(data.get("type") or "")
    return event_type in {"Flushed", "Close", "Done", "Metadata"} and bool(
        data.get("flushed") or event_type in {"Flushed", "Done"}
    )

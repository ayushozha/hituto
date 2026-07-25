"""Legacy Deepgram cascade voice session.

This is the old browser -> Deepgram STT -> chat-completions brain -> Deepgram TTS path.
It is kept importable for manual recovery, but the active app voice route uses OpenAI
Realtime S2S and must not fall back here automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect

from ..core.config import get_settings
from . import protocol
from .agent_langchain import LangChainVoiceAgent
from .stt_deepgram import DeepgramSTT, TranscriptEvent
from .tts_deepgram import DeepgramTTS

logger = logging.getLogger(__name__)

STTFactory = Callable[[], Any]
TTSFactory = Callable[[], Any]
AgentFactory = Callable[..., Any]


class DeepgramCascadeVoiceSession:
    """Owns all async work for a single legacy Deepgram cascade voice connection."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        lesson_context: dict[str, Any],
        stt_factory: STTFactory = DeepgramSTT,
        tts_factory: TTSFactory = DeepgramTTS,
        agent_factory: AgentFactory = LangChainVoiceAgent,
    ):
        self.websocket = websocket
        self.lesson_context = lesson_context
        self.stt = stt_factory()
        self.tts = tts_factory()
        self.agent = agent_factory(lesson_context=lesson_context, send_frame=self.send_json)
        self._closed = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._agent_lock = asyncio.Lock()
        self._last_activity = time.monotonic()
        self._last_final = ""
        self._active_turn: asyncio.Task[None] | None = None

    async def run(self) -> None:
        settings = get_settings()
        await self.stt.connect()
        await self.send_json(
            protocol.session_ready(
                sample_rate=settings.voice_sample_rate,
                tts_sample_rate=settings.voice_tts_sample_rate,
            )
        )
        tasks = [
            asyncio.create_task(self._receive_client(), name="voice-client"),
            asyncio.create_task(self._consume_stt(), name="voice-stt"),
            asyncio.create_task(self._idle_watch(), name="voice-idle"),
            asyncio.create_task(self._max_duration_watch(), name="voice-max-duration"),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
            for task in pending:
                task.cancel()
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("voice: legacy Deepgram session failed")
            with suppress(Exception):
                await self.send_json(protocol.error_frame("voice session failed"))
        finally:
            await self.close("closed")

    async def send_json(self, frame: dict) -> None:
        if self._closed.is_set():
            return
        async with self._send_lock:
            await self.websocket.send_text(protocol.encode_frame(frame))

    async def send_audio(self, chunk: bytes) -> None:
        if self._closed.is_set() or not chunk:
            return
        async with self._send_lock:
            await self.websocket.send_bytes(chunk)

    async def close(self, reason: str) -> None:
        if self._closed.is_set():
            return
        self._cancel_active_turn()
        abort = getattr(self.agent, "abort_pending_generate_ui", None)
        if abort is not None:
            await abort()
        self.agent.close()
        with suppress(Exception):
            await self.stt.close()
        with suppress(Exception):
            async with self._send_lock:
                await self.websocket.send_text(protocol.encode_frame(protocol.closed_frame(reason)))
        self._closed.set()
        with suppress(Exception):
            await self.websocket.close()

    async def _receive_client(self) -> None:
        while not self._closed.is_set():
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            data = message.get("bytes")
            if data is not None:
                self._touch()
                await self.stt.send_audio(data)
                continue
            text = message.get("text")
            if text is not None:
                await self._handle_client_frame(protocol.decode_frame(text))

    async def _handle_client_frame(self, frame: protocol.ClientFrame) -> None:
        self._touch()
        if frame.type in {"client.ready", "client.ping", "audio.start"}:
            return
        if frame.type == "audio.stop":
            await self.stt.finalize_turn()
            return
        # Page-control results moved to GuideBridge's own WebSocket; only the
        # PAGE_MAP live-context push still arrives on this socket.
        if frame.type == "PAGE_MAP":
            raw = frame.content if isinstance(frame.content, str) else json.dumps(frame.content or {})
            cleaned = raw.strip()
            if cleaned:
                self.lesson_context["page_map"] = cleaned[:6000]
            return
        if frame.type in {"TOOL_CALL_RESULT", "tool.result"}:
            result = protocol.parse_json_content(frame.content)
            if frame.toolCallId:
                result.setdefault("toolCallId", frame.toolCallId)
            self._launch_turn(self._agent_turn_from_tool_result(result))

    async def _consume_stt(self) -> None:
        async for event in self.stt.events():
            if self._closed.is_set():
                return
            if event.text.strip() and self._active_turn and not self._active_turn.done():
                self._cancel_active_turn()
                await self.send_json(protocol.tts_interrupt())
            await self.send_json(protocol.transcript_frame(event.text, final=event.final))
            if event.final:
                self._launch_turn(self._agent_turn_from_transcript(event))

    def _launch_turn(self, coro: Any) -> None:
        self._cancel_active_turn()
        task = asyncio.create_task(coro)
        self._active_turn = task
        task.add_done_callback(self._on_turn_done)

    def _cancel_active_turn(self) -> None:
        task = self._active_turn
        if task is not None and not task.done():
            task.cancel()

    def _on_turn_done(self, task: asyncio.Task[None]) -> None:
        if self._active_turn is task:
            self._active_turn = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("voice: legacy agent turn failed", exc_info=exc)

    async def _agent_turn_from_transcript(self, event: TranscriptEvent) -> None:
        text = event.text.strip()
        if not text or text == self._last_final:
            return
        self._last_final = text
        await self._run_agent_and_speak(text)

    async def _agent_turn_from_tool_result(self, result: dict[str, Any]) -> None:
        async with self._agent_lock:
            response = await self.agent.respond_to_tool_result(result)
            await self._speak_response(response)

    async def _run_agent_and_speak(self, text: str) -> None:
        async with self._agent_lock:
            response = await self.agent.respond_to_text(text)
            await self._speak_response(response)

    async def _speak_response(self, response: str) -> None:
        response = response.strip()
        if not response:
            return
        await self.send_json(protocol.agent_final(response))
        settings = get_settings()
        await self.send_json(protocol.tts_start(sample_rate=settings.voice_tts_sample_rate))
        try:
            async for chunk in self.tts.speak(response):
                await self.send_audio(chunk)
        except Exception:
            logger.exception("voice: legacy Deepgram TTS failed")
            await self.send_json(protocol.error_frame("voice audio generation failed"))
        finally:
            await self.send_json(protocol.tts_done())

    async def _idle_watch(self) -> None:
        timeout = max(15, get_settings().voice_idle_timeout_s)
        while not self._closed.is_set():
            await asyncio.sleep(min(5, timeout))
            if time.monotonic() - self._last_activity >= timeout:
                await self.close("idle timeout")
                return

    async def _max_duration_watch(self) -> None:
        seconds = max(60, get_settings().voice_session_max_minutes * 60)
        await asyncio.sleep(seconds)
        await self.close("max duration reached")

    def _touch(self) -> None:
        self._last_activity = time.monotonic()


VoiceSession = DeepgramCascadeVoiceSession

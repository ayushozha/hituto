# voice — real-time voice instructor

A voice teacher that talks with the learner **and** observes + drives the running lesson capsule.
Off by default: needs `VOICE_ENABLED=true` + `OPENAI_REALTIME_API_KEY` (`/health` reports
`voice.enabled`; the frontend hides the button when disabled).

## Active path: OpenAI Realtime S2S

`session.py` hardcodes `VoiceSession = OpenAIRealtimeVoiceSession`. `core/config.py` forces the
provider to `openai_realtime_s2s`. A server-to-server bridge relays audio:

```
browser PCM (24kHz) ⇄ FastAPI WebSocket ⇄ OpenAI Realtime (gpt-realtime-2.1) ⇄ tools
   api/v1/voice.py: /courses/{cid}/lessons/{lid}/voice/ws
   → auth (get_user_id_from_websocket) + ownership check
   → load_lesson_context() + build_instructions()  (grounding.py)
   → OpenAIRealtimeVoiceSession.run(): 4 tasks — client recv, realtime consume, idle, max-duration
```

Browser does VAD (`audio.start`/PCM/`audio.stop`); the session commits the buffer, OpenAI returns
a transcript + streams audio deltas back; tool calls arrive as
`response.function_call_arguments.*` and are executed via the agent, with the result returned as a
`conversation.item.create` function output. Barge-in interrupts the active response.

## The agent + tools (`agent_langchain.py`)

`LangChainVoiceAgent` is a single-lesson conversational agent (sliding window of ~16 turns, not
persisted). Two tool families (`realtime_tool_specs()`):

- **Widget tools** — reuse the text tutor's `_TOOL_DEFS` (`render_ui`, `generate_ui`, quiz,
  flashcards, code, game, diagram, calculator) so voice and text render identically. `render_ui`
  fails closed to speech; `generate_ui` shows a pending card immediately, generates the HTML in a
  background task, sanitizes + stores it, and returns a `ui_id`.
- **Page tools** — `observe_page`, `point_at`, `scroll_to`, `scroll_by`, `highlight`, `click`,
  `type_text`, `select_option`, provided by the GuideBridge SDK: the agent calls
  `app.agentbridge.bridge.call_tool(...)`, which routes over guidebridge's own WebSocket
  (`/courses/{c}/lessons/{l}/agent-bridge/ws`) to the lesson tab, where the guidebridge iframe
  runtime (injected by `capsule/postprocess.py`) executes it and the SDK's `AgentCursor` draws
  the Tutor pointer. Stale-id fuzzy retry is built into the SDK.

## Grounding (`grounding.py`)

`load_lesson_context()` reads course/lesson metadata + the latest `Artifact` digest.
`build_instructions()` compiles the system prompt with hard rules — e.g. *when the learner asks to
see something → must call `render_ui`/`generate_ui`; when teaching a section/control → must call
`highlight`/`scroll_to` from the LIVE PAGE MAP*. The page map (ids/slugs of on-screen controls) is
appended so the model can target real elements.

## Legacy: Deepgram cascade

`deepgram_cascade_session.py` (browser audio → Deepgram STT → LangChain brain → Deepgram TTS) is
**manual-recovery only, not an automatic fallback** — `voice_ready()` gates on OpenAI Realtime
alone. Kept for historical deployments.

## Data model touched

**Read-only.** `Course`, `Lesson`, latest `Artifact` (digest). Writes nothing durable (the
`generate_ui` store is in-memory). See [`../../DATABASE.md`](../../DATABASE.md).

## Config

`VOICE_ENABLED`, `OPENAI_REALTIME_API_KEY`, `OPENAI_REALTIME_MODEL` (gpt-realtime-2.1),
`OPENAI_REALTIME_VOICE` (verse), `VOICE_SESSION_MAX_MINUTES` (15), `VOICE_IDLE_TIMEOUT_S` (60),
`VOICE_PAGE_TOOL_TIMEOUT_S` (8). Optional `VOICE_LLM_*` for the text-model calls (falls back to the
tutor LLM). Never imports `coursegen`.

## Key files

`session.py` (alias) · `openai_realtime_session.py` (S2S bridge) · `agent_langchain.py` (agent +
tools) · `grounding.py` (context + instructions) · `tools.py` (widget ACKs) · `protocol.py` /
`events.py` (frames) · `generate_ui.py` · `deepgram_cascade_session.py` (legacy). Route:
`api/v1/voice.py`. Host side: `frontend/src/lib/lessonBridge.ts`, `components/AgentCursorOverlay.tsx`.

## Tests

`test_voice.py`, `test_openai_realtime_voice.py`, `test_voice_page_control.py`,
`test_lesson_bridge.py`, `test_edit_mode.py`; live smoke: `test_voice_live.py`
(`RUN_LIVE_VOICE=1` + creds).

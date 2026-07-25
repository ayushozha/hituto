"""Voice tutor brain — OpenAI-compatible httpx tool loop.

STT/TTS stay in separate adapters; this module only turns learner text into a short spoken
reply and optional widget/page tool calls. Uses the same direct /chat/completions path as the
text tutor so voice turns stay in the ~5s range instead of the 45s+ LangGraph agent loop.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from guidebridge import tools as gb_tools

from ..agentbridge import bridge as agent_bridge, page_session_id
from ..core.config import get_settings
from ..core.tracing import llm_traceable, traceable_run
from ..a2ui import normalize_render_ui
from ..tutor import _TOOL_DEFS
from ..capsule import generative_ui
from ..services import whiteboard_service
from ..services import coding_lab_service
from . import protocol
from .events import build_result_instructions
from .grounding import build_instructions
from .tools import _ACKS

from .generate_ui import (  # noqa: F401 — re-export for tests that monkeypatch agent_langchain.*
    VOICE_GENERATE_UI_MAX_TOKENS,
    VOICE_GENERATE_UI_STRONG_TIMEOUT_SECONDS,
    VoiceGenerateUiTool,
    _VOICE_GENERATE_UI_DESC,
    _ensure_generate_ui_asset,
    _extract_generated_html_from_response,
    _extract_html_from_arguments,
    _extract_html_from_text,
    _first_html_value,
    _regenerate_ui_html_strong,
    _trace_generate_ui_html_inputs,
    _trace_html_output,
    _trace_prepare_generate_ui_inputs,
)

logger = logging.getLogger(__name__)

_THINKING_RE = re.compile(r"</?redacted_thinking>|</?think>", re.IGNORECASE)

SendFrame = Callable[[dict], Awaitable[None]]
MAX_TOOL_ROUNDS = 3
_WIDGET_NAMES = {name for name, _, _ in _TOOL_DEFS}

# Page control now rides GuideBridge's own WebSocket (see app/agentbridge.py),
# not the voice socket. These are the guidebridge tools the voice tutor exposes.
PAGE_TOOL_NAMES = {
    "observe_page",
    "point_at",
    "scroll_to",
    "scroll_by",
    "highlight",
    "click",
    "type_text",
    "select_option",
}

# Video-guide surfaces (specs/design_agents §6): no iframe runtime, so page tools are
# meaningless — the host page registers custom actions (seek_to/play_video/pause_video)
# that the agent discovers via observe_page and invokes via app_action. Same GuideBridge
# session, same calling convention; only where the handler runs differs.
VIDEO_TOOL_NAMES = {"observe_page", "app_action"}

# Every guidebridge tool the dispatcher may route (union of the capability sets).
BRIDGE_TOOL_NAMES = PAGE_TOOL_NAMES | VIDEO_TOOL_NAMES

# Hi-Tuto's teaching-oriented descriptions layered over the SDK's schemas.
_PAGE_TOOL_DESCRIPTIONS = {
    "observe_page": (
        "Read the live lesson page: sections, headings, targets (controls), scroll position, "
        "and recent learner interactions. Call when you need fresh ids (no page map yet, or "
        "after the page changed). Returns target_ids for highlight/scroll_to/click/type_text."
    ),
    "point_at": "Move the Tutor cursor onto a section/control without acting, to direct attention.",
    "scroll_to": "Scroll a lesson section or control into view (use with highlight while teaching).",
    "scroll_by": "Scroll the lesson page up or down without a target (e.g. 'scroll down a bit').",
    "highlight": (
        "Point the Tutor cursor at a section/control and outline it while you explain. "
        "Call this whenever you teach something that is already on the lesson page."
    ),
    "click": (
        "Click a lesson button/control with the Tutor cursor (tabs, chips, quiz, reset). "
        "Use to demonstrate the interactive page while teaching."
    ),
    "type_text": "Move the Tutor cursor and type into an input, textarea, or slider on the lesson page.",
    "select_option": "Move the Tutor cursor and choose a dropdown option on the lesson page.",
    "app_action": (
        "Invoke an app-registered action listed under customActions in observe_page. On video "
        "lessons: seek_to {seconds}, play_video {}, pause_video {} control the lesson video."
    ),
}


def _bridge_tool_names(capabilities: Optional[Dict[str, Any]]) -> set[str]:
    """Which guidebridge tools this surface supports (specs/design_agents §6).

    No capabilities (older callers, missing surface) → the full page set, matching the
    pre-gating behavior. GuideBridge itself degrades gracefully for unsupported calls.
    """
    if capabilities is None:
        return set(PAGE_TOOL_NAMES)
    names: set[str] = set()
    if capabilities.get("page_control"):
        names |= PAGE_TOOL_NAMES | {"app_action"}
    if capabilities.get("seek"):
        names |= VIDEO_TOOL_NAMES
    return names


def _page_tool_specs(capabilities: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    allowed = _bridge_tool_names(capabilities)
    specs = []
    for spec in gb_tools.openai_tool_specs():
        fn = spec["function"]
        if fn["name"] not in allowed:
            continue
        fn = {**fn, "description": _PAGE_TOOL_DESCRIPTIONS.get(fn["name"], fn["description"])}
        specs.append({"type": "function", "function": fn})
    return specs


async def _regenerate_ui_html_with_realtime_timeout(**kwargs: Any) -> Optional[str]:
    """Wrap strong regen with a timeout; resolve `_regenerate_ui_html_strong` at call time.

    Tests monkeypatch `agent_langchain._regenerate_ui_html_strong` — a load-time binding inside
    `generate_ui` would ignore that patch, so the wrapper lives here.
    """
    try:
        return await asyncio.wait_for(
            _regenerate_ui_html_strong(**kwargs),
            timeout=VOICE_GENERATE_UI_STRONG_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "voice: strong-model generate_ui timed out after %.1fs; generation failed",
            VOICE_GENERATE_UI_STRONG_TIMEOUT_SECONDS,
        )
        return None


class LangChainVoiceAgent:
    """One lesson-scoped conversational agent."""

    def __init__(self, *, lesson_context: Dict[str, Any], send_frame: SendFrame):
        self.lesson_context = lesson_context
        self._send_frame = send_frame
        # Same identity the lesson viewer's AgentProvider claims on its bridge WS.
        self._page_session_id = page_session_id(
            str(lesson_context.get("user_id") or ""),
            str(lesson_context.get("lesson_id") or ""),
        )
        self._messages: List[Dict[str, str]] = []
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._pending_generate_ui: set[str] = set()

    def record_user_text(self, text: str) -> None:
        self._append_message("user", text)

    def record_assistant_text(self, text: str) -> None:
        self._append_message("assistant", text)

    async def respond_to_text(self, text: str) -> str:
        """Run one learner turn and return assistant text for TTS."""
        prompt = text.strip()
        if not prompt:
            return ""
        self.record_user_text(prompt)
        try:
            content = await self._run_chat_loop()
        except Exception:
            logger.exception("voice: agent invocation failed")
            fallback = "Sorry, I hit an issue thinking through that. Could you try that again?"
            self.record_assistant_text(fallback)
            return fallback

        self.record_assistant_text(content)
        return content

    async def respond_to_tool_result(self, result: Dict[str, Any]) -> str:
        return await self.respond_to_text(build_result_instructions(result))

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Execute one voice tool call and return the tool output for the model."""
        return await self._execute_tool(
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {})},
            }
        )

    async def abort_pending_generate_ui(self) -> None:
        """Emit error TOOL_CALL_END for in-flight generate_ui cards before tearing down."""
        for tool_call_id in list(self._pending_generate_ui):
            with suppress(Exception):
                await self._send_frame(
                    {"type": "TOOL_CALL_END", "toolCallId": tool_call_id, "error": True}
                )
        self._pending_generate_ui.clear()

    def close(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()

    def has_pending_work(self) -> bool:
        return bool(self._pending_generate_ui) or any(
            not task.done() for task in self._background_tasks
        )

    def _append_message(self, role: str, text: str) -> None:
        content = " ".join((text or "").split())
        if not content:
            return
        if self._messages and self._messages[-1] == {"role": role, "content": content}:
            return
        self._messages.append({"role": role, "content": content})
        self._messages = self._messages[-16:]

    async def _run_chat_loop(self) -> str:
        system = build_instructions(self.lesson_context)
        history: List[Dict[str, Any]] = [
            {"role": message["role"], "content": message["content"]} for message in self._messages
        ]

        last_content = ""
        for _ in range(MAX_TOOL_ROUNDS):
            last_content, tool_calls = await _voice_llm_call(
                system, history, tools=_openai_tool_specs(self.lesson_context.get("surface_capabilities"))
            )
            if not tool_calls:
                final = (last_content or "").strip()
                logger.info(
                    "voice: model returned NO tool calls (spoke only, content_len=%d)", len(final)
                )
                return final or "I'm here — what would you like to work on?"
            logger.info(
                "voice: model returned %d tool call(s): %s",
                len(tool_calls),
                [tc.get("function", {}).get("name") for tc in tool_calls],
            )

            history.append(
                {
                    "role": "assistant",
                    "content": last_content or "",
                    "tool_calls": tool_calls,
                }
            )
            for tool_call in tool_calls:
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": await self._execute_tool(tool_call),
                    }
                )

        return (last_content or "").strip() or "I put that on screen for you — give it a try."

    async def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        func = tool_call.get("function") or {}
        name = str(func.get("name") or "")
        try:
            args = json.loads(func.get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        logger.info("voice: tool call name=%s arg_keys=%s", name, list(args.keys()))

        if name in _WIDGET_NAMES:
            if name == "render_ui":
                # Fail closed: an invalid A2UI tree is never rendered; the agent talks instead.
                normalized = normalize_render_ui(args)
                if normalized is None:
                    logger.warning("voice: render_ui REJECTED (invalid A2UI tree) — speaking instead")
                    return "That visual didn't come together — let me explain it out loud instead."
                args = normalized
            tool_call_id = f"tc_{uuid.uuid4().hex[:8]}"
            if name == "show_whiteboard":
                session = whiteboard_service.create_session(
                    lesson_id=str(self.lesson_context.get("lesson_id") or ""),
                    user_id=str(self.lesson_context.get("user_id") or ""),
                    tool_call_id=tool_call_id,
                    title=str(args.get("title") or "Whiteboard"),
                    intent=str(args.get("intent") or ""),
                    elements=args.get("elements"),
                )
                if session is not None:
                    args = {**args, "whiteboard_session_id": session.id}
                    self.lesson_context["whiteboard_state"] = (
                        whiteboard_service.session_context(session)
                    )
            if name == "show_coding_lab":
                session = coding_lab_service.create_session(
                    lesson_id=str(self.lesson_context.get("lesson_id") or ""),
                    user_id=str(self.lesson_context.get("user_id") or ""),
                    tool_call_id=tool_call_id,
                    title=str(args.get("title") or "Coding Lab"),
                    language=str(args.get("language") or "javascript"),
                    instructions=str(args.get("instructions") or ""),
                    files=args.get("files"),
                    entrypoint=args.get("entrypoint"),
                    expected_stdout=args.get("expectedStdout"),
                    hint=args.get("hint"),
                )
                if session is not None:
                    args = coding_lab_service.tool_args_from_session(session)
                    self.lesson_context["coding_lab_state"] = (
                        coding_lab_service.session_context(session)
                    )
            if name == "update_coding_lab":
                session = coding_lab_service.update_session_from_tool_args(
                    lesson_id=str(self.lesson_context.get("lesson_id") or ""),
                    user_id=str(self.lesson_context.get("user_id") or ""),
                    args=args,
                )
                if session is not None:
                    args = coding_lab_service.tool_args_from_session(session)
                    self.lesson_context["coding_lab_state"] = (
                        coding_lab_service.session_context(session)
                    )
            if name == "generate_ui":
                # Path B is slow by nature. Match the old generative-widget UX: publish a pending
                # card immediately, then finish the card from a background task when the stronger
                # model has produced and stored the sandboxed capsule.
                title = str(args.get("title") or "Interactive visual")
                intent = str(args.get("intent") or args.get("visual_prompt") or "")
                logger.info("voice: emitting pending generate_ui frame tool_call_id=%s", tool_call_id)
                self._pending_generate_ui.add(tool_call_id)
                await self._send_frame(
                    {
                        "type": "TOOL_CALL_START",
                        "toolCallId": tool_call_id,
                        "toolCallName": name,
                        "title": title,
                    }
                )
                self._track_background_task(
                    asyncio.create_task(
                        self._emit_generate_ui_result(tool_call_id, args),
                        name=f"voice-generate-ui-{tool_call_id}",
                    )
                )
                return intent or "I'm building an interactive visual for you. It will appear shortly."
            logger.info("voice: emitting %s frames tool_call_id=%s", name, tool_call_id)
            for frame in protocol.build_tool_call_frames(tool_call_id, name, args):
                await self._send_frame(frame)
            # Prefer the per-call `intent` (render_ui/generate_ui) as the spoken-turn seed; fall
            # back to the static ACK for the fixed widgets that carry no intent.
            return args.get("intent") or _ACKS.get(
                name, "Here's an interactive activity. Try it when you're ready."
            )

        if name in BRIDGE_TOOL_NAMES:
            # GuideBridge routes to the lesson viewer's tab (its own WS) and
            # already degrades gracefully when no tab is connected.
            # Brief wait: the viewer remounts the bridge WS on navigation/HMR and
            # a bare get_session() during that gap falsely returns UNAVAILABLE.
            try:
                await agent_bridge.wait_for_session(self._page_session_id, timeout_s=3.0)
            except Exception:
                logger.warning(
                    "voice: guidebridge session missing id=%s sessions=%s",
                    self._page_session_id,
                    agent_bridge.sessions(),
                )
            result = await agent_bridge.call_tool(
                name, args, session_id=self._page_session_id
            )
            logger.info(
                "voice: guidebridge %s session=%s result=%s",
                name,
                self._page_session_id,
                (result[:180] + "…") if isinstance(result, str) and len(result) > 180 else result,
            )
            return result

        return f"Unknown tool: {name}"

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)

        def _done(done: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done)
            with suppress(asyncio.CancelledError):
                exc = done.exception()
                if exc is not None:
                    logger.error(
                        "voice: background task failed",
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )

        task.add_done_callback(_done)

    async def _emit_generate_ui_result(self, tool_call_id: str, raw_args: Dict[str, Any]) -> None:
        try:
            args = await self._prepare_generate_ui_args(raw_args)
            if args is None:
                await self._send_frame(
                    {"type": "TOOL_CALL_END", "toolCallId": tool_call_id, "error": True}
                )
                return
            await self._send_frame(
                {
                    "type": "TOOL_CALL_ARGS",
                    "toolCallId": tool_call_id,
                    "delta": json.dumps(args),
                }
            )
            await self._send_frame({"type": "TOOL_CALL_END", "toolCallId": tool_call_id})
        except asyncio.CancelledError:
            with suppress(Exception):
                await self._send_frame(
                    {"type": "TOOL_CALL_END", "toolCallId": tool_call_id, "error": True}
                )
            raise
        except Exception:
            logger.exception("voice: generate_ui background emit failed")
            with suppress(Exception):
                await self._send_frame(
                    {"type": "TOOL_CALL_END", "toolCallId": tool_call_id, "error": True}
                )
        finally:
            self._pending_generate_ui.discard(tool_call_id)

    @traceable_run(
        "voice_prepare_generate_ui",
        run_type="chain",
        tags=["agent:voice", "voice"],
        metadata={"agent": "voice"},
        process_inputs=_trace_prepare_generate_ui_inputs,
    )
    async def _prepare_generate_ui_args(self, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = str(args.get("title") or "Interactive visual")
        learner_text = _latest_user_text(self._messages)
        intent = str(args.get("intent") or args.get("visual_prompt") or learner_text or "")
        visual_prompt = str(args.get("visual_prompt") or intent or learner_text or title)
        user_id = str(self.lesson_context.get("user_id") or "")
        lesson_id = str(self.lesson_context.get("lesson_id") or "")

        logger.info(
            "voice: generate_ui request title=%r visual_prompt_len=%d",
            title,
            len(visual_prompt),
        )

        html = await _regenerate_ui_html_with_realtime_timeout(
            title=title,
            intent=intent,
            visual_prompt=visual_prompt,
            learner_text=learner_text,
            lesson_context=self.lesson_context,
        )
        checks: Dict[str, Any] = {}
        ui_id: Optional[str] = None

        if html:
            html = _ensure_generate_ui_asset(html, title=title, visual_prompt=visual_prompt)
            ui_id, checks = generative_ui.sanitize_and_store_with_checks(
                html, user_id=user_id, lesson_id=lesson_id
            )
            if not ui_id:
                failed = checks.get("failed") or []
                logger.warning(
                    "voice: generate_ui strong HTML rejected reasons=%s html_len=%d",
                    failed,
                    len(html),
                )
                repaired = await _regenerate_ui_html_with_realtime_timeout(
                    title=title,
                    intent=intent,
                    visual_prompt=visual_prompt,
                    learner_text=learner_text,
                    lesson_context=self.lesson_context,
                    repair_reasons=failed,
                )
                if repaired:
                    repaired = _ensure_generate_ui_asset(
                        repaired, title=title, visual_prompt=visual_prompt
                    )
                    ui_id, checks = generative_ui.sanitize_and_store_with_checks(
                        repaired, user_id=user_id, lesson_id=lesson_id
                    )
                    if not ui_id:
                        logger.warning(
                            "voice: generate_ui repaired HTML rejected reasons=%s html_len=%d",
                            checks.get("failed") or [],
                            len(repaired),
                        )

        if not ui_id:
            logger.warning(
                "voice: generate_ui failed closed reasons=%s had_strong_html=%s",
                checks.get("failed") or [],
                bool(html),
            )
            return None

        logger.info("voice: generate_ui OK ui_id=%s", ui_id)
        return {"title": title, "intent": intent, "ui_id": ui_id}


def _tool_argument_keys(call: Dict[str, Any]) -> list[str]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        return sorted(str(key) for key in arguments)
    if not isinstance(arguments, str):
        return []
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return []
    return sorted(str(key) for key in parsed) if isinstance(parsed, dict) else []


@llm_traceable(
    "voice_chat",
    tags=["agent:voice", "voice"],
    metadata={"agent": "voice"},
)
async def _voice_llm_call(
    system: str,
    messages: List[Dict[str, Any]],
    *,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """Voice httpx /chat/completions. Traced inputs exclude Authorization headers."""
    settings = get_settings()
    api_key = settings.resolved_voice_llm_api_key()
    if not api_key:
        raise RuntimeError("voice LLM key not set (VOICE_LLM_API_KEY / LLM_API_KEY)")

    payload: Dict[str, Any] = {
        # Widget tool calls (quiz, flashcards, …) carry large JSON argument payloads, so the
        # cap must be generous or the tool call is truncated into invalid JSON. Spoken replies
        # stay short on their own; this only bounds runaway generations.
        "model": settings.resolved_voice_llm_model(),
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": 0.35,
        "max_tokens": settings.voice_llm_max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = 120 if tools else 90
    base_url = settings.resolved_voice_llm_base_url()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    choice = data["choices"][0]["message"]
    raw_content = choice.get("content") or ""
    raw_calls = choice.get("tool_calls") or []

    # Some OpenAI-compatible models (Qwen on Nebius) intermittently emit the tool call in-band as
    # a <tool_call>{...}</tool_call> block in `content` instead of the structured tool_calls field.
    # Recover those so the widget still renders and the raw JSON is never spoken aloud.
    if not raw_calls:
        stripped, inline_calls = _parse_inline_tool_calls(raw_content)
        if inline_calls:
            return _clean_spoken_text(stripped), inline_calls
        return _clean_spoken_text(raw_content), None

    tool_calls: List[Dict[str, Any]] = []
    for index, call in enumerate(raw_calls):
        func = call.get("function") or {}
        tool_calls.append(
            {
                "id": call.get("id") or f"call_{index}",
                "type": "function",
                "function": {
                    "name": func.get("name") or "",
                    "arguments": func.get("arguments") or "{}",
                },
            }
        )
    return _clean_spoken_text(raw_content), tool_calls


def _openai_tool_specs(
    capabilities: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    for name, description, schema in _TOOL_DEFS:
        if name == "generate_ui":
            description = _VOICE_GENERATE_UI_DESC
            schema = VoiceGenerateUiTool
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": schema.model_json_schema(),
                },
            }
        )
    tools.extend(_page_tool_specs(capabilities))
    return tools


def realtime_tool_specs(
    capabilities: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return tool specs in the flat shape expected by OpenAI Realtime sessions."""
    specs: List[Dict[str, Any]] = []
    for spec in _openai_tool_specs(capabilities):
        function = spec.get("function") or {}
        specs.append(
            {
                "type": "function",
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "parameters": function.get("parameters") or {},
            }
        )
    return specs


_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL | re.IGNORECASE)
_TOOL_CALL_TAG_RE = re.compile(r"</?tool_call>", re.IGNORECASE)
# A JSON object that carries the tool-call signature (a "name" plus "arguments"/"parameters").
# Some models emit this bare into `content` with no <tool_call> wrapper; it must never be spoken.
_BARE_TOOL_JSON_RE = re.compile(
    r"\{[^{}]*\"name\"\s*:\s*\"[^\"]+\"[\s\S]*?\"(?:arguments|parameters)\"\s*:\s*[\[{][\s\S]*",
    re.IGNORECASE,
)


def _latest_user_text(messages: List[Dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return (message.get("content") or "").strip()
    return ""


def _parse_inline_tool_calls(content: str) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """Extract <tool_call>{...}</tool_call> blocks a model leaked into content.

    Returns (content_without_blocks, tool_calls) where tool_calls is None if nothing parseable
    was found. Also handles a single unclosed block (e.g. truncated output).
    """
    if not content or "<tool_call>" not in content.lower():
        return content, None

    calls: List[Dict[str, Any]] = []

    def _add(candidate: str) -> bool:
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            return False
        name = obj.get("name")
        if not name:
            return False
        args = obj.get("arguments", obj.get("parameters", {}))
        if not isinstance(args, str):
            args = json.dumps(args or {})
        calls.append(
            {
                "id": f"call_{len(calls)}",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
        return True

    matches = list(_TOOL_CALL_BLOCK_RE.finditer(content))
    if matches:
        for match in matches:
            _add(match.group(1))
        cleaned = _TOOL_CALL_BLOCK_RE.sub(" ", content)
    else:
        # Unclosed tag — parse everything after it (truncated generation). Whether or not the
        # partial JSON parses, DROP everything from the opening tag onward: a truncated tool call
        # must never be read aloud as raw JSON. Only the prose before the tag is speakable.
        idx = content.lower().find("<tool_call>")
        _add(content[idx + len("<tool_call>") :].strip())
        cleaned = content[:idx]

    cleaned = _TOOL_CALL_TAG_RE.sub(" ", cleaned)
    return cleaned.strip(), (calls or None)


def _clean_spoken_text(text: str) -> str:
    cleaned = _THINKING_RE.sub(" ", text or "")
    cleaned = _TOOL_CALL_TAG_RE.sub(" ", cleaned)
    # Last line of defense: strip any residual bare tool-call JSON so the TTS never reads a
    # raw {"name": ..., "arguments": ...} blob aloud (renders no widget either way).
    cleaned = _BARE_TOOL_JSON_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

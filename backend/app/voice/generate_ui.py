"""Voice Path B generate_ui — strong-model HTML capsule generation + extraction."""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from pydantic import BaseModel, Field

from ..capsule.postprocess import CHART_JS_CDN, THREE_JS_CDN
from ..core.config import get_settings
from ..core.tracing import traceable_run

logger = logging.getLogger(__name__)

VOICE_GENERATE_UI_STRONG_TIMEOUT_SECONDS = 30.0
VOICE_GENERATE_UI_MAX_TOKENS = 5500

def _trace_prepare_generate_ui_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    args = inputs.get("args") if isinstance(inputs.get("args"), dict) else {}
    visual_prompt = str(args.get("visual_prompt") or args.get("intent") or "")
    return {
        "title": args.get("title"),
        "intent": args.get("intent"),
        "visual_prompt_len": len(visual_prompt),
        "visual_prompt_preview": visual_prompt[:1000],
    }


def _trace_generate_ui_html_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    context = inputs.get("lesson_context") if isinstance(inputs.get("lesson_context"), dict) else {}
    visual_prompt = str(inputs.get("visual_prompt") or "")
    return {
        "title": inputs.get("title"),
        "intent": inputs.get("intent"),
        "visual_prompt_len": len(visual_prompt),
        "visual_prompt_preview": visual_prompt[:1000],
        "learner_text": inputs.get("learner_text"),
        "lesson_title": context.get("lesson_title"),
        "lesson_objective": context.get("lesson_objective"),
        "repair_reasons": inputs.get("repair_reasons"),
    }


def _trace_html_output(output: Optional[str]) -> Dict[str, Any]:
    html = output or ""
    return {"has_html": bool(html.strip()), "html_len": len(html)}


class VoiceGenerateUiTool(BaseModel):
    """Request a bespoke interactive visual without making the realtime voice model write HTML.

    Use this for visuals that require arbitrary canvas, animation, simulation, or a 3D scene. The
    server will ask the stronger LLM_MODEL to build the full sandboxed HTML capsule. Prefer
    render_ui for structured cards, charts, tables, steps, sliders, and small diagrams.
    """

    title: str = Field(description="Short title shown on the card header")
    intent: str = Field(description="One line describing what appears on screen, spoken by voice")
    visual_prompt: str = Field(
        description=(
            "Detailed request for the stronger model: what to visualize, what should move or be "
            "interactive, and what learner control is needed. Mention 3D/canvas only when required."
        )
    )


_VOICE_GENERATE_UI_DESC = (
    "Request a bespoke interactive HTML/canvas/3D visual. Provide title, intent, and a detailed "
    "visual_prompt only — do NOT write HTML. The server will generate the sandboxed capsule and "
    f"may use Chart.js only from {CHART_JS_CDN} and Three.js only from {THREE_JS_CDN}."
)

@traceable_run(
    "voice_generate_ui_html",
    run_type="llm",
    tags=["agent:voice", "voice"],
    metadata={"agent": "voice"},
    process_inputs=_trace_generate_ui_html_inputs,
    process_outputs=_trace_html_output,
)
async def _regenerate_ui_html_strong(
    *,
    title: str,
    intent: str,
    visual_prompt: str,
    learner_text: str,
    lesson_context: Dict[str, Any],
    repair_reasons: Optional[List[str]] = None,
) -> Optional[str]:
    """Generate or repair a Path B HTML capsule.

    The main lesson-generation model can spend its full budget in `reasoning_content` on some
    OpenAI-compatible providers, returning no HTML. For realtime tutor turns, first use the resolved
    voice LLM as a direct HTML writer because it has proven to emit normal message content quickly.

    Returns None on any failure so the caller fails closed.
    """
    settings = get_settings()
    api_key = settings.resolved_voice_llm_api_key()
    if not api_key:
        logger.info("voice: strong-regen skipped (no VOICE_LLM_API_KEY / LLM_API_KEY)")
        return None
    logger.info(
        "voice: strong-regen START (html model=%s repair=%s)",
        settings.resolved_voice_llm_model(),
        bool(repair_reasons),
    )

    repair_line = ""
    if repair_reasons:
        repair_line = (
            "\nREPAIR MODE: The previous HTML was rejected by the security/quality gate for: "
            + "; ".join(str(r) for r in repair_reasons)
            + ". Produce a corrected complete HTML document."
        )
    digest = str(lesson_context.get("artifact_digest") or "")[:1600]
    context_lines = [
        f"Course: {lesson_context.get('course_title') or 'Course'}",
        f"Lesson: {lesson_context.get('lesson_title') or 'Current lesson'}",
        f"Objective: {lesson_context.get('lesson_objective') or ''}",
        f"Archetype: {lesson_context.get('lesson_archetype') or 'explainer'}",
    ]
    if digest:
        context_lines.append(f"Lesson content digest: {digest}")

    payload: Dict[str, Any] = {
        "model": settings.resolved_voice_llm_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return ONLY one complete, compact, self-contained interactive HTML document. "
                    "No markdown, no prose before or after the document. The document MUST include "
                    "<!DOCTYPE html>, <body>, Tailwind from "
                    "https://cdn.tailwindcss.com, at least one <canvas>, at least one "
                    "<img go-data-src=\"/image?query=...\"> or <img go-data-src=\"/gen?prompt=...\">, "
                    "and at least one learner control (button/input/select). For standard charts "
                    f"(line/bar/scatter/pie), load Chart.js ONLY from this exact script URL: "
                    f"{CHART_JS_CDN}. If 3D is needed, "
                    f"load Three.js ONLY from this exact script URL: {THREE_JS_CDN}. Do not use "
                    "ES modules, importmaps, workers, blob URLs, window.parent/window.top, "
                    "localStorage/sessionStorage, or any other external script. Use inline CSS/JS "
                    "and keep the visual focused, labelled, and interactive. Keep the document "
                    "compact enough for a realtime tutor turn: one canvas, one small control panel, "
                    "plain JavaScript, no framework-style architecture. If you cannot implement "
                    "every requested feature, implement a small working version of the requested "
                    "concept rather than a generic placeholder."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Build the interactive visual requested by the voice tutor.\n\n"
                    + "\n".join(context_lines)
                    + f"\nLearner said: {learner_text or '(not available)'}"
                    + f"\nTitle: {title}"
                    + f"\nSpoken intent: {intent}"
                    + f"\nVisual prompt: {visual_prompt}"
                    + repair_line
                ),
            },
        ],
        "temperature": 0.4,
        "max_tokens": min(max(3000, settings.llm_max_tokens), VOICE_GENERATE_UI_MAX_TOKENS),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=VOICE_GENERATE_UI_STRONG_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.resolved_voice_llm_base_url()}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        html = _extract_generated_html_from_response(data)
        if not html:
            choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
            message = choice.get("message") if isinstance(choice, dict) else {}
            reasoning_len = len(message.get("reasoning_content") or "") if isinstance(message, dict) else 0
            logger.info(
                "voice: strong-regen returned no html finish=%s reasoning_len=%d",
                choice.get("finish_reason") if isinstance(choice, dict) else None,
                reasoning_len,
            )
        return html
    except Exception:
        logger.exception("voice: strong-model generate_ui regeneration failed")
        return None


def _ensure_generate_ui_asset(html: str, *, title: str, visual_prompt: str) -> str:
    if not html or re.search(r"<img\b", html, flags=re.I):
        return html
    safe_alt = html_lib.escape(title or "Interactive visual", quote=True)
    query = quote_plus((title or visual_prompt or "interactive learning visual")[:120])
    image = f'<img alt="{safe_alt}" go-data-src="/image?query={query}&aspect=16:9" class="sr-only">'
    body_match = re.search(r"<body\b[^>]*>", html, flags=re.I)
    if body_match:
        insert_at = body_match.end()
        return html[:insert_at] + "\n  " + image + html[insert_at:]
    return html


def _extract_generated_html_from_response(data: Dict[str, Any]) -> Optional[str]:
    """Extract a generated capsule from common OpenAI-compatible response shapes."""
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(message, dict):
        return None

    calls = message.get("tool_calls") or []
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            html = _extract_html_from_arguments(function.get("arguments"))
            if html:
                return html

    function_call = message.get("function_call")
    if isinstance(function_call, dict):
        html = _extract_html_from_arguments(function_call.get("arguments"))
        if html:
            return html

    return _extract_html_from_text(message.get("content"))


def _extract_html_from_arguments(arguments: Any) -> Optional[str]:
    if isinstance(arguments, dict):
        return _first_html_value(arguments)
    if not isinstance(arguments, str) or not arguments.strip():
        return None
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return _extract_html_from_text(arguments)
    if isinstance(parsed, dict):
        return _first_html_value(parsed)
    if isinstance(parsed, str):
        return _extract_html_from_text(parsed)
    return None


def _first_html_value(args: Dict[str, Any]) -> Optional[str]:
    for key in ("html", "document", "code", "content"):
        value = args.get(key)
        if isinstance(value, str):
            html = _extract_html_from_text(value)
            if html:
                return html
    return None


def _extract_html_from_text(text: Any) -> Optional[str]:
    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        html = _first_html_value(parsed)
        if html:
            return html

    fence = re.search(r"```(?:html)?\s*(.*?)```", raw, flags=re.I | re.S)
    if fence:
        raw = fence.group(1).strip()

    doc = re.search(r"<!doctype html\b.*?</html>", raw, flags=re.I | re.S)
    if doc:
        return doc.group(0).strip()
    lowered = raw.lower()
    if "<html" in lowered and "</html>" in lowered:
        start = lowered.find("<html")
        end = lowered.rfind("</html>") + len("</html>")
        return "<!DOCTYPE html>\n" + raw[start:end].strip()
    return raw if "<body" in lowered and "</body>" in lowered else None



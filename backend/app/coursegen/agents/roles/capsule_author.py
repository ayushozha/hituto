"""capsule-author — HTML (graph.generate) + optional A2UI lesson emission (Phase 5)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

ROLE_NAME = "capsule_author"

logger = logging.getLogger(__name__)

# Archetypes that fit the A2UI vocabulary well (no bespoke canvas/3D).
A2UI_ELIGIBLE_ARCHETYPES = frozenset({"explainer", "narrative", "tool"})


# Design type (resolved presentation) → shell skill injected into the author prompt.
_BRAND_SKILL = "hituto-generated-lesson-design"
_DESIGN_SKILLS = {
    "page": "ui-page-style",
    "studio": "ui-studio-style",
    "slide": "ui-slide-deck",
}

_DESIGN_HEADERS = {
    "page": (
        "## Page shell — REQUIRED for this lesson\n"
        "Build the scrollable interactive mini-app described below — not a slide deck, not the "
        "studio shell.\n"
    ),
    "studio": (
        "## Studio v2 shell — REQUIRED for this lesson\n"
        "Follow the selected specimen, simulation, or process-cutaway reference below. Keep a "
        "dominant live stage and wire only asset-supported controls. If a mesh manifest exists, "
        "use it in specimen mode without starting another WebGL loop.\n"
    ),
    "slide": (
        "## Slide-deck shell — REQUIRED for this lesson\n"
        "Build the stepped slide deck described below — one idea per slide with prev/next "
        "controls, not a long scroll article.\n"
    ),
}

# Lesson archetype → skill folder injected after the design shell (playable / sim contracts).
_ARCHETYPE_SKILLS = {
    "game": "game",
    "simulation": "simulation",
}

_ARCHETYPE_HEADERS = {
    "game": (
        "## Game archetype — REQUIRED for this lesson\n"
        "Follow the playable mini-game skill below. Ship a working goal → play → feedback → "
        "reset loop (not a quiz card or dead canvas).\n"
    ),
    "simulation": (
        "## Simulation archetype — REQUIRED for this lesson\n"
        "Follow the simulation skill below. Ship parameterize → play/step → readout "
        "(not a scored mini-game unless the plan also demands one).\n"
    ),
}


def capsule_author_subagent(
    subject: str | None = None,
    *,
    design: str = "page",
    archetype: str = "explainer",
) -> dict:
    """Deep Agent subagent dict: authors the HTML capsule to /build/capsule.html (§4).

    The resolved design type (`page` | `studio` | `slide`) selects the shell skill injected
    into the author prompt — the design shell is mandatory for the lesson, so it is injected
    directly rather than left to on-demand skill discovery. Game / simulation archetypes also
    get their playable / parameter-loop skill after the shell.
    """
    from ..prompt_loader import load_agent_prompt, load_skill

    prompt = load_agent_prompt(
        "capsule_author",
        "You are the capsule author. Write ONE complete, self-contained HTML document to "
        "/build/capsule.html via write_file: Tailwind CDN, at least one <canvas> or SVG "
        "graphic with an interactive control. Prefer drawn visuals over /gen images. "
        "Never use window.parent, window.top, or localStorage. Close with </body></html>.",
    )
    design = design if design in _DESIGN_SKILLS else "page"
    brand = load_skill(_BRAND_SKILL)
    if brand:
        prompt = (
            f"{prompt}\n\n## Shared Hi Tuto lesson design — REQUIRED for every shell\n"
            f"{brand}"
        )
    shell = load_skill(_DESIGN_SKILLS[design])
    if shell:
        prompt = f"{prompt}\n\n{_DESIGN_HEADERS[design]}\n{shell}"
    arch = (archetype or "explainer").lower()
    skill_name = _ARCHETYPE_SKILLS.get(arch)
    if skill_name:
        arch_body = load_skill(skill_name)
        if arch_body:
            prompt = (
                f"{prompt}\n\n{_ARCHETYPE_HEADERS[arch]}\n{arch_body}"
            )
    return {
        "name": "capsule_author",
        "description": (
            "Author one self-contained interactive HTML lesson capsule and write it to "
            "/build/capsule.html via write_file."
        ),
        "system_prompt": prompt,
    }

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / "agents" / "capsule_author_a2ui.md"
)


def a2ui_eligible(archetype: str | None, *, enabled: bool) -> bool:
    if not enabled:
        return False
    return (archetype or "explainer").lower() in A2UI_ELIGIBLE_ARCHETYPES


def _clean(content: str) -> str:
    content = _THINK.sub("", content or "").strip()
    return _FENCE.sub("", content).strip()


def _system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "Emit ONLY JSON {title, intent, root} using A2UI node types "
            "stack/heading/text/callout/math/steps/quiz/table/chart/slider/diagram."
        )


def _fallback_tree(plan: dict) -> dict[str, Any]:
    """Deterministic interactive A2UI tree when the LLM fails (offline / parse errors)."""
    title = plan.get("title") or "Lesson"
    objective = plan.get("subtitle") or plan.get("objective") or f"Learn {title}."
    sections = plan.get("sections") or []
    children: list[dict] = []
    for sec in sections[:6]:
        st = sec.get("title") or "Section"
        body = re.sub(r"<[^>]+>", "", sec.get("body") or sec.get("objective") or "")
        blurb = (body.strip() or f"Key idea for {st}.")[:280]
        children.append({"type": "heading", "props": {"text": st, "level": 2}, "children": []})
        children.append(
            {"type": "callout", "props": {"text": blurb, "variant": "info"}, "children": []}
        )
        children.append(
            {
                "type": "steps",
                "props": {
                    "steps": [
                        {"title": "Notice", "detail": f"What stands out about {st}?"},
                        {"title": "Connect", "detail": "Link this to what you already know."},
                        {"title": "Check", "detail": "Answer the quick quiz."},
                    ]
                },
                "children": [],
            }
        )
        children.append(
            {
                "type": "quiz",
                "props": {
                    "topic": st,
                    "questions": [
                        {
                            "type": "mcq",
                            "title": "Quick check",
                            "prompt": f"What is the main takeaway of “{st}”?",
                            "options": [
                                blurb[:80] or "The core idea of this section",
                                "An unrelated fact",
                                "None of the above",
                            ],
                            "correctAnswer": "0",
                            "explanation": blurb or "Re-read the callout.",
                            "hints": ["Skim the callout."],
                        }
                    ],
                },
                "children": [],
            }
        )
    if not children:
        children.append(
            {
                "type": "callout",
                "props": {
                    "text": "Explore the ideas above, then check your understanding with the tutor.",
                    "variant": "info",
                },
                "children": [],
            }
        )
        children.append(
            {
                "type": "quiz",
                "props": {
                    "topic": title,
                    "questions": [
                        {
                            "type": "mcq",
                            "title": "Check",
                            "prompt": f"Can you explain “{title}” in one sentence?",
                            "options": ["Yes", "Not yet", "I need a hint"],
                            "correctAnswer": "0",
                            "explanation": "Teaching it back is the best check.",
                            "hints": ["Start with the objective."],
                        }
                    ],
                },
                "children": [],
            }
        )
    return {
        "title": title,
        "intent": objective[:200],
        "root": {"type": "stack", "props": {"direction": "vertical", "gap": "md"}, "children": children},
    }


async def author_a2ui_lesson(plan: dict) -> dict[str, Any] | None:
    """Produce a normalized A2UI document for the lesson plan, or None on hard failure.

    Uses the shared `a2ui` schema (not the tutor `render_ui` runtime tool).
    """
    from ....a2ui import normalize_render_ui
    from ....providers.registry import get_coursegen_llm

    fallback = _fallback_tree(plan)
    try:
        llm = get_coursegen_llm()
        user = (
            f"Lesson title: {plan.get('title')}\n"
            f"Objective: {plan.get('subtitle') or plan.get('objective') or ''}\n"
            f"Archetype: {plan.get('archetype') or 'explainer'}\n"
            f"Difficulty: {plan.get('difficulty') or 'intermediate'}\n"
            f"Sections JSON: {json.dumps(plan.get('sections') or [])[:4000]}\n"
            f"Facts: {json.dumps(plan.get('facts') or [])[:1500]}\n"
            "Build one focused INTERACTIVE A2UI surface for this lesson. "
            "REQUIRED: each section must include quiz OR slider OR chart OR steps OR diagram — "
            "never heading+text essays. The host already renders the lesson title and objective; "
            "start directly with the first section heading and do not repeat the lesson title."
        )
        raw = await llm.generate_html(_system_prompt(), user)
        data = json.loads(_clean(raw))
        root = data.get("root") or data
        # Soft-guard: essay-only trees get a quiz injected before normalize.
        if isinstance(root, dict):
            from ...a2ui_sections import _enrich_if_text_only, _is_interactive

            title = str(data.get("title") or plan.get("title") or "Lesson")
            root = _enrich_if_text_only(root, title)
            if not _is_interactive(root):
                raise ValueError("A2UI lesson is text-only")
        normalized = normalize_render_ui(
            {
                "title": data.get("title") or plan.get("title") or "Lesson",
                "intent": data.get("intent") or plan.get("subtitle") or "",
                "root": root,
            }
        )
        if normalized:
            return normalized
    except Exception as exc:  # noqa: BLE001
        logger.warning("A2UI capsule-author LLM path failed; using fallback tree: %s", exc)

    normalized = normalize_render_ui(fallback)
    return normalized

"""fast_gen Phase 5 (GEN_SECTION_FANOUT): per-section parallel lesson authoring.

Instead of one whole-document LLM call, each plan section is authored by its own
concurrent call producing a single ``<section>`` fragment against a **server-owned
document shell** (head, Tailwind config with the Hi Tuto brand tokens, fonts, base
styles). Fragments stream to the generating user's shell iframe as they generate
(`gen_fragment` frames carrying ``section_id``), the page visibly assembles, and the
assembled document then passes the full capsule gate in ``post_process`` exactly like
a whole-document lesson.

Fail-closed at every level: an invalid or text-only fragment retries once, then
degrades to a deterministic section (plan draft + minimal SVG stub); if every
section degrades, the caller falls back to the whole-document author.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from typing import Any, Awaitable, Callable

from ..capsule.postprocess import GLTF_LOADER_CDN, THREE_JS_CDN
from ..capsule.shell import lesson_shell
from ..core.config import get_settings

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:html)?\s*|\s*```$", re.MULTILINE)
_FORBIDDEN_RE = re.compile(r"<(?:!doctype|html|head|body)\b", re.I)


def build_shell(plan: dict) -> tuple[str, str]:
    """(head, tail) of the server-owned zinc document shell fragments assemble into."""
    return lesson_shell(plan)


SECTION_SYSTEM = f"""You are an expert interactive-lesson author for Hi Tuto. You write EXACTLY ONE
self-contained HTML <section> fragment that a server inserts into an existing page shell.
The shell already loads Tailwind (CDN) with zinc-neutral Hi Tuto brand tokens — colors
paper/sand/surface, ink (+soft/faint), line, cobalt (+dark/soft), lime (+dark/soft), coral,
grass, mint, lilac, peach, sky, plum; font families display/sans (Plus Jakarta Sans) and mono;
borderRadius 4xl; shadows card/press — plus brand fonts, Chart.js, and overflow clamps.

OUTPUT CONTRACT (violations get your output discarded):
- Output ONLY the fragment: exactly one
  <section id="section-SLUG" data-lesson-section="SLUG" data-lesson-title="TITLE"> … </section>
  using the SLUG and TITLE given in the brief. No <!DOCTYPE>, <html>, <head>, <body>,
  no page title/intro header/nav/sidebar/table of contents, no markdown fences, no prose
  outside the tag.
- Style with Tailwind utility classes (brand tokens above). If you need custom CSS, include
  ONE <style> inside the section and prefix EVERY selector with [data-lesson-section="SLUG"].
- All JavaScript in ONE <script> inside the section, wrapped in an IIFE, touching only
  elements inside this section. Prefix every element id you create with "SLUG-".
  Never reference window.parent/window.top, storage, or fetch.
- REQUIRED VISUAL: every section MUST include at least one drawn graphic — an inline <svg>
  and/or a <canvas> — wired to at least one working control (range input, buttons, or tabs)
  that updates the drawing. Text-only sections are rejected. Chart.js is already loaded
  (do not add script tags for it). For 3D only, these exact URLs are allowed:
  {THREE_JS_CDN} and {GLTF_LOADER_CDN}.
- Do NOT use decorative /gen image art as the teaching graphic. Optional real-world photo only
  when the concept needs a photograph:
    <img go-data-src="/image?query=URL_ENCODED" alt="...">
  Prefer canvas/SVG whenever the idea can be drawn.
- Design: zinc paper canvas, ink text, lime primary actions, mint soft fills; rounded-3xl panels;
  no warm-cream nostalgia palette, no purple gradients, no gray/slate scales, no black borders;
  controls at least 44px tall; max-width 100% — no horizontal overflow.
- Interactions assigned in the brief must be REAL working controls wired to visible output,
  never mockups or placeholders. Keep copy tight and concrete — the graphic teaches; prose supports.
"""


_VISUAL_RE = re.compile(r"<(?:svg|canvas)\b", re.I)


def sections_eligible(plan: dict, state: dict) -> bool:
    """Fan-out only for multi-section page lessons authored from scratch.

    Simulations/games stay whole-document — they are one coherent interactive app, not a
    sequence of independent sections. Refinements/targeted edits keep the whole-document
    path because they transform existing HTML.
    """
    settings = get_settings()
    if not settings.gen_section_fanout:
        return False
    if state.get("previous_html") or state.get("target_html"):
        return False
    archetype = str(
        plan.get("archetype") or (state.get("knobs") or {}).get("archetype") or "explainer"
    ).lower()
    if archetype in ("simulation", "game"):
        return False
    sections = plan.get("sections") or []
    return len(sections) >= 2


def _slug(section: dict, index: int) -> str:
    raw = str(section.get("id") or f"part-{index + 1}")
    slug = re.sub(r"[^a-z0-9-]", "-", raw.lower()).strip("-")
    return slug or f"part-{index + 1}"


def build_section_user_prompt(plan: dict, index: int) -> str:
    sections = plan.get("sections") or []
    section = sections[index]
    slug = _slug(section, index)
    siblings = [
        f"  {i + 1}. {s.get('title')} — {s.get('objective') or ''}"
        for i, s in enumerate(sections)
        if i != index
    ]
    interactions = plan.get("interactions") or []
    assigned = [
        w for i, w in enumerate(interactions) if i % max(len(sections), 1) == index
    ]
    visual = (
        "\nREQUIRED: include at least one inline <svg> or <canvas> that teaches this section's"
        " idea, plus a working control (slider or buttons) that updates it."
        " Do not use a /gen image as the graphic. Text alone is not enough."
    )
    facts = "\n".join(
        f"- {f['claim']} (source: {f['source_url']})" for f in plan.get("facts", [])
    )
    photo_hint = ""
    if section.get("image"):
        photo_hint = (
            f"\nOptional real-world photo reference (only if a photograph teaches better than "
            f"a drawn diagram): {section.get('image')} — otherwise draw it on canvas/SVG."
        )
    return f"""Write section {index + 1} of {len(sections)} for the "{plan.get('archetype', 'explainer')}" lesson "{plan.get('title')}".
Audience difficulty: {plan.get('difficulty', 'intermediate')}.

YOUR SECTION — SLUG="{slug}", TITLE="{section.get('title')}":
Objective: {section.get('objective') or ''}
Draft content to build on (rewrite freely, keep the substance):
{section.get('body') or '(none)'}
{photo_hint}
{visual}

Interactions assigned to THIS section (build each as a real working widget):
{json.dumps(assigned, indent=2) if assigned else '  (none — still add a small SVG/canvas + control)'}

The OTHER sections of this lesson (do NOT cover their material, do not add navigation to them):
{chr(10).join(siblings) or '  (none)'}

Verified facts you may use:
{facts or '  (none — use self-contained, clearly illustrative data)'}
"""


def _clean_fragment(raw: str, *, slug: str | None = None, title: str | None = None) -> str | None:
    """Extract and validate one <section> fragment; None if unusable or text-only."""
    from .html_sections import stamp_section_attrs

    text = _FENCE_RE.sub("", raw or "").strip()
    start = text.lower().find("<section")
    end = text.lower().rfind("</section>")
    if start == -1 or end == -1 or end <= start:
        return None
    fragment = text[start : end + len("</section>")]
    if _FORBIDDEN_RE.search(fragment):
        return None
    if len(fragment) < 200:  # degenerate output
        return None
    if not _VISUAL_RE.search(fragment):
        return None
    if slug:
        fragment = stamp_section_attrs(fragment, slug, title)
    return fragment


def fallback_section(plan: dict, index: int) -> str:
    """Deterministic visual section from the plan draft — never fails.

    Includes a minimal SVG so the capsule visual gate and theater stay non-empty
    when the LLM could not produce a valid fragment.
    """
    section = (plan.get("sections") or [])[index]
    slug = _slug(section, index)
    title = str(section.get("title") or f"Part {index + 1}")
    body = str(section.get("body") or "").strip() or (
        f"<p>{section.get('objective') or ''}</p>"
    )
    return (
        f'<section id="section-{slug}" data-lesson-section="{slug}" '
        f'data-lesson-title="{title}" class="rounded-3xl border border-line bg-white p-8">\n'
        f'<h2 class="font-display text-2xl font-extrabold text-ink">{title}</h2>\n'
        f'<div class="mt-4 space-y-4 text-ink-soft">{body}</div>\n'
        f'<figure class="mt-6 rounded-2xl border border-line bg-paper p-4">'
        f'<svg viewBox="0 0 240 120" width="100%" height="120" role="img" '
        f'aria-label="Diagram placeholder for {title}">'
        f'<rect x="8" y="8" width="224" height="104" rx="12" fill="#F4F4F5" stroke="#E4E4E7"/>'
        f'<circle cx="80" cy="60" r="28" fill="none" stroke="#16A34A" stroke-width="3"/>'
        f'<circle cx="130" cy="60" r="18" fill="none" stroke="#16A34A" stroke-width="3"/>'
        f'<text x="120" y="100" text-anchor="middle" fill="#71717A" font-size="11">'
        f'{title[:40]}</text></svg></figure>\n</section>'
    )


async def author_sections(
    *,
    plan: dict,
    llm: Any,
    streamer_factory: Callable[[str], Any] | None = None,
    on_section_done: Callable[[str, bool], Awaitable[None]] | None = None,
) -> str | None:
    """Author all plan sections concurrently; return the assembled document.

    Returns None when every section degraded to its fallback — a systemic failure the
    caller should answer with the whole-document author (fail-closed).
    """
    sections = plan.get("sections") or []
    settings = get_settings()
    sem = asyncio.Semaphore(max(1, settings.gen_section_concurrency))
    supports_stream = "on_delta" in inspect.signature(llm.generate_html).parameters

    async def one(index: int) -> tuple[str, bool]:
        section = sections[index]
        slug = _slug(section, index)
        title = str(section.get("title") or f"Part {index + 1}")
        system = SECTION_SYSTEM.replace("SLUG", slug).replace("TITLE", title)
        user = build_section_user_prompt(plan, index)
        streamer = streamer_factory(slug) if streamer_factory else None
        async with sem:
            for attempt in (1, 2):
                try:
                    if streamer is not None and supports_stream:
                        raw = await llm.generate_html(
                            system, user, on_delta=streamer.on_delta
                        )
                        await streamer.flush(final=True)
                    else:
                        raw = await llm.generate_html(system, user)
                except Exception as exc:  # noqa: BLE001 — degrade, never crash the lesson
                    logger.warning("section %s author failed (try %d): %s", slug, attempt, exc)
                    continue
                fragment = _clean_fragment(raw, slug=slug, title=title)
                if fragment:
                    return fragment, True
                user += (
                    "\n\nREPAIR: your previous output was rejected. Output ONLY one valid "
                    "<section …>…</section> fragment that includes an inline <svg> or "
                    "<canvas> plus a working control. No text-only sections."
                )
        return fallback_section(plan, index), False

    results = await asyncio.gather(*(one(i) for i in range(len(sections))))
    if on_section_done:
        for i, (_, ok) in enumerate(results):
            await on_section_done(_slug(sections[i], i), ok)
    if not any(ok for _, ok in results):
        return None
    head, tail = build_shell(plan)
    return head + "\n\n".join(fragment for fragment, _ in results) + "\n" + tail

"""The generation prompt contract (design.md §3.3) — faithful to the paper's
system instructions: build interactive apps first, no placeholders, Tailwind via
CDN, images via the lazy go-data-src pattern resolved at runtime.
"""
from __future__ import annotations

import json

from functools import lru_cache
from pathlib import Path

from ..capsule.postprocess import CHART_JS_CDN, GLTF_LOADER_CDN, THREE_JS_CDN

_PROMPTS = Path(__file__).resolve().parent / "prompts"
_SKILLS = Path(__file__).resolve().parent / "skills"


@lru_cache
def _load_prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def _load_skill(name: str) -> str:
    # Not cached: skill markdown is iterated often; stale prompts are worse than a cheap read.
    return (_SKILLS / name / "SKILL.md").read_text(encoding="utf-8").rstrip("\n")


# Substitute the single source-of-truth library URLs so the prompt, the postprocess
# allowlist, and the artifact CSP can never drift out of sync (a plain .replace, not
# .format, because the prompt contains literal `{`/`}` in its Tailwind config block).
SYSTEM = (
    _load_prompt("lesson_system")
    .replace("{{THREE_JS_CDN}}", THREE_JS_CDN)
    .replace("{{GLTF_LOADER_CDN}}", GLTF_LOADER_CDN)
    .replace("{{CHART_JS_CDN}}", CHART_JS_CDN)
    + "\n\n## Shared Hi Tuto lesson design skill\n"
    + _load_skill("hituto-generated-lesson-design")
)


def build_user_prompt(plan: dict, previous_html: str | None = None) -> str:
    """Natural-language brief for real LLMs + a machine-readable plan block the
    stub provider renders deterministically."""
    facts = "\n".join(f"- {f['claim']} (source: {f['source_url']})" for f in plan.get("facts", []))
    sections = "\n".join(f"  {i+1}. {s['title']} — {s['objective']}" for i, s in enumerate(plan["sections"]))
    grounding = _grounding_block(plan.get("source_pack") or [])
    figures = _source_figures_block(plan.get("source_figures") or [], plan.get("source_document_id"))
    brief = f"""Build interactive sections for a "{plan['archetype']}" lesson whose host title is "{plan['title']}".
Audience difficulty: {plan.get('difficulty','intermediate')}.
Start directly with the first learning section. Do not generate a page title, intro header, module
label, section navigation, sidebar, fixed rail, or nested documentation layout. Include these sections:
{sections}

Implement these interaction specs as working controls, not mockups:
{json.dumps(plan.get('interactions', []), indent=2)}

Verified facts you may use:
{facts or '  (none — use self-contained, clearly illustrative data)'}
"""
    if previous_html:
        target_block = ""
        tid = plan.get("target_id")
        thtml = plan.get("target_html")
        if thtml:
            target_block = f"""
TARGETED EDIT — modify ONLY this subtree (id={tid or "unknown"}). Preserve all other HTML, scripts, and layout.
TARGET OUTER HTML:
```html
{thtml[:12000]}
```
"""
        brief = f"""You are refining an existing HTML page. YOUR GOAL IS TO APPLY THE USER'S CHANGE REQUEST TO THE PROVIDED HTML.
DO NOT completely rewrite the page from scratch. PRESERVE the existing widgets, layout, styling, and complex logic, modifying only what is necessary to fulfill the change request.
{target_block}
EXISTING HTML:
```html
{previous_html}
```

CHANGE REQUEST / PLAN:
{brief}
"""
    trace = _trace_block(plan.get("simulation_trace"))
    compute = _compute_block(plan)
    presentation = _presentation_block(plan)
    mesh = _mesh_block(plan)
    learner = _learner_block(plan)
    archetype_skill = _archetype_skill_block(plan)
    # Never put mesh bytes in the LLM prompt (Nebius 400 / huge traces).
    plan_for_llm = dict(plan)
    ma = plan_for_llm.get("mesh_artifact")
    if isinstance(ma, dict) and ma.get("data_b64"):
        plan_for_llm["mesh_artifact"] = {**ma, "data_b64": None}
    return (
        grounding
        + figures
        + trace
        + compute
        + presentation
        + mesh
        + learner
        + archetype_skill
        + brief
        + "\n\n<<PLAN>>"
        + json.dumps(plan_for_llm)
        + "<<END>>"
    )


def build_generation_repair_suffix(prior_html: str, failed: list[str], attempt: int) -> str:
    """Extra user prompt when the generate↔post_process loop retries after failed checks."""
    if not failed:
        return ""
    lines = [
        f"\n\n--- REPAIR ATTEMPT {attempt} ---",
        f"The previous HTML failed validation: {failed}",
        "Output a COMPLETE HTML document ending with </body></html>.",
    ]
    if any("truncated" in f for f in failed):
        lines.append(
            "The prior output was TRUNCATED (too long). Write a SHORTER page: fewer sections, "
            "tighter copy, same required canvas + interactive controls + lazy go-data-src images."
        )
    if prior_html:
        tail = prior_html[-12000:] if len(prior_html) > 12000 else prior_html
        lines.append(f"\nPrior output to fix or replace:\n```html\n{tail}\n```")
    return "\n".join(lines)


# Archetype → coursegen skill folder injected into the user brief (game / simulation).
_ARCHETYPE_SKILLS = {
    "game": "game",
    "simulation": "simulation",
}


def _archetype_skill_block(plan: dict) -> str:
    """Inject playable game / simulation authoring skill when the plan archetype matches."""
    arch = str(plan.get("archetype") or "explainer").lower()
    skill_name = _ARCHETYPE_SKILLS.get(arch)
    if not skill_name:
        return ""
    try:
        body = _load_skill(skill_name)
    except OSError:
        return ""
    if not body:
        return ""
    header = (
        f"## Archetype skill — REQUIRED for this {arch} lesson\n"
        f"Follow the `{skill_name}` skill below. Ship a working interactive surface "
        f"(not a mockup).\n\n"
    )
    return header + body + "\n\n"


def _trace_block(trace: dict | None) -> str:
    """Pass a sandbox-verified simulation trace to the artifact as DATA (task 33). The page renders
    it on a canvas (step/replay) — it must NOT recompute anything at runtime (R6.6)."""
    if not trace:
        return ""
    return (
        "PRECOMPUTED SIMULATION TRACE — render this as an interactive canvas the learner can step "
        "through and replay. Use ONLY these values; DO NOT recompute anything client-side.\n"
        f"{json.dumps(trace)[:3000]}\n\n"
    )


def _presentation_block(plan: dict) -> str:
    """Route capsule-author to the correct shell skill from knobs.presentation."""
    from .presentation import resolve_presentation

    mode = resolve_presentation(plan, plan.get("knobs") if isinstance(plan.get("knobs"), dict) else None)
    plan["presentation"] = mode
    if mode == "studio":
        from .studio_manifest import resolve_studio_mode

        studio_mode = resolve_studio_mode(plan, plan.get("knobs"))
        return (
            f"PRESENTATION = studio; STUDIO MODE = {studio_mode} — MANDATORY:\n"
            "- Preserve the Studio v2 hierarchy: selection/input | dominant live stage | "
            "explanation/evidence, with playback or timeline controls below when the mode needs it.\n"
            "- Every control must change lesson state and produce an immediate visible response.\n"
            "- Do not recreate the old eight-card specimen dashboard or duplicate title/progress/tutor UI.\n"
            "- Keep concise domain-specific labels, one scene owner, responsive drawers, keyboard access, "
            "and a usable reduced-motion path.\n"
            "- When data-mesh-src is present: do NOT start a second Three.js loop.\n"
            "- data-lesson-section / data-lesson-control tutor hooks on every major block/control.\n\n"
        )
    if mode == "slide":
        return (
            "PRESENTATION = slide (skills/ui-slide-deck) — MANDATORY:\n"
            "- Horizontal or stepped slide deck (one idea per slide), not a long scroll article.\n"
            "- Prev/Next controls with data-lesson-control; progress dots; keep each slide short.\n"
            "- Still include one canvas viz + one go-data-src image + one interactive control.\n"
            "- Use the shared Hi Tuto cream, forest, lime, and lilac design contract.\n\n"
        )
    if mode == "game":
        return (
            "PRESENTATION = game (GameManifest / ui-game-style) — MANDATORY:\n"
            "- Stage-first toon gallery: Goal, #stage3d, Next/Reset, Visited N/M, plaque.\n"
            "- Characters only from /game-kits/toon/; classic Three.js + GLTFLoader pins.\n"
            "- Prefer the server GameManifest path; do not freestyle a second Three.js loop.\n\n"
        )
    return (
        "PRESENTATION = page — responsive scrollable interactive mini-app using the shared Hi Tuto "
        "design skill. Start with the first content section; do not render the host-owned lesson "
        "title, an intro header, or navigation controls. Do not build a fixed documentation rail or "
        "use the Canvas Studio shell unless the plan also sets needs_3d.\n\n"
    )


def _learner_block(plan: dict) -> str:
    """Learner-profile directives (specs/learner_profile) — only when a knobs snapshot exists."""
    context = plan.get("learner_profile")
    if not isinstance(context, dict) or not context:
        return ""
    from ..services.profile_service import prompt_lines

    lines = prompt_lines(context, consumer="coursegen")
    if not lines:
        return ""
    return (
        "LEARNER PROFILE — adapt the presentation and structure of this lesson to these "
        "learner preferences:\n- " + "\n- ".join(lines) + "\n\n"
    )


def _mesh_block(plan: dict) -> str:
    """Hint capsule-author to embed Hunyuan mesh inside the studio stage when 3D is gated on."""
    from .presentation import resolve_presentation

    mesh = plan.get("mesh_artifact")
    mesh_path = plan.get("mesh_url") or (mesh or {}).get("path")
    wants_mesh = bool(mesh_path or plan.get("needs_3d"))
    if not wants_mesh:
        return ""
    # Mesh implies studio chrome even if presentation was page (spatial 3D always needs a stage).
    if resolve_presentation(plan) != "studio":
        plan["presentation"] = "studio"
    fallback = plan.get("mesh_fallback")
    lines = [
        "HUNYUAN 3D MESH — embed in the Canvas Studio center stage (clipped card):",
        "- <canvas id=\"studio-canvas\" width=\"640\" height=\"420\">; stage card overflow:hidden",
        "- Load <script src=\"" + THREE_JS_CDN + "\"></script> AND <script src=\"" + GLTF_LOADER_CDN + "\"></script>",
        "- Mesh holder: data-mesh-src=\"/build/mesh/model.glb\" data-mesh-canvas=\"studio-canvas\"",
        "- Do NOT start a second Three.js loop when the mesh holder is present",
        "- Focus selection updates the stage annotation and evidence rail",
    ]
    catalog = plan.get("mesh_catalog") or plan.get("studio_subjects")
    if catalog:
        lines.append("STUDIO SUBJECT CATALOG — wire the specimen selector to these managed meshes:")
        for entry in catalog[:12]:
            mid = entry.get("id")
            name = entry.get("name")
            src = entry.get("meshSrc") or entry.get("path") or "/build/mesh/model.glb"
            strat = entry.get("mesh_strategy") or "procedural"
            lines.append(f'  - id={mid!r} name={name!r} meshSrc="{src}" strategy={strat}')
        lines.append(
            "Fill subject-list buttons from this catalog; on click set mesh-holder data-mesh-src "
            "and call window.__hitutoReloadMesh(holder)."
        )
    if mesh_path:
        lines.append(f'- Mesh scratch path: data-mesh-src="{mesh_path}" data-mesh-canvas="studio-canvas"')
    if fallback:
        lines.append(
            "MESH API UNAVAILABLE — use the mode-specific procedural fallback without blocking the lesson."
        )
    lines.append("(Server rewrites mesh paths to /mesh?key= at persist; runtime auto-loads GLB.)")
    return "\n".join(lines) + "\n\n"


def _compute_block(plan: dict) -> str:
    """Hint capsule-author to embed precomputed plot paths (inlined as data: URLs at persist)."""
    paths = plan.get("compute_plot_paths") or []
    chart = plan.get("chart_spec")
    if not paths and not chart:
        return ""
    lines = [
        "PRECOMPUTED COMPUTE ASSETS — embed these as <img src=\"/build/compute/...\"> "
        "(the server will rewrite to data: URLs at persist). Do NOT regenerate plots in the browser."
    ]
    for p in paths[:6]:
        lines.append(f'- <img src="{p}" alt="precomputed plot">')
    if chart:
        lines.append(f"Optional Chart.js spec: {json.dumps(chart)[:1500]}")
    return "\n".join(lines) + "\n\n"


def _grounding_block(pack: list[dict]) -> str:
    """Prepend source excerpts + grounding rules when generating a document-grounded lesson
    (specs/document-grounded-courses). Empty for topic courses, so the contract is unchanged."""
    if not pack:
        return ""
    lines = []
    for p in pack:
        ps, pe = p.get("page_start"), p.get("page_end")
        pg = f"p.{ps}" if ps and (pe is None or ps == pe) else (f"p.{ps}-{pe}" if ps else "p.?")
        sec = p.get("section_title") or "—"
        lines.append(f"[S{p['id']} {pg} §{sec}]\n{(p.get('text') or '')[:800]}")
    excerpts = "\n\n".join(lines)
    return (
        "GROUND-TRUTH SOURCE EXCERPTS — base ALL factual claims ONLY on these. Cite each claim inline "
        "as [S<id> p.<page>] or in a visible citations panel. Teach ONE focused concept capsule. Do NOT "
        "copy long passages verbatim — paraphrase and cite. If the excerpts don't cover something, say "
        "so rather than inventing.\n\n"
        f"{excerpts}\n\n"
        "Now, using ONLY the above as ground truth:\n\n"
    )


def _source_figures_block(figures: list[dict], source_document_id: str | None = None) -> str:
    """Prefer parse-time source figures over `/gen` for document-grounded lessons."""
    if not figures:
        return ""
    sid = source_document_id or "SOURCE_ID"
    lines = []
    for f in figures[:8]:
        image_id = f.get("image_id") or f.get("figure_id") or ""
        if not image_id:
            continue
        page = f.get("page")
        pg = f" p.{page}" if page is not None else ""
        url = f"/sources/{sid}/figures/{image_id}"
        lines.append(f"- {image_id}{pg}: use <img go-data-src=\"{url}\" alt=\"source figure {image_id}\">")
    if not lines:
        return ""
    return (
        "SOURCE FIGURES (prefer these over /gen for diagrams that appear in the document). "
        "Only fall back to /gen?prompt=… when none of these fit the visual need.\n"
        + "\n".join(lines)
        + "\n\n"
    )

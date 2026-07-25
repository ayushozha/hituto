"""generate_ui HTML escape-hatch tool schema."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...capsule.postprocess import CHART_JS_CDN, THREE_JS_CDN

# --- Path B (bespoke HTML capsule) declarative UI: generate_ui ---
# Escape hatch for visuals outside the render_ui vocabulary (bespoke canvas/animation/3D).
# The model emits body content (fragment or full doc); the server wraps it in a zinc design
# shell, runs the capsule gate, and stores only a ui_id — raw HTML never reaches the client.


class GenerateUiTool(BaseModel):
    """Render a BESPOKE interactive HTML/SVG/JS visualization the render_ui vocabulary can't
    express — algorithm animation, physics/particle sim, shader, custom game, or 3D scene.
    Prefer render_ui for structured surfaces (prose, math, steps, quiz); use this only when
    the visual needs arbitrary canvas/animation/3D.

    Decision matrix (pick the right medium — graphics ≠ stock photos):
    - How X works physically / abstractly → SVG or HTML + inline SVG with controls
    - Process / flowchart / architecture → SVG diagram
    - Trends / categories / part-of-whole → Chart.js on <canvas> (CDN already allowlisted)
    - Physics / math simulation / algorithm steps → <canvas> + vanilla JS + at least one control
    - 3D scene → Three.js at the exact allowlisted URL only
    - Real-world photograph needed as reference → optional <img go-data-src="/image?query=...">
      NEVER use /gen image art as the teaching graphic — draw it.

    Build to pass the security gate on the FIRST try:
    - Prefer a BODY FRAGMENT (inner HTML only). A full document is OK; the server extracts
      the body and wraps it in the Hi Tuto zinc design shell (tokens, fonts, overflow clamps).
    - The ONLY external scripts allowed are Tailwind (https://cdn.tailwindcss.com), Chart.js at
      exactly the pinned URL below, and Three.js at exactly the pinned URL below. Hand-draw
      everything else with SVG, <canvas>, or vanilla JS. No D3, Mermaid, KaTeX, unpkg, esm.sh.
    - Must include at least one interactive control (button/input/select/range) wired to a
      visible SVG or <canvas> that updates. Do NOT require a decorative <img>.
    - Fit the viewport: max-width 100%, no fixed widths > 720px, no horizontal overflow.
    - Never touch window.parent/window.top, cookies, or localStorage/sessionStorage.
    - On-brand: dark ink on light paper, lime primary buttons — shell CSS already styles
      buttons; focus on the teaching visual."""

    title: str = Field(description="Short title shown on the card header")
    intent: str = Field(description="One line describing what the visual shows (spoken by voice)")
    html: str = Field(
        description=(
            "Body fragment (preferred) or a complete HTML5 document. Hand-draw the graphic with "
            "SVG/<canvas>/vanilla JS — do not use /gen images as the main visual. Optional "
            "Tailwind classes using brand tokens (paper, ink, lime, mint, sand, line). For "
            f"charts use Chart.js from exactly {CHART_JS_CDN}; for 3D use Three.js from exactly "
            f"{THREE_JS_CDN}. Include ≥1 interactive control wired to visible SVG/canvas output. "
            "Never access window.parent/window.top or localStorage/sessionStorage."
        )
    )


_GENERATE_UI_DESC = (
    "Render a bespoke interactive HTML/SVG/JS visualization (algorithm animation, physics sim, "
    "particle/shader, custom game, 3D scene) for visuals that do NOT fit the render_ui component "
    "vocabulary. Prefer SVG/canvas over images. Prefer render_ui for structured surfaces; use "
    "this only for arbitrary canvas/animation/3D. "
    f"If using Chart.js, the only allowed script URL is {CHART_JS_CDN}. "
    f"If using Three.js, the only allowed script URL is {THREE_JS_CDN}."
)

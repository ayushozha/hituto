"""Server-owned design shells for untrusted HTML (generate_ui + lesson sections).

Mirrors OpenGenerativeUI's assemble_document pattern: the host owns tokens, control
chrome, and overflow constraints; the model fills body content only. Zinc-neutral
palette matches ``frontend/tailwind.config.js`` (not the legacy warm-cream Thinkby look).
"""
from __future__ import annotations

import re

from .postprocess import CHART_JS_CDN, GLTF_LOADER_CDN, THREE_JS_CDN

# Exact brand tokens — keep in sync with frontend/tailwind.config.js.
SHELL_TAILWIND_CONFIG = """tailwind.config = { theme: { extend: {
  colors: {
    paper: "#FAFAFA", sand: "#F4F4F5", surface: "#FFFFFF",
    ink: { DEFAULT: "#18181B", soft: "#52525B", faint: "#A1A1AA" },
    line: "#E4E4E7",
    cobalt: { DEFAULT: "#27272A", dark: "#18181B", soft: "#F4F4F5" },
    lime: { DEFAULT: "#16A34A", dark: "#14532D", soft: "#EAF7EE" },
    coral: { DEFAULT: "#EF4444", dark: "#991B1B", soft: "#FEF2F2" },
    grass: { DEFAULT: "#16A34A", soft: "#EAF7EE" },
    mint: "#EAF7EE", lilac: "#F4F4F5", peach: "#FEF2F2",
    sky: "#2563EB", plum: "#18181B"
  },
  fontFamily: {
    display: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
    sans: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
    mono: ['"JetBrains Mono"', "ui-monospace", "monospace"]
  },
  borderRadius: { "4xl": "1.75rem" },
  boxShadow: {
    card: "0 1px 3px rgba(0,0,0,0.06)",
    press: "0 1px 2px rgba(0,0,0,0.08)",
    "press-cobalt": "0 1px 2px rgba(0,0,0,0.08)"
  }
} } };"""

_SHELL_BASE_CSS = """
  html, body { margin: 0; max-width: 100%; overflow-x: hidden; box-sizing: border-box; }
  *, *::before, *::after { box-sizing: border-box; }
  body {
    background: transparent;
    color: #18181B;
    font-family: "Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif;
  }
  img, canvas, svg, video, iframe { max-width: 100%; height: auto; }
  canvas { display: block; }
  input[type=range] { accent-color: #16A34A; width: 100%; max-width: 100%; }
  button, [role=button], .ht-btn {
    min-height: 44px; border-radius: 9999px; border: none; cursor: pointer;
    font-weight: 600; padding: 0.5rem 1rem;
    background: #16A34A; color: #fff;
  }
  button.secondary, .ht-btn-secondary {
    background: #F4F4F5; color: #18181B;
  }
  .ht-shell { width: 100%; max-width: 100%; overflow-x: hidden; }
"""

_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.I | re.S)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\s+html", re.I)
_FONTS = (
    "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;600&display=swap"
)


def extract_body_inner(html: str) -> str:
    """Pull body inner HTML from a full document, or return the fragment as-is."""
    text = (html or "").strip()
    if not text:
        return ""
    m = _BODY_RE.search(text)
    if m:
        return m.group(1).strip()
    # Strip a lone doctype/html/head wrapper noise if present without a clean body match.
    if _DOCTYPE_RE.search(text) or text[:20].lower().find("<html") >= 0:
        # Best-effort: drop head block
        low = text.lower()
        body_idx = low.find("<body")
        if body_idx >= 0:
            gt = text.find(">", body_idx)
            end = low.rfind("</body>")
            if gt > 0 and end > gt:
                return text[gt + 1 : end].strip()
    return text


def lesson_shell(plan: dict | None = None) -> tuple[str, str]:
    """(head, tail) for coursegen section fan-out documents."""
    plan = plan or {}
    three = ""
    if plan.get("needs_3d") or plan.get("mesh_artifact") or plan.get("mesh_catalog"):
        three = (
            f'<script src="{THREE_JS_CDN}"></script>\n'
            f'<script src="{GLTF_LOADER_CDN}"></script>\n'
        )
    head = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://cdn.tailwindcss.com"></script>
<script>{SHELL_TAILWIND_CONFIG}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_FONTS}" rel="stylesheet">
<script src="{CHART_JS_CDN}"></script>
{three}<style>
{_SHELL_BASE_CSS}
  main {{ display: flex; flex-direction: column; gap: 2rem; padding: 0.25rem 0 2rem; }}
</style>
</head>
<body>
<main class="ht-shell mx-auto max-w-7xl px-4 py-5 md:px-6 md:py-7">
"""
    return head, "</main>\n</body>\n</html>"


def widget_shell(*, needs_3d: bool = False) -> tuple[str, str]:
    """(head, tail) for tutor/voice generate_ui Path B capsules."""
    three = ""
    if needs_3d:
        three = f'<script src="{THREE_JS_CDN}"></script>\n'
    head = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://cdn.tailwindcss.com"></script>
<script>{SHELL_TAILWIND_CONFIG}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_FONTS}" rel="stylesheet">
<script src="{CHART_JS_CDN}"></script>
{three}<style>
{_SHELL_BASE_CSS}
  .ht-shell {{ padding: 12px; }}
</style>
</head>
<body>
<div class="ht-shell">
"""
    return head, "</div>\n</body>\n</html>"


def assemble_generate_ui(html: str, *, needs_3d: bool = False) -> str:
    """Wrap model output in the server-owned widget shell before the capsule gate.

    Accepts either a body fragment or a full HTML document (body is extracted).
    """
    inner = extract_body_inner(html)
    if not inner:
        inner = '<p class="text-ink-soft">Visual unavailable.</p>'
    # Heuristic: Three.js tags mean we need the CDN in the shell head.
    low = (html or "").lower()
    use_3d = needs_3d or "three.min.js" in low or "three.js" in low or "webgl" in low
    head, tail = widget_shell(needs_3d=use_3d)
    return head + inner + tail

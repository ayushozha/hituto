# capsule — untrusted-HTML security gate (protocol)

Generated lesson HTML (and tutor `generate_ui` HTML) is **untrusted**. This package is the gate
that decides whether HTML may ship, injects the runtime, and defines the CSP the iframe runs
under. A **protocol** package: it never imports agents.

> **Do not relax the sandbox, the CSP allowlist, or the postprocess rejection rules without a
> security review.** The postprocess `script-src` allowlist must stay in sync with `artifact_csp()`.

## Security gate (`postprocess.py`)

`postprocess(html) -> (clean_html, checks)` is the quality + security verdict:
- Strips disallowed external `<script src>` (exact-equality allowlist: Tailwind, pinned Three.js /
  GLTFLoader / Chart.js), markdown fences, stray prose.
- Rejects `window.parent`/`window.top`/`localStorage`/`sessionStorage`, placeholder tokens
  (`lorem ipsum`, `todo`, `{{`, `[image]`), and missing structure (`<body>`, canvas, controls,
  ≥1 image).
- Normalizes images to the lazy `go-data-src` loader (resolved at runtime via same-origin
  `/gen`,`/image`) and injects the **lesson bridge** + mesh runtime.
`checks["passed"]` gates a lesson to `ready`. `ensure_artifact_runtime()` re-pins CDN tags at
serve time.

## CSP (`csp.py`)

`artifact_csp()` — `default-src 'none'`; `img-src 'self' data: blob:`; `script-src 'self'
'unsafe-inline'` + the pinned CDNs; `connect-src 'self' blob:` (GLTFLoader); `frame-ancestors
'self' <frontend_origin>`. Artifacts are served as `HTMLResponse` with this header; the frontend
renders only in `sandbox="allow-scripts"` iframes via `src=` (never `srcdoc`).

## Lesson bridge (host ↔ capsule)

`postprocess` injects a versioned `postMessage` bridge into every capsule (host side:
`frontend/src/lib/lessonBridge.ts`). Because the sandboxed iframe has an opaque origin, message
identity is verified with `event.source === iframe.contentWindow`, **not** origin checks. It
exposes a snapshot (headings/sections/controls) and whitelisted actions (scroll, highlight, click,
set value, edit mode, get HTML) — this is how the tutor and voice agents observe and drive the
page. Bump the bridge version when changing the protocol.

## Ephemeral UI store (`generative_ui.py`)

`sanitize_and_store()` runs the same gate on tutor `generate_ui` HTML and returns an unguessable
`ui_id` (30-min TTL, owner+lesson tagged, in-memory). `get_ui_html()` serves it only to the owning
user+lesson, under the same CSP.

## Key files

`postprocess.py` (gate + bridge + mesh runtime) · `csp.py` (`artifact_csp`) ·
`generative_ui.py` (ephemeral store). Host side: `frontend/src/lib/lessonBridge.ts`,
`components/AgentCursorOverlay.tsx`.

## Tests

`test_lesson_bridge.py`, `test_edit_mode.py`, `test_generative_ui.py`, `test_compute_artifact.py`
(data: passthrough), `test_voice_page_control.py`.

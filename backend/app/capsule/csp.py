"""Content-Security-Policy for sandboxed lesson / tutor HTML capsules."""
from __future__ import annotations

from ..core.config import get_settings
from .postprocess import CHART_JS_CDN, GLTF_LOADER_CDN, THREE_JS_CDN


def _frontend_origins() -> str:
    """Return configured frontend origins in CSP source-list syntax.

    ``FRONTEND_ORIGIN`` is shared with CORS and may contain a comma-separated
    allowlist. CSP source lists are space-separated, so inserting the raw
    setting makes every entry after the first comma invalid.
    """
    raw = (get_settings().frontend_origin or "").strip()
    origins = [part.strip() for part in raw.split(",") if part.strip()]
    return " ".join(origins or ["http://localhost:5173"])


def artifact_csp() -> str:
    return (
        "default-src 'none'; "
        # blob: required — GLTFLoader decodes embedded GLB images via createObjectURL.
        "img-src 'self' data: blob:; "
        f"script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com {THREE_JS_CDN} {GLTF_LOADER_CDN} {CHART_JS_CDN}; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
        "font-src https://fonts.gstatic.com data:; "
        # Sandboxed capsules omit allow-same-origin (opaque origin), so 'self' alone does
        # not match fetches to the host. Allow configured frontend origins for /mesh and
        # /game-kits. data: covers embedded glTF buffers (Quaternius kits); blob: covers
        # createObjectURL decode of fetched GLB/glTF.
        f"connect-src 'self' blob: data: {_frontend_origins()}; "
        f"frame-ancestors 'self' {_frontend_origins()}"
    )

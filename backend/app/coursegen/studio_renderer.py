"""Render a validated Studio v2 manifest through server-owned assets."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .studio_manifest import StudioManifest

_SKILL_DIR = Path(__file__).resolve().parent / "skills" / "ui-studio-style"
_TEMPLATE_PATH = _SKILL_DIR / "assets" / "templates" / "studio-v2.html"
_TOKENS_PATH = _SKILL_DIR / "scripts" / "studio-tokens.css"
_RUNTIME_PATH = _SKILL_DIR / "scripts" / "studio-runtime.js"


@lru_cache
def _assets() -> tuple[str, str, str]:
    return (
        _TEMPLATE_PATH.read_text(encoding="utf-8"),
        _TOKENS_PATH.read_text(encoding="utf-8"),
        _RUNTIME_PATH.read_text(encoding="utf-8"),
    )


def render_studio_manifest(manifest: StudioManifest) -> str:
    """Return one self-contained capsule; postprocess remains the security gate."""
    template, tokens, runtime = _assets()
    payload = json.dumps(manifest.model_dump(mode="json"), separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    uses_three_stage = bool(manifest.stage.asset.src) or any(
        subject.procedural_kind for subject in manifest.subjects
    )
    html = (
        template.replace("__STUDIO_CSS__", tokens)
        .replace("__STUDIO_RUNTIME__", runtime)
        .replace("__STUDIO_MANIFEST__", payload)
        .replace("__STUDIO_MODE__", manifest.mode)
        .replace("__STUDIO_THEME__", manifest.theme)
        .replace(
            "__STUDIO_MESH_ATTRIBUTE__",
            (
                'data-mesh-src="" data-procedural-kind="" '
                'data-mesh-yaw="" data-mesh-pitch=""'
                if uses_three_stage
                else ""
            ),
        )
    )
    markers = (
        "__STUDIO_CSS__",
        "__STUDIO_RUNTIME__",
        "__STUDIO_MANIFEST__",
        "__STUDIO_MODE__",
        "__STUDIO_THEME__",
        "__STUDIO_MESH_ATTRIBUTE__",
    )
    if any(marker in html for marker in markers):
        raise ValueError("Studio template contains unresolved build markers")
    return html


def studio_artifact_metadata(html: str) -> dict[str, str]:
    """Read trusted routing metadata emitted by the owned Studio template."""
    if not re.search(
        r'<meta\s+name=["\']hituto-presentation["\']\s+content=["\']studio["\']',
        html,
        re.I,
    ):
        return {}
    mode_match = re.search(
        r'<meta\s+name=["\']hituto-studio-mode["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    metadata = {"presentation": "studio", "studio_manifest_version": "2.0"}
    if mode_match:
        metadata["studio_mode"] = mode_match.group(1)[:40]
    return metadata

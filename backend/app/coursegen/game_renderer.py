"""Render a validated GameManifest through server-owned assets."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..capsule.postprocess import GLTF_LOADER_CDN, THREE_JS_CDN
from .game_manifest import GameManifest

_SKILL_DIR = Path(__file__).resolve().parent / "skills" / "ui-game-style"
_TEMPLATE_PATH = _SKILL_DIR / "assets" / "templates" / "game-gallery.html"
_TOKENS_PATH = _SKILL_DIR / "scripts" / "game-tokens.css"
_RUNTIME_PATH = _SKILL_DIR / "scripts" / "game-runtime.js"


@lru_cache
def _assets() -> tuple[str, str, str]:
    return (
        _TEMPLATE_PATH.read_text(encoding="utf-8"),
        _TOKENS_PATH.read_text(encoding="utf-8"),
        _RUNTIME_PATH.read_text(encoding="utf-8"),
    )


def render_game_manifest(manifest: GameManifest) -> str:
    """Return one self-contained capsule; postprocess remains the security gate."""
    template, tokens, runtime = _assets()
    payload = json.dumps(manifest.model_dump(mode="json"), separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    html = (
        template.replace("__GAME_CSS__", tokens)
        .replace("__GAME_RUNTIME__", runtime)
        .replace("__GAME_MANIFEST__", payload)
        .replace("__GAME_MODE__", manifest.mode)
        .replace("__GAME_TITLE__", _escape_html(manifest.title))
        .replace("__GAME_GOAL__", _escape_html(manifest.goal))
        .replace("__THREE_JS_CDN__", THREE_JS_CDN)
        .replace("__GLTF_LOADER_CDN__", GLTF_LOADER_CDN)
    )
    markers = (
        "__GAME_CSS__",
        "__GAME_RUNTIME__",
        "__GAME_MANIFEST__",
        "__GAME_MODE__",
        "__GAME_TITLE__",
        "__GAME_GOAL__",
        "__THREE_JS_CDN__",
        "__GLTF_LOADER_CDN__",
    )
    if any(marker in html for marker in markers):
        raise ValueError("Game template contains unresolved build markers")
    return html


def game_artifact_metadata(html: str) -> dict[str, str]:
    """Read trusted routing metadata emitted by the owned game template."""
    if not re.search(
        r'<meta\s+name=["\']hituto-presentation["\']\s+content=["\']game["\']',
        html,
        re.I,
    ):
        return {}
    mode_match = re.search(
        r'<meta\s+name=["\']hituto-game-mode["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    metadata = {"presentation": "game", "game_manifest_version": "1.0"}
    if mode_match:
        metadata["game_mode"] = mode_match.group(1)[:40]
    return metadata


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

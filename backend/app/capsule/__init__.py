"""Untrusted HTML security gate: postprocess, CSP, ephemeral generative UI store."""

from .csp import artifact_csp
from .postprocess import (
    CHART_JS_CDN,
    GLTF_LOADER_CDN,
    THREE_JS_CDN,
    ensure_artifact_runtime,
    postprocess,
    validate_artifact_runtime,
)
from .shell import assemble_generate_ui, lesson_shell, widget_shell

__all__ = [
    "CHART_JS_CDN",
    "GLTF_LOADER_CDN",
    "THREE_JS_CDN",
    "assemble_generate_ui",
    "artifact_csp",
    "ensure_artifact_runtime",
    "lesson_shell",
    "postprocess",
    "validate_artifact_runtime",
    "widget_shell",
]

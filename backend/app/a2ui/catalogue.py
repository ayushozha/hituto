"""A2UI component catalogue — normative type set for backend/frontend sync."""
from __future__ import annotations

from typing import get_args

from .schema import UiNodeType, _PROP_MODELS, _RENDER_UI_DESC, RenderUiTool

COMPONENT_TYPES: tuple[str, ...] = get_args(UiNodeType)

RENDER_UI_TOOL_SPEC = {
    "name": "render_ui",
    "description": _RENDER_UI_DESC,
    "schema": RenderUiTool,
}

__all__ = [
    "COMPONENT_TYPES",
    "RENDER_UI_TOOL_SPEC",
    "UiNodeType",
    "_PROP_MODELS",
]

"""Declarative A2UI protocol — trusted JSON component trees for render_ui."""
from .catalogue import COMPONENT_TYPES, RENDER_UI_TOOL_SPEC
from .normalize import normalize_render_ui
from .schema import (
    INSERTABLE_TYPES,
    MAX_UI_DEPTH,
    MAX_UI_NODES,
    QuizStep,
    RenderUiTool,
    UiNode,
    UiNodeType,
    normalize_ui_node,
)

__all__ = [
    "COMPONENT_TYPES",
    "INSERTABLE_TYPES",
    "MAX_UI_DEPTH",
    "MAX_UI_NODES",
    "QuizStep",
    "RENDER_UI_TOOL_SPEC",
    "RenderUiTool",
    "UiNode",
    "UiNodeType",
    "normalize_render_ui",
    "normalize_ui_node",
]

"""Tutor tool registry — single source of truth for model-facing tools."""
from __future__ import annotations

from typing import List, Tuple, Type

from pydantic import BaseModel

from ...a2ui import RenderUiTool
from ...a2ui.schema import _RENDER_UI_DESC
from .generate_ui import GenerateUiTool, _GENERATE_UI_DESC
from .widgets import (
    CreateGameTool,
    CreateQuizTool,
    ShowCodeExerciseTool,
    ShowCodingLabTool,
    ShowDiagramTool,
    ShowFlashcardsTool,
    ShowFormulaCalculatorTool,
    ShowWhiteboardTool,
    UpdateCodingLabTool,
)

# (name exposed to the model, description, Pydantic schema). Frontend switches on the same
# names in LessonTutorChat.tsx — keep all three in sync when adding a tool.
TOOL_DEFS: List[Tuple[str, str, Type[BaseModel]]] = [
    ("create_quiz", "Call this tool to generate an interactive quiz for the student.", CreateQuizTool),
    ("show_flashcards", "Call this tool to show a deck of flip cards for memorization or review.", ShowFlashcardsTool),
    (
        "show_coding_lab",
        "Open a live coding lab (multi-file tree + editor + run/preview). Prefer this over "
        "show_code_exercise when teaching coding. Seed one or many starter files — for a "
        "mini website use language=html with index.html, styles.css, and script.js "
        "(Preview wires CSS/JS in). Set expectedStdout when an exact output check helps.",
        ShowCodingLabTool,
    ),
    (
        "update_coding_lab",
        "Rewrite or extend the open coding lab (replace files, add CSS/JS, change "
        "instructions/checks) without dumping long code in chat. Use after the learner "
        "runs code or asks for the next step.",
        UpdateCodingLabTool,
    ),
    (
        "show_code_exercise",
        "Simple single-file code textarea (no run). Prefer show_coding_lab for real practice.",
        ShowCodeExerciseTool,
    ),
    ("create_game", "Call this tool to spawn an interactive matching or trivia game.", CreateGameTool),
    ("show_diagram", "Call this tool ONLY for a clickable mind map / concept map (not freeform drawings).", ShowDiagramTool),
    ("show_formula_calculator", "Call this tool to show a step-by-step formula solver where the user can input values and see calculations.", ShowFormulaCalculatorTool),
    (
        "show_whiteboard",
        "Call this tool to open an Excalidraw teaching whiteboard. Use for draw/sketch/diagram/"
        "process cycles (e.g. water cycle), architecture, and editable labeled sketches. "
        "Prefer this over show_diagram for almost all drawing requests.",
        ShowWhiteboardTool,
    ),
    ("render_ui", _RENDER_UI_DESC, RenderUiTool),
    ("generate_ui", _GENERATE_UI_DESC, GenerateUiTool),
]

# Backward-compat alias used by voice + tests during migration.
_TOOL_DEFS = TOOL_DEFS

__all__ = ["TOOL_DEFS", "_TOOL_DEFS", "GenerateUiTool"]

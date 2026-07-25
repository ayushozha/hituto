"""Tutor widget tool schemas (quiz, flashcards, code, game, diagram, formula, whiteboard)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ...a2ui import QuizStep

_MAX_WHITEBOARD_ELEMENTS = 80

class CreateQuizTool(BaseModel):
    """Call this tool to generate an interactive quiz for the student."""
    topic: str
    questions: List[QuizStep]

class Flashcard(BaseModel):
    front: str = Field(description="Question, concept, or term on the front of the card")
    back: str = Field(description="Answer, definition, or explanation on the back of the card")

class ShowFlashcardsTool(BaseModel):
    """Call this tool to show a deck of flip cards for memorization or review."""
    topic: str
    cards: List[Flashcard]

class ShowCodeExerciseTool(BaseModel):
    """Call this tool to show an interactive code practice exercise."""
    title: str
    language: str = Field(description="e.g. python, javascript")
    initialCode: str = Field(description="Starter code snippet for the student to complete")
    instructions: str = Field(description="Clear explanation of the goal and instructions")
    expectedOutput: Optional[str] = Field(default=None, description="Expected console output to match")
    hint: Optional[str] = Field(default=None, description="Optional helper hint")


class CodingLabFile(BaseModel):
    path: str = Field(description="File path, e.g. main.py, index.html, styles.css, script.js")
    content: str = Field(description="Full file contents")


class ShowCodingLabTool(BaseModel):
    """Open a Mimo-like coding lab: file tree, editor, run/preview for fundamentals practice."""

    title: str = Field(description="Short title for the coding lab card")
    language: str = Field(
        description=(
            "Primary language. Runnable in-lab: javascript, python, html. "
            "Use language=html for multi-file websites (index.html + styles.css + script.js); "
            "Preview injects all .css/.js into the HTML. "
            "Any other (typescript, java, go, cpp, rust, …) still opens the lab; learner "
            "submits for tutor review. Python/JS: no interactive input()/stdin — use fixed "
            "values and print/console.log. Python packages: prefer stdlib + Pyodide-supported "
            "libs (numpy, pandas, matplotlib, scipy); arbitrary pip packages may fail."
        )
    )
    instructions: str = Field(description="Clear exercise goal the learner should complete")
    files: List[CodingLabFile] = Field(
        description=(
            "Starter project files (path + content). Multi-file is supported and preferred for "
            "web work — e.g. index.html, styles.css, script.js. For a single-language drill, "
            "one file is fine. Avoid Python input() — assign sample values instead. "
            "You may fully rewrite the workspace later via update_coding_lab."
        )
    )
    entrypoint: Optional[str] = Field(
        default=None,
        description="File to run/preview first, e.g. main.py or index.html",
    )
    expectedStdout: Optional[str] = Field(
        default=None,
        description="Expected console output for auto-check (trim-compared)",
    )
    hint: Optional[str] = Field(default=None, description="Optional helper hint")


class UpdateCodingLabTool(BaseModel):
    """Update the open coding lab mid-lesson (new files, instructions, or checks)."""

    coding_lab_session_id: Optional[str] = Field(
        default=None,
        description="Existing lab session id; omit to update the latest lab for this lesson",
    )
    title: Optional[str] = None
    language: Optional[str] = None
    instructions: Optional[str] = None
    files: Optional[List[CodingLabFile]] = Field(
        default=None,
        description=(
            "When set, replaces the whole workspace file set (full rewrite OK). "
            "Pass every file the learner should see, including new ones like styles.css."
        ),
    )
    entrypoint: Optional[str] = None
    expectedStdout: Optional[str] = None
    hint: Optional[str] = None
class CreateGameTool(BaseModel):
    """Call this tool to spawn an interactive matching or trivia game."""
    gameType: Literal["matching", "trivia"]
    topic: str
    content: Dict[str, Any] = Field(description="If matching: {leftItems: str[], rightItems: str[], pairs: [str, str][]}. If trivia: list of question objects.")

class DiagramNode(BaseModel):
    id: str
    label: str
    description: str

class ShowDiagramTool(BaseModel):
    """Call this tool to show a structured mindmap or flowchart (concept map) for visual explanations."""
    title: str
    mermaidDefinition: str = Field(description="Mermaid diagram string, e.g. 'graph TD; A-->B;'")
    nodes: List[DiagramNode] = Field(description="Explanation of key components in the graph")

class FormulaVariable(BaseModel):
    name: str
    label: str
    unit: str
    defaultValue: float

class ShowFormulaCalculatorTool(BaseModel):
    """Call this tool to show a step-by-step formula solver where the user can input values and see calculations."""
    title: str
    formula: str = Field(description="The symbolic math equation, e.g., 'E = m * c^2'")
    variables: List[FormulaVariable]
    steps: List[str] = Field(description="Step-by-step derivations or explanations")


class ShowWhiteboardTool(BaseModel):
    """Call this tool to open an Excalidraw teaching whiteboard with a sketched diagram."""

    title: str = Field(description="Short title for the whiteboard card")
    intent: str = Field(
        default="",
        description="One-line teaching goal shown to the student (e.g. 'Trace the water cycle')",
    )
    elements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Excalidraw elements to seed the canvas. Prefer rectangles, ellipses, diamonds, "
            "arrows, lines, and text. Each element needs type, id, x, y, width, height; "
            "text elements also need text/fontSize; arrows need points. Keep under 80 elements."
        ),
    )
    caption: Optional[str] = Field(
        default=None,
        description="Optional short caption under the whiteboard",
    )

    @field_validator("elements")
    @classmethod
    def _cap_elements(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(value) > _MAX_WHITEBOARD_ELEMENTS:
            return value[:_MAX_WHITEBOARD_ELEMENTS]
        return value

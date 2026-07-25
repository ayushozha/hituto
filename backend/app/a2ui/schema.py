"""A2UI declarative UI schema: UiNode tree, RenderUiTool, prop models."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)

class QuizStep(BaseModel):
    """Shared quiz-step shape for create_quiz widget and A2UI quiz nodes."""
    type: Literal["mcq", "numeric", "slider"]
    title: str = Field(description="Step title, e.g. Question 1")
    prompt: str = Field(description="The question or task prompt")
    explanation: str = Field(description="Background context or visual description/explanation of the correct answer")
    options: List[str] = Field(default=[], description="List of options for MCQ step")
    correctAnswer: str = Field(description="The correct value (index for MCQ, number for numeric/slider)")
    hints: List[str] = Field(default=[], description="1-2 hints for the student")

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        key = v.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "mcq": "mcq",
            "multiple_choice": "mcq",
            "multiplechoice": "mcq",
            "choice": "mcq",
            "numeric": "numeric",
            "number": "numeric",
            "slider": "slider",
            "range": "slider",
        }
        return aliases.get(key, v)

    @field_validator("correctAnswer", mode="before")
    @classmethod
    def _stringify_answer(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, (int, float, bool)):
            return str(v)
        return v


MAX_UI_DEPTH = 6
MAX_UI_NODES = 60

# A2UI vocabulary: layout + prose + math + steps + quiz (v1) plus table + chart + slider + diagram
# (v2, all hand-drawn SVG / vanilla React — no chart/graph lib, so nothing new for the CSP). Anything
# outside this set is the signal to route to generate_ui.
UiNodeType = Literal[
    "stack", "heading", "text", "callout", "math", "steps", "quiz",
    "table", "chart", "slider", "diagram", "map", "embed",
]


class _PropsBase(BaseModel):
    # Accept alias keys (model variance) and the canonical name; ignore stray extras rather than
    # crash. Missing a REQUIRED prop still rejects (that is the "bad props" rejection path).
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class StackProps(_PropsBase):
    """Layout container. Children carry the content."""
    direction: Literal["vertical", "horizontal"] = "vertical"
    gap: Literal["sm", "md", "lg"] = "md"


class HeadingProps(_PropsBase):
    text: str = Field(validation_alias=AliasChoices("text", "content", "title"))
    level: int = 2

    @field_validator("level", mode="before")
    @classmethod
    def _clamp_level(cls, v: Any) -> int:
        try:
            return min(3, max(1, int(v)))
        except (TypeError, ValueError):
            return 2


class TextProps(_PropsBase):
    text: str = Field(validation_alias=AliasChoices("text", "content", "body"))


class CalloutProps(_PropsBase):
    text: str = Field(validation_alias=AliasChoices("text", "content", "body"))
    variant: Literal["info", "warning", "success", "danger"] = "info"


class MathProps(_PropsBase):
    latex: str = Field(validation_alias=AliasChoices("latex", "tex", "expression", "content"))
    display: bool = True


class StepItem(_PropsBase):
    title: str = Field(validation_alias=AliasChoices("title", "heading", "label"))
    detail: str = Field(default="", validation_alias=AliasChoices("detail", "text", "content", "body"))


class StepsProps(_PropsBase):
    steps: List[StepItem] = Field(validation_alias=AliasChoices("steps", "items"))


class QuizProps(_PropsBase):
    """Reuses the create_quiz shape so the frontend can render QuizComponent directly."""
    topic: str = Field(default="", validation_alias=AliasChoices("topic", "title"))
    questions: List[QuizStep] = Field(validation_alias=AliasChoices("questions", "steps", "items"))


class TableProps(_PropsBase):
    """Comparison/reference table. Cells are coerced to strings so the renderer never receives a
    non-primitive (models emit numbers/None freely)."""
    headers: List[str] = Field(default_factory=list, validation_alias=AliasChoices("headers", "columns", "cols"))
    rows: List[List[str]] = Field(validation_alias=AliasChoices("rows", "data"))
    caption: str = Field(default="", validation_alias=AliasChoices("caption", "title"))

    @field_validator("rows", mode="before")
    @classmethod
    def _coerce_rows(cls, v: Any) -> List[List[str]]:
        if not isinstance(v, list):
            return []
        out: List[List[str]] = []
        for row in v:
            if isinstance(row, dict):
                row = list(row.values())
            if isinstance(row, list):
                out.append(["" if c is None else str(c) for c in row])
        return out


class ChartSeries(_PropsBase):
    label: str = Field(default="", validation_alias=AliasChoices("label", "name", "title"))
    values: List[float] = Field(validation_alias=AliasChoices("values", "data", "points"))


class ChartProps(_PropsBase):
    """Bar or line chart drawn from numeric series (hand-drawn SVG on the frontend — no chart lib,
    so no new dep and nothing for the CSP to allow). `labels` are the x-axis categories; each
    `series` is one bar group / line."""
    kind: Literal["bar", "line"] = Field(default="bar", validation_alias=AliasChoices("kind", "type", "variant"))
    labels: List[str] = Field(default_factory=list, validation_alias=AliasChoices("labels", "categories", "x"))
    series: List[ChartSeries] = Field(validation_alias=AliasChoices("series", "datasets"))
    caption: str = Field(default="", validation_alias=AliasChoices("caption", "title"))


class SliderReadout(_PropsBase):
    """A live-computed value shown next to the slider. `expr` is arithmetic in the variable `x`
    (the slider value), evaluated by a SAFE, no-`eval` parser on the frontend — a bad/blocked
    expr just renders a dash, it never runs code."""
    label: str = Field(default="", validation_alias=AliasChoices("label", "title", "name"))
    expr: str = Field(validation_alias=AliasChoices("expr", "formula", "expression"))
    unit: str = Field(default="", validation_alias=AliasChoices("unit", "units", "suffix"))
    precision: int = 2

    @field_validator("precision", mode="before")
    @classmethod
    def _clamp_precision(cls, v: Any) -> int:
        try:
            return min(6, max(0, int(v)))
        except (TypeError, ValueError):
            return 2


class SliderProps(_PropsBase):
    """A labelled range input the learner drags; optional `readouts` recompute live from its value
    (no reactive cross-tree data-model in v1 — the slider owns its own state and its readouts)."""
    label: str = Field(validation_alias=AliasChoices("label", "title", "name"))
    min: float = 0.0
    max: float = 100.0
    step: float = 1.0
    value: float = Field(default=0.0, validation_alias=AliasChoices("value", "default", "initial"))
    unit: str = Field(default="", validation_alias=AliasChoices("unit", "units", "suffix"))
    readouts: List[SliderReadout] = Field(
        default_factory=list, validation_alias=AliasChoices("readouts", "outputs", "results")
    )

    @model_validator(mode="after")
    def _sane_range(self) -> "SliderProps":
        if self.max <= self.min:
            self.max = self.min + 1.0
        if self.step <= 0:
            self.step = 1.0
        self.value = min(self.max, max(self.min, self.value))
        return self


class UiDiagramNode(_PropsBase):
    # Distinct from the top-level `DiagramNode` used by the show_diagram (Mermaid) tool.
    id: str = Field(validation_alias=AliasChoices("id", "key", "name"))
    label: str = Field(default="", validation_alias=AliasChoices("label", "text", "title"))

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @model_validator(mode="after")
    def _default_label(self) -> "UiDiagramNode":
        if not self.label:
            self.label = self.id
        return self


class UiDiagramEdge(_PropsBase):
    # `from` is a Python keyword, so the canonical field is `source` with `from` as an alias.
    source: str = Field(validation_alias=AliasChoices("source", "from", "src", "start"))
    target: str = Field(validation_alias=AliasChoices("target", "to", "dst", "end"))
    label: str = Field(default="", validation_alias=AliasChoices("label", "text", "title"))

    @field_validator("source", "target", mode="before")
    @classmethod
    def _endpoint_str(cls, v: Any) -> str:
        return "" if v is None else str(v)


class DiagramProps(_PropsBase):
    """A small node/edge graph auto-laid-out (layered longest-path) and drawn as SVG on the
    frontend. For standalone flowcharts/mindmaps the dedicated show_diagram (Mermaid) tool is
    richer; this is the inline A2UI version."""
    nodes: List[UiDiagramNode] = Field(validation_alias=AliasChoices("nodes", "vertices"))
    edges: List[UiDiagramEdge] = Field(
        default_factory=list, validation_alias=AliasChoices("edges", "links", "connections")
    )
    direction: Literal["TB", "LR"] = Field(
        default="TB", validation_alias=AliasChoices("direction", "dir", "orientation")
    )
    caption: str = Field(default="", validation_alias=AliasChoices("caption", "title"))

    @field_validator("direction", mode="before")
    @classmethod
    def _norm_direction(cls, v: Any) -> str:
        s = str(v or "TB").upper()
        if s in ("TB", "TOP-BOTTOM", "TOPDOWN", "TOP", "VERTICAL", "V", "DOWN"):
            return "TB"
        if s in ("LR", "LEFT-RIGHT", "LEFTRIGHT", "LEFT", "HORIZONTAL", "H", "RIGHT"):
            return "LR"
        return "TB"


class MapListing(_PropsBase):
    """One pin on an A2UI map (real-estate / geo teaching demos)."""

    id: str = Field(default="", validation_alias=AliasChoices("id", "key"))
    lat: float = Field(validation_alias=AliasChoices("lat", "latitude"))
    lng: float = Field(validation_alias=AliasChoices("lng", "lon", "longitude"))
    label: str = Field(default="", validation_alias=AliasChoices("label", "title", "name"))
    beds: float | None = None
    baths: float | None = None
    sqft: float | None = None
    list_price: float | None = Field(
        default=None, validation_alias=AliasChoices("list_price", "price", "listPrice")
    )

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @model_validator(mode="after")
    def _default_id_label(self) -> "MapListing":
        if not self.id:
            self.id = f"{self.lat:.4f},{self.lng:.4f}"
        if not self.label:
            self.label = self.id
        return self


class MapPrediction(_PropsBase):
    mode: Literal["linear_demo", "none"] = "linear_demo"
    features: List[str] = Field(
        default_factory=lambda: ["sqft", "beds", "baths"],
        validation_alias=AliasChoices("features", "inputs"),
    )
    student_inputs: List[str] = Field(
        default_factory=lambda: ["sqft", "beds"],
        validation_alias=AliasChoices("student_inputs", "controls"),
    )


class MapCenter(_PropsBase):
    lat: float = 37.8
    lng: float = Field(default=-122.3, validation_alias=AliasChoices("lng", "lon", "longitude"))


class MapProps(_PropsBase):
    """Trusted interactive map panel — model supplies listings/config only; React draws the UI."""

    title: str = Field(default="Map lab", validation_alias=AliasChoices("title", "heading", "name"))
    center: MapCenter = Field(default_factory=MapCenter)
    zoom: int = 11
    listings: List[MapListing] = Field(
        default_factory=list, validation_alias=AliasChoices("listings", "pins", "markers", "points")
    )
    prediction: MapPrediction = Field(default_factory=MapPrediction)
    task_copy: Dict[str, str] = Field(
        default_factory=dict, validation_alias=AliasChoices("task_copy", "copy", "labels")
    )
    caption: str = Field(default="", validation_alias=AliasChoices("caption", "subtitle"))

    @field_validator("zoom", mode="before")
    @classmethod
    def _clamp_zoom(cls, v: Any) -> int:
        try:
            return min(18, max(1, int(v)))
        except (TypeError, ValueError):
            return 11

    @field_validator("center", mode="before")
    @classmethod
    def _coerce_center(cls, v: Any) -> Any:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return {"lat": v[0], "lng": v[1]}
        return v


class EmbedProps(_PropsBase):
    """Sandboxed HTML leaf for sims outside the catalogue. `html` is server-gated only."""

    title: str = Field(validation_alias=AliasChoices("title", "heading", "name"))
    slot_id: str = Field(
        default="embed",
        validation_alias=AliasChoices("slot_id", "slotId", "id", "slot"),
    )
    html: str = Field(default="", max_length=200_000)
    caption: str = Field(default="", validation_alias=AliasChoices("caption", "subtitle"))

    @field_validator("slot_id", mode="before")
    @classmethod
    def _slug_slot(cls, v: Any) -> str:
        raw = re.sub(r"[^a-z0-9-]", "-", str(v or "embed").lower()).strip("-")
        return raw or "embed"


_PROP_MODELS: Dict[str, Type[BaseModel]] = {
    "stack": StackProps,
    "heading": HeadingProps,
    "text": TextProps,
    "callout": CalloutProps,
    "math": MathProps,
    "steps": StepsProps,
    "quiz": QuizProps,
    "table": TableProps,
    "chart": ChartProps,
    "slider": SliderProps,
    "diagram": DiagramProps,
    "map": MapProps,
    "embed": EmbedProps,
}


class UiNode(BaseModel):
    """One node in an A2UI component tree. `type` selects a trusted React renderer; `props` are
    validated + normalized per type; `children` nest (containers only)."""
    model_config = ConfigDict(extra="ignore")

    type: UiNodeType
    props: Dict[str, Any] = Field(default_factory=dict)
    children: List["UiNode"] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _hoist_flat_props(cls, data: Any) -> Any:
        """Accept LLM variants that put prop keys on the node instead of under `props`."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        props = dict(out.get("props") or {})
        # Common flat keys models emit next to `type` (OpenGenerativeUI / loose JSON style).
        for key in (
            "text", "content", "title", "body", "latex", "tex", "expression",
            "level", "variant", "display", "steps", "items", "questions",
            "topic", "headers", "rows", "caption", "kind", "labels", "series",
            "label", "min", "max", "step", "value", "unit", "readouts",
            "nodes", "edges", "direction", "gap",
            "center", "zoom", "listings", "pins", "prediction", "copy", "task_copy",
            "slot_id", "slotId", "html",
        ):
            if key in out and key not in props:
                props[key] = out.pop(key)
        out["props"] = props
        return out

    @model_validator(mode="after")
    def _validate_props(self) -> "UiNode":
        model = _PROP_MODELS.get(self.type)
        if model is not None:
            # Raises ValidationError on bad props -> bubbles up -> whole tree rejected.
            self.props = model.model_validate(self.props or {}).model_dump()
        return self


UiNode.model_rebuild()


class RenderUiTool(BaseModel):
    """Render an interactive surface from trusted, theme-locked components (A2UI). Prefer this
    over a long text answer when a visual teaches better AND the surface fits these node types:

      - stack   {direction?: "vertical"|"horizontal", gap?: "sm"|"md"|"lg"} + children (layout)
      - heading {text: str, level?: 1-3}
      - text    {text: str}                     (a short paragraph)
      - callout {text: str, variant?: "info"|"warning"|"success"|"danger"}
      - math    {latex: str, display?: bool}    (KaTeX)
      - steps   {steps: [{title: str, detail?: str}]}
      - quiz    {topic?: str, questions: [...]}  (same shape as create_quiz)
      - table   {headers: [str], rows: [[str]], caption?: str}
      - chart   {kind?: "bar"|"line", labels: [str], series: [{label?: str, values: [num]}]}
      - slider  {label: str, min?, max?, step?, value?, unit?, readouts?: [{label?, expr, unit?}]}
                (expr is arithmetic in `x` = the slider value, e.g. "3.14159*x*x")
      - diagram {nodes: [{id, label?}], edges: [{from, to, label?}], direction?: "TB"|"LR"}
      - map     {title?, center?: {lat,lng}, listings?: [...], prediction?: {...}}
      - embed   {title, slot_id?, caption?}  (server fills gated html for sims)

    Compose them under a single `root` node (usually a `stack`). Emit the exact prop keys above.
    Use raw HTML (the generate_ui tool) ONLY for bespoke canvas/animation/3D outside this set;
    use plain text for a quick fact with no visual."""
    title: str = Field(description="Short title shown on the card header")
    intent: str = Field(description="One line describing the surface (spoken by the voice agent)")
    root: UiNode

    @model_validator(mode="after")
    def _enforce_bounds(self) -> "RenderUiTool":
        total = 0

        def walk(node: UiNode, depth: int) -> None:
            nonlocal total
            total += 1
            if depth > MAX_UI_DEPTH:
                raise ValueError(f"UI tree exceeds max depth {MAX_UI_DEPTH}")
            if total > MAX_UI_NODES:
                raise ValueError(f"UI tree exceeds max nodes {MAX_UI_NODES}")
            for child in node.children:
                walk(child, depth + 1)

        walk(self.root, 1)
        return self


_RENDER_UI_DESC = (
    "Render an interactive surface from trusted, theme-locked components (fast, always on-brand). "
    "Prefer this over a long text answer when a visual teaches better and fits the node types "
    "stack/heading/text/callout/math/steps/quiz/table/chart/slider/diagram/map/embed. Compose them "
    "under a single `root` node."
)


def normalize_render_ui(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate + normalize a render_ui tool-call payload.

    Returns the canonical arguments dict (props normalized to canonical keys, tree bounded) or
    None if the tree is invalid — the caller then falls back (generate_ui/text), per the
    fail-closed rule in the spec.
    """
    try:
        return RenderUiTool.model_validate(arguments).model_dump()
    except Exception as exc:  # pydantic ValidationError or ValueError from bounds
        logger.warning("render_ui tree rejected: %s", exc)
        return None


def normalize_ui_node(node: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    """Validate a single UiNode (for catalogue insert). None if invalid."""
    if not isinstance(node, dict):
        return None
    try:
        return UiNode.model_validate(node).model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ui node rejected: %s", exc)
        return None


# Allowlisted catalogue types for slash-insert (excludes pure layout containers).
INSERTABLE_TYPES = frozenset(
    {
        "heading",
        "text",
        "callout",
        "math",
        "steps",
        "quiz",
        "table",
        "chart",
        "slider",
        "diagram",
        "map",
        "embed",
    }
)

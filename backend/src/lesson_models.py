import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Space = Literal["board", "source", "diagram"]
LayoutMode = Literal["absolute", "flow", "auto"]


def _validate_stable_id(value: str) -> str:
    if value and not all(character.isalnum() or character in "-_ :" for character in value):
        raise ValueError("scene IDs may contain only letters, digits, '-', '_', and ':'")
    if " " in value:
        raise ValueError("scene IDs may not contain spaces")
    return value


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)

    @field_validator("id")
    @classmethod
    def stable_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)


class InkCommand(CommandBase):
    space: Space = "board"
    layout: LayoutMode = "absolute"
    text: str = Field(min_length=1, max_length=240)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    width: float = Field(default=0.0, ge=0.0, le=1.0)
    height: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_flow_layout(self) -> "InkCommand":
        if self.layout == "flow" and self.space != "board":
            raise ValueError("flow layout is only available in board space")
        return self


class TextCommand(InkCommand):
    kind: Literal["text"]


class MathCommand(InkCommand):
    kind: Literal["math"]

    @field_validator("text")
    @classmethod
    def math_is_not_plain_prose(cls, value: str) -> str:
        # Named quantities are ordinary notation — "Area = ½ · base · height"
        # is maths, not prose. Only reject when there is nothing mathematical
        # left to justify the KaTeX pass.
        plain_words = re.findall(r"[A-Za-z]{3,}", value.replace(r"\text", ""))
        has_maths = re.search(r"[0-9=+\-*/^_\\<>×·÷±≤≥≠]", value) is not None
        if len(plain_words) >= 3 and not has_maths and r"\text{" not in value:
            raise ValueError("plain prose belongs in a text command, not a math command")
        return value


class SegmentCommand(CommandBase):
    kind: Literal["line", "arrow", "bracket"]
    space: Space = "diagram"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class RectCommand(CommandBase):
    kind: Literal["rect"]
    space: Space = "diagram"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    preserve_aspect: bool = False


class HighlightCommand(CommandBase):
    kind: Literal["highlight"]
    space: Literal["board", "source"] = "board"
    target_id: str = Field(default="", max_length=80)
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    width: float = Field(default=0.0, ge=0.0, le=1.0)
    height: float = Field(default=0.0, ge=0.0, le=1.0)
    color: str = Field(default="#f4b400", max_length=24)
    opacity: float = Field(default=0.25, ge=0.0, le=1.0)

    @field_validator("target_id")
    @classmethod
    def stable_target_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)


class CircleCommand(CommandBase):
    kind: Literal["circle"]
    space: Space = "diagram"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    radius: float = Field(gt=0.0, le=0.5)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class AngleCommand(CommandBase):
    kind: Literal["angle"]
    space: Space = "diagram"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    radius: float = Field(gt=0.0, le=0.5)
    start_angle: float = Field(ge=-360.0, le=360.0)
    end_angle: float = Field(ge=-360.0, le=360.0)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class PolylineCommand(CommandBase):
    kind: Literal["polyline"]
    space: Space = "diagram"
    points: list[Point] = Field(min_length=2, max_length=40)
    color: str = Field(default="#1769e0", max_length=24)
    size: float = Field(default=0.04, ge=0.001, le=0.2)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    formula: str = Field(min_length=1, max_length=240)
    color: str = Field(default="#1769e0", max_length=24)
    label: str = Field(default="", max_length=80)

    @field_validator("id")
    @classmethod
    def stable_graph_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)

    @field_validator("formula")
    @classmethod
    def safe_function_formula(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9A-Za-z_+\-*/^().,\s]+", value):
            raise ValueError("graph formulas contain unsupported characters")
        allowed_names = {"x", "abs", "sqrt", "sin", "cos", "tan", "log", "log10", "exp", "pi", "e"}
        names = re.findall(r"[A-Za-z_]+", value)
        if any(name not in allowed_names for name in names):
            raise ValueError("graph formulas contain an unsupported name")
        return value


class GraphMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    label: str = Field(default="", max_length=80)
    color: str = Field(default="#d93025", max_length=24)

    @field_validator("id")
    @classmethod
    def stable_marker_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)


class GraphCommand(CommandBase):
    kind: Literal["graph"]
    space: Literal["board"] = "board"
    layout: Literal["auto"] = "auto"
    curves: list[GraphCurve] = Field(default_factory=list, max_length=6)
    markers: list[GraphMarker] = Field(default_factory=list, max_length=12)
    x_min: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    x_max: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    y_min: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    y_max: float = Field(ge=-1_000_000.0, le=1_000_000.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_graph(self) -> "GraphCommand":
        if not self.curves and not self.markers:
            raise ValueError("graph commands require a curve or marker")
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("graph bounds must increase from min to max")
        if any(not self.x_min <= marker.x <= self.x_max or not self.y_min <= marker.y <= self.y_max for marker in self.markers):
            raise ValueError("graph markers must be inside the graph bounds")
        return self


class BarDatum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=48)
    value: float = Field(ge=0.0, le=1_000_000.0)
    display_value: str = Field(default="", max_length=48)
    color: str = Field(default="#1769e0", max_length=24)


class BarChartCommand(CommandBase):
    kind: Literal["bar_chart"]
    space: Literal["board"] = "board"
    layout: Literal["auto"] = "auto"
    title: str = Field(default="", max_length=100)
    x_label: str = Field(default="", max_length=80)
    y_label: str = Field(default="", max_length=80)
    bars: list[BarDatum] = Field(min_length=2, max_length=12)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class VennCommand(CommandBase):
    kind: Literal["venn"]
    space: Literal["board"] = "board"
    layout: Literal["auto"] = "auto"
    title: str = Field(default="", max_length=100)
    left_label: str = Field(min_length=1, max_length=64)
    right_label: str = Field(min_length=1, max_length=64)
    left_only: str = Field(min_length=1, max_length=64)
    overlap: str = Field(min_length=1, max_length=64)
    right_only: str = Field(min_length=1, max_length=64)
    outside: str = Field(default="", max_length=64)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class EraseCommand(CommandBase):
    kind: Literal["erase"]
    target_id: str = Field(min_length=1, max_length=80)

    @field_validator("target_id")
    @classmethod
    def stable_target_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)


class ClearCommand(CommandBase):
    kind: Literal["clear"]


class CameraCommand(CommandBase):
    kind: Literal["camera"]
    space: Space = "board"
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    width: float = Field(default=0.55, gt=0.0, le=1.0)
    height: float = Field(default=0.55, gt=0.0, le=1.0)


SceneCommand = Annotated[
    Union[
        TextCommand,
        MathCommand,
        SegmentCommand,
        RectCommand,
        HighlightCommand,
        CircleCommand,
        AngleCommand,
        PolylineCommand,
        GraphCommand,
        BarChartCommand,
        VennCommand,
        EraseCommand,
        ClearCommand,
        CameraCommand,
    ],
    Field(discriminator="kind"),
]


# What the planner actually fills in.
#
# `SceneCommand` is a 14-member discriminated union, and measurement showed the
# planner almost never reaches `text`/`math` out of it — it picks a geometry
# primitive and encodes labels as zero-length lines. Splitting writing from
# drawing means choosing to write is a 2-way choice competing against nothing,
# instead of a 14-way one competing against twelve shapes.
#
# erase/clear/camera are deliberately absent: `_normalize_lesson` has always
# dropped them, so offering them only widened the choice for no effect.
WriteCommand = Annotated[
    Union[TextCommand, MathCommand],
    Field(discriminator="kind"),
]

DrawCommand = Annotated[
    Union[
        SegmentCommand,
        RectCommand,
        HighlightCommand,
        CircleCommand,
        AngleCommand,
        PolylineCommand,
        GraphCommand,
        BarChartCommand,
        VennCommand,
    ],
    Field(discriminator="kind"),
]


class TeachingBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    teaching_goal: str = Field(min_length=3, max_length=180)
    spoken_text: str = Field(min_length=3, max_length=900)
    caption: str = Field(min_length=1, max_length=220)
    strategy: str = Field(min_length=2, max_length=80)
    # A reconstructed diagram and its labels share this budget with the beat's
    # own board notes, so it has to hold a fully labelled figure.
    commands: list[SceneCommand] = Field(default_factory=list, max_length=24)
    pause_after_ms: int = Field(default=0, ge=0, le=3000)
    checkpoint: bool = False


class LessonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Literal["math", "reading_writing"]
    question_summary: str = Field(min_length=5, max_length=600)
    final_answer: str = Field(min_length=1, max_length=300)
    answer_explanation: str = Field(min_length=5, max_length=1200)
    confidence: float = Field(ge=0.0, le=1.0)
    beats: list[TeachingBeat] = Field(min_length=2, max_length=8)


class BeatDraft(BaseModel):
    """One teaching beat as the planner writes it, before flattening."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    teaching_goal: str = Field(min_length=3, max_length=180)
    spoken_text: str = Field(min_length=3, max_length=900)
    caption: str = Field(min_length=1, max_length=220)
    strategy: str = Field(min_length=2, max_length=80)
    # At least one note per beat: a beat that draws without writing leaves the
    # board silent, which is the state the reviewer kept rejecting.
    write: list[WriteCommand] = Field(min_length=1, max_length=10)
    draw: list[DrawCommand] = Field(default_factory=list, max_length=12)
    pause_after_ms: int = Field(default=0, ge=0, le=3000)
    checkpoint: bool = False


class LessonDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Literal["math", "reading_writing"]
    question_summary: str = Field(min_length=5, max_length=600)
    final_answer: str = Field(min_length=1, max_length=300)
    answer_explanation: str = Field(min_length=5, max_length=1200)
    confidence: float = Field(ge=0.0, le=1.0)
    beats: list[BeatDraft] = Field(min_length=2, max_length=8)

    def to_plan(self) -> "LessonPlan":
        """
        Flatten to the shape the renderer, reviewer, and stored lessons use.

        Writing comes first so a highlight in `draw` can always resolve a
        target that was written earlier in the same beat — `_normalize_lesson`
        drops highlights whose target has not been written yet.
        """
        return LessonPlan(
            domain=self.domain,
            question_summary=self.question_summary,
            final_answer=self.final_answer,
            answer_explanation=self.answer_explanation,
            confidence=self.confidence,
            beats=[
                TeachingBeat(
                    id=beat.id,
                    teaching_goal=beat.teaching_goal,
                    spoken_text=beat.spoken_text,
                    caption=beat.caption,
                    strategy=beat.strategy,
                    commands=[*beat.write, *beat.draw],
                    pause_after_ms=beat.pause_after_ms,
                    checkpoint=beat.checkpoint,
                )
                for beat in self.beats
            ],
        )


class LessonReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    issues: list[str] = Field(default_factory=list, max_length=8)


class WorkDiagnosis(BaseModel):
    """A verdict on the student's own working, not a solution from scratch."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["correct", "incorrect", "unclear"]
    restated_steps: list[str] = Field(default_factory=list, max_length=12)
    # 1-indexed into restated_steps; 0 means "no step is wrong".
    first_error_step: int = Field(default=0, ge=0, le=12)
    error_quote: str = Field(default="", max_length=200)
    misconception: str = Field(default="", max_length=400)
    next_hint: str = Field(min_length=3, max_length=400)
    correct_answer: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def verdict_and_error_step_agree(self) -> "WorkDiagnosis":
        # Telling a student their correct step is wrong is the most damaging
        # thing this feature can do, so the shape itself forbids the states
        # that would express it incoherently.
        if self.verdict == "incorrect" and self.first_error_step == 0:
            raise ValueError("an 'incorrect' verdict must name the first wrong step")
        if self.verdict != "incorrect" and self.first_error_step != 0:
            raise ValueError("only an 'incorrect' verdict may name a wrong step")
        if self.first_error_step > len(self.restated_steps):
            raise ValueError("first_error_step must point at a restated step")
        return self


class DiagramSpecBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#1769e0", max_length=24)

    @field_validator("id")
    @classmethod
    def stable_id_characters(cls, value: str) -> str:
        return _validate_stable_id(value)


class DiagramLineSpec(DiagramSpecBase):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)


class DiagramRectSpec(DiagramSpecBase):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    preserve_aspect: bool = False


class DiagramPolylineSpec(DiagramSpecBase):
    points: list[Point] = Field(min_length=2, max_length=16)
    closed: bool = True


class DiagramCircleSpec(DiagramSpecBase):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    radius: float = Field(gt=0.0, le=0.5)


class DiagramAngleSpec(DiagramSpecBase):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    radius: float = Field(gt=0.0, le=0.5)
    start_angle: float = Field(ge=-360.0, le=360.0)
    end_angle: float = Field(ge=-360.0, le=360.0)


class DiagramLabelSpec(DiagramSpecBase):
    text: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    size: float = Field(default=0.045, ge=0.02, le=0.08)


class ImageQuestionAnalysis(BaseModel):
    """A small vision-only contract that the deterministic diagram renderer compiles."""

    model_config = ConfigDict(extra="forbid")

    extracted_question: str = Field(min_length=5, max_length=2400)
    diagram_summary: str = Field(default="", max_length=800)
    should_reconstruct: bool = False
    rects: list[DiagramRectSpec] = Field(default_factory=list, max_length=4)
    lines: list[DiagramLineSpec] = Field(default_factory=list, max_length=10)
    polylines: list[DiagramPolylineSpec] = Field(default_factory=list, max_length=4)
    circles: list[DiagramCircleSpec] = Field(default_factory=list, max_length=8)
    angles: list[DiagramAngleSpec] = Field(default_factory=list, max_length=6)
    labels: list[DiagramLabelSpec] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def reconstructed_diagram_has_geometry(self) -> "ImageQuestionAnalysis":
        geometry_count = len(self.rects) + len(self.lines) + len(self.polylines) + len(self.circles)
        if self.should_reconstruct and geometry_count == 0:
            raise ValueError("a reconstructed diagram requires at least one geometric element")
        return self

from __future__ import annotations

import base64
import json
import re
from typing import Any, Sequence, Union

from pydantic_ai import BinaryContent
from pydantic_ai.messages import UserContent

from lesson_models import (
    HighlightCommand,
    ImageQuestionAnalysis,
    LessonPlan,
    SegmentCommand,
    TeachingBeat,
    TextCommand,
    WorkDiagnosis,
)


MAX_SOURCE_BYTES = 4 * 1024 * 1024
SUPPORTED_SOURCE_MEDIA_TYPES = {"image/jpeg", "image/png"}
MAX_BEAT_COMMANDS = 24
MAX_DIAGRAM_COMMANDS = 16
MAX_DIAGRAM_GEOMETRY = 9
VERTEX_SNAP_TOLERANCE = 0.012
PromptContent = Union[str, Sequence[UserContent]]


def _source_content(prompt: str, media_type: str, source_base64: str) -> PromptContent:
    if not source_base64:
        return prompt
    if media_type not in SUPPORTED_SOURCE_MEDIA_TYPES:
        raise ValueError("Upload a PNG or JPEG image")
    try:
        image_bytes = base64.b64decode(source_base64, validate=True)
    except ValueError as error:
        raise ValueError("The question image is not valid base64") from error
    if not image_bytes or len(image_bytes) > MAX_SOURCE_BYTES:
        raise ValueError("The prepared question image must be between 1 byte and 4 MB")
    return [
        prompt,
        BinaryContent(
            data=image_bytes,
            media_type=media_type,
            vendor_metadata={"detail": "high"},
        ),
    ]


def _might_be_a_topic(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 160 or re.search(r"\b[A-D]\)", stripped):
        return False
    asks_to_be_taught = re.search(
        r"\b(teach|explain|learn|help me with|how do i|struggle|bad at|revise|practice)\b",
        stripped,
        re.IGNORECASE,
    )
    return bool(asks_to_be_taught) or "?" not in stripped


def _same_answer(left: str, right: str) -> bool:
    def canonical(text: str) -> str:
        lowered = text.lower()
        for dash in ("−", "–", "—"):
            lowered = lowered.replace(dash, "-")
        lowered = lowered.replace("·", "*").replace("×", "*").replace("π", "pi")
        return re.sub(r"[\s,]+", "", lowered)

    return canonical(left) == canonical(right)


def _safe_error(error: Exception) -> str:
    raw = str(error).strip()
    message = raw.splitlines()[0] if raw else type(error).__name__
    return f"The tutor could not prepare this lesson: {message[:220]}"


def _normalize_lesson(
    lesson: LessonPlan,
    *,
    source_has_image: bool = False,
    question_text: str = "",
) -> LessonPlan:
    """Keep only scene commands that the deterministic renderer can honor."""
    source_words = (question_text or lesson.question_summary).lower()
    venn_relevant = any(
        phrase in source_words
        for phrase in (
            "venn", " both ", "neither", "at least one", "overlap", "union",
            "intersection", "survey", "students who",
        )
    )
    bars_relevant = any(
        phrase in source_words
        for phrase in ("distribution", "frequency", "probability", "histogram", "data table", "bar chart")
    )
    written_ids: set[str] = set()
    visual_family: str | None = None
    visual_emitted = False
    diagram_signatures: set[str] = set()
    normalized_beats: list[TeachingBeat] = []

    if not source_has_image and any(
        getattr(command, "space", "") == "diagram"
        for beat in lesson.beats
        for command in beat.commands
    ):
        visual_family = "diagram"

    for beat_index, beat in enumerate(lesson.beats):
        commands: list[Any] = []
        for command in beat.commands:
            if command.kind in {"erase", "clear", "camera"}:
                continue
            if isinstance(command, SegmentCommand) and (command.x, command.y) == (command.x2, command.y2):
                continue
            if source_has_image and getattr(command, "space", "") in {"source", "diagram"}:
                continue
            if getattr(command, "space", "") == "diagram":
                signature = json.dumps(
                    command.model_dump(mode="json", exclude={"id"}), sort_keys=True
                )
                if signature in diagram_signatures:
                    continue
                diagram_signatures.add(signature)
            if command.kind in {"text", "math"}:
                if command.kind == "math" and len(command.text.strip()) < 2:
                    continue
                written_ids.add(command.id)
                commands.append(command)
                continue
            if command.kind == "highlight":
                if command.target_id and command.target_id in written_ids:
                    commands.append(command)
                continue
            if command.kind in {"graph", "bar_chart", "venn"}:
                if command.kind == "graph" and lesson.domain != "math":
                    continue
                if command.kind == "venn" and not venn_relevant:
                    continue
                if command.kind == "bar_chart":
                    if not bars_relevant:
                        continue
                    labels = [bar.label.strip() for bar in command.bars]
                    if len(set(labels)) != len(labels) or all(
                        re.fullmatch(r"[A-Da-d](?:[).:]?)", label) for label in labels
                    ):
                        continue
                if visual_family is None:
                    visual_family = command.kind
                if command.kind != visual_family or visual_emitted:
                    continue
                visual_emitted = True
            commands.append(command)

        if not commands:
            commands.append(
                TextCommand(
                    id=f"auto-note-{beat_index + 1}",
                    kind="text",
                    space="board",
                    layout="flow",
                    text=beat.caption,
                    color="#1769e0",
                    size=0.055,
                )
            )
        normalized_beats.append(beat.model_copy(update={"commands": commands}))
    return lesson.model_copy(update={"beats": normalized_beats})


class _VertexSnapper:
    def __init__(self, points: list[tuple[float, float]]) -> None:
        clusters: list[list[tuple[float, float]]] = []
        for point in points:
            for cluster in clusters:
                anchor = cluster[0]
                if abs(point[0] - anchor[0]) <= VERTEX_SNAP_TOLERANCE and abs(point[1] - anchor[1]) <= VERTEX_SNAP_TOLERANCE:
                    cluster.append(point)
                    break
            else:
                clusters.append([point])
        self.clusters = [
            (cluster[0], (sum(x for x, _ in cluster) / len(cluster), sum(y for _, y in cluster) / len(cluster)))
            for cluster in clusters
        ]

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        for anchor, centroid in self.clusters:
            if abs(x - anchor[0]) <= VERTEX_SNAP_TOLERANCE and abs(y - anchor[1]) <= VERTEX_SNAP_TOLERANCE:
                return round(centroid[0], 4), round(centroid[1], 4)
        return x, y


def _compile_diagram(analysis: ImageQuestionAnalysis) -> list[dict[str, Any]]:
    if not analysis.should_reconstruct:
        return []
    points: list[tuple[float, float]] = []
    for line in analysis.lines:
        points.extend([(line.x, line.y), (line.x2, line.y2)])
    for polyline in analysis.polylines:
        points.extend((point.x, point.y) for point in polyline.points)
    snap = _VertexSnapper(points)
    geometry: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    used: set[str] = set()

    def add(target: list[dict[str, Any]], kind: str, raw_id: str, payload: dict[str, Any]) -> None:
        identifier = f"rebuild:{kind}:{raw_id}"
        if identifier not in used:
            used.add(identifier)
            target.append({"id": identifier, "kind": kind, "space": "diagram", **payload})

    for rect in analysis.rects:
        add(geometry, "rect", rect.id, {
            "x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height,
            "color": rect.color, "size": 0.025, "opacity": 1.0,
            "preserve_aspect": rect.preserve_aspect,
        })
    for line in analysis.lines:
        x, y = snap(line.x, line.y)
        x2, y2 = snap(line.x2, line.y2)
        if (x, y) != (x2, y2):
            add(geometry, "line", line.id, {
                "x": x, "y": y, "x2": x2, "y2": y2,
                "color": line.color, "size": 0.025, "opacity": 1.0,
            })
    for polyline in analysis.polylines:
        poly_points: list[dict[str, float]] = []
        for point in polyline.points:
            x, y = snap(point.x, point.y)
            candidate = {"x": x, "y": y}
            if not poly_points or poly_points[-1] != candidate:
                poly_points.append(candidate)
        if polyline.closed and len(poly_points) > 2 and poly_points[0] != poly_points[-1]:
            poly_points.append(poly_points[0])
        if len(poly_points) >= 2:
            add(geometry, "polyline", polyline.id, {
                "points": poly_points, "color": polyline.color, "size": 0.03, "opacity": 1.0,
            })
    for circle in analysis.circles:
        x, y = snap(circle.x, circle.y)
        add(geometry, "circle", circle.id, {
            "x": x, "y": y, "radius": circle.radius,
            "color": circle.color, "size": 0.025, "opacity": 1.0,
        })
    for angle in analysis.angles:
        x, y = snap(angle.x, angle.y)
        add(geometry, "angle", angle.id, {
            "x": x, "y": y, "radius": angle.radius,
            "start_angle": angle.start_angle, "end_angle": angle.end_angle,
            "color": angle.color, "size": 0.025, "opacity": 1.0,
        })
    for label in analysis.labels:
        add(labels, "text", label.id, {
            "layout": "absolute", "text": label.text, "x": label.x, "y": label.y,
            "color": label.color, "size": label.size, "opacity": 1.0,
        })
    geometry = geometry[:MAX_DIAGRAM_GEOMETRY]
    return (geometry + labels[: MAX_DIAGRAM_COMMANDS - len(geometry)])[:MAX_DIAGRAM_COMMANDS]


def _inject_diagram(lesson: LessonPlan, diagram_commands: list[dict[str, Any]]) -> LessonPlan:
    if not diagram_commands:
        return lesson
    payload = lesson.model_dump(mode="json")
    for beat in payload["beats"]:
        beat["commands"] = [
            command for command in beat["commands"]
            if command["kind"] not in {"graph", "bar_chart", "venn", "clear"}
            and command.get("space") != "diagram"
        ]
    room = max(0, MAX_BEAT_COMMANDS - len(diagram_commands))
    payload["beats"][0]["commands"] = diagram_commands + payload["beats"][0]["commands"][:room]
    return LessonPlan.model_validate(payload)


def _note(index: int, text: str, *, color: str = "#1769e0") -> TextCommand:
    return TextCommand(
        id=f"work-note-{index}", kind="text", space="board", layout="flow",
        text=text[:240], color=color, size=0.05,
    )


def _beat(identifier: str, goal: str, spoken: str, caption: str, strategy: str, commands: list[Any]) -> TeachingBeat:
    return TeachingBeat(
        id=identifier, teaching_goal=goal[:180], spoken_text=(spoken or goal)[:900],
        caption=caption[:220], strategy=strategy[:80], commands=commands,
    )


def _explanation(text: str, fallback: str) -> str:
    cleaned = text.strip()
    return cleaned if len(cleaned) >= 5 else fallback


def _diagnosis_to_lesson(diagnosis: WorkDiagnosis, question_text: str) -> LessonPlan:
    summary = (question_text.strip() or "The student's submitted working")[:600]
    steps = [step.strip() for step in diagnosis.restated_steps if step.strip()]
    if diagnosis.verdict == "correct":
        notes = [_note(index, f"{index + 1}. {step}") for index, step in enumerate(steps[:6])]
        return LessonPlan(
            domain="math", question_summary=summary, final_answer=diagnosis.correct_answer,
            answer_explanation=_explanation(diagnosis.misconception, "Every step in the submitted work is correct."),
            confidence=diagnosis.confidence,
            beats=[
                _beat("work:confirm", "Confirm the work is correct", "I checked every step, and this is right. Let me show you what you did well.", "Your work checks out", "confirm", notes or [_note(0, "Your working is correct.")]),
                _beat("work:answer", "State the verified answer", f"Your answer, {diagnosis.correct_answer}, is the one I get too. {diagnosis.next_hint}", f"Answer: {diagnosis.correct_answer}", "confirm", [_note(90, f"Answer: {diagnosis.correct_answer}", color="#1a7f37")]),
            ],
        )
    if diagnosis.verdict == "unclear":
        return LessonPlan(
            domain="math", question_summary=summary,
            final_answer="I need one more detail before I can check this.",
            answer_explanation=_explanation(diagnosis.misconception, "The submitted work could not be read confidently."),
            confidence=diagnosis.confidence,
            beats=[
                _beat("work:unclear", "Say honestly that the work cannot be judged yet", "I don't want to guess and tell you something wrong, so let me ask first.", "I want to make sure I'm following you", "clarify", [_note(0, "I couldn't follow every step here.")]),
                _beat("work:ask", "Ask the question that would settle it", diagnosis.next_hint, diagnosis.next_hint[:220], "clarify", [_note(1, diagnosis.next_hint, color="#b26a00")]),
            ],
        )

    error_index = diagnosis.first_error_step - 1
    recap: list[Any] = []
    for index, step in enumerate(steps[:6]):
        color = "#1a7f37" if index < error_index else "#d93025" if index == error_index else "#5f6b76"
        recap.append(_note(index, f"{index + 1}. {step}", color=color))
    if error_index < len(recap):
        recap.append(HighlightCommand(
            id="work-error-highlight", kind="highlight", space="board",
            target_id=f"work-note-{error_index}",
        ))
    good_steps = error_index
    opening = (
        "Let's look at the very first step together." if good_steps == 0
        else "The first step is right — the break comes after that." if good_steps == 1
        else f"The first {good_steps} steps are right — the break comes after that."
    )
    return LessonPlan(
        domain="math", question_summary=summary, final_answer=diagnosis.correct_answer,
        answer_explanation=_explanation(diagnosis.misconception, "The submitted work goes wrong at the marked step."),
        confidence=diagnosis.confidence,
        beats=[
            _beat("work:recap", "Show the student their own steps", f"Here's what you did. {opening}", "Here's your working", "diagnose", recap or [_note(0, "I read through your working.")]),
            _beat("work:error", "Point at the first step that breaks", f"Step {diagnosis.first_error_step} is where it goes wrong. {diagnosis.misconception}", f"Step {diagnosis.first_error_step} is the first slip", "diagnose", [_note(80, f"Step {diagnosis.first_error_step}: {diagnosis.error_quote}"[:240], color="#d93025")]),
            _beat("work:hint", "Hand back the next move without solving it", diagnosis.next_hint, "Try this next", "hint", [_note(81, diagnosis.next_hint, color="#b26a00")]),
        ],
    )


def _assistant_message_text(lesson: LessonPlan) -> str:
    narration = " ".join(
        beat.spoken_text.strip() for beat in lesson.beats if beat.spoken_text.strip()
    )
    return f"{narration or lesson.answer_explanation}\n\nAnswer: {lesson.final_answer}"

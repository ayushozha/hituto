import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from typing import Any, Sequence, Union

import httpx
from pydantic_ai import BinaryContent
from pydantic_ai.messages import UserContent
from rbt.std.ciphertext.v1.ciphertext_rbt import Ciphertext
from reboot.aio.auth.authorizers import allow_if, has_verified_token, is_app_internal
from reboot.aio.contexts import ReaderContext, TransactionContext, WorkflowContext, WriterContext
from reboot.aio.workflows import at_least_once
from reboot.std.ciphertext.v1.ciphertext import (
    APP_SHARED_KEY_MANAGER_ID,
    make_associated_data,
)
from reboot.std.collections.ordered_map.v1.ordered_map import OrderedMap
from sat_tutor.v1.tutor import ChatMessage
from sat_tutor.v1.tutor_rbt import TutorMessage, TutorSession

from lesson_models import ImageQuestionAnalysis, LessonPlan, SegmentCommand, TextCommand
from tutor_agents import (
    llm_configuration_message,
    planner_agent,
    replanner_agent,
    reviewer_agent,
    vision_configuration_message,
    vision_diagram_agent,
    vision_reviewer_agent,
)


MAX_SOURCE_BYTES = 4 * 1024 * 1024
SUPPORTED_SOURCE_MEDIA_TYPES = {"image/jpeg", "image/png"}
# Must stay at or below `TeachingBeat.commands`' own limit, with room left for
# the beat's board notes.
MAX_BEAT_COMMANDS = 24
MAX_DIAGRAM_COMMANDS = 16
MAX_DIAGRAM_GEOMETRY = 9
# Endpoints closer than this in normalized diagram units were meant to be the
# same vertex. Roughly 1% of the panel: tight enough not to merge distinct
# features, loose enough to close a hand-estimated corner.
VERTEX_SNAP_TOLERANCE = 0.012
PromptContent = Union[str, Sequence[UserContent]]
logger = logging.getLogger(__name__)


def _source_content(
    prompt: str,
    source_media_type: str,
    source_base64: str,
) -> PromptContent:
    if not source_base64:
        return prompt
    if source_media_type not in SUPPORTED_SOURCE_MEDIA_TYPES:
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
            media_type=source_media_type,
            vendor_metadata={"detail": "high"},
        ),
    ]


def _safe_error(error: Exception) -> str:
    message = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return f"The tutor could not prepare this lesson: {message[:220]}"


def _normalize_lesson(
    lesson: LessonPlan,
    *,
    source_has_image: bool = False,
    question_text: str = "",
) -> LessonPlan:
    """Remove model decorations that cannot refer to a real rendered element."""
    source_words = (question_text or lesson.question_summary).lower()
    venn_is_relevant = any(
        phrase in source_words
        for phrase in (
            "venn",
            " both ",
            "neither",
            "at least one",
            "overlap",
            "union",
            "intersection",
            "survey",
            "students who",
        )
    )
    bars_are_relevant = any(
        phrase in source_words
        for phrase in (
            "distribution",
            "frequency",
            "probability",
            "histogram",
            "data table",
            "bar chart",
        )
    )
    written_ids: set[str] = set()
    visual_emitted = False
    has_diagram = not source_has_image and any(
        getattr(command, "space", "") == "diagram"
        and command.kind not in {"erase", "clear", "camera"}
        for beat in lesson.beats
        for command in beat.commands
    )
    visual_family: str | None = "diagram" if has_diagram else None
    diagram_signatures: set[str] = set()
    normalized_beats = []
    for beat_index, beat in enumerate(lesson.beats):
        commands = []
        for command in beat.commands:
            # Each assistant response owns a fresh inline activity card, so
            # destructive scene commands have nothing useful to target here.
            if command.kind in {"erase", "clear", "camera"}:
                continue
            # A zero-length segment renders as nothing. The planner reaches for
            # one when it means to write a label but picks the wrong member of
            # the command union, which leaves the spoken beat describing labels
            # that were never drawn — the single most common reason a verified
            # lesson gets rejected. Dropping it lets the empty-beat fallback
            # below turn the caption into writing the student can actually see.
            if isinstance(command, SegmentCommand) and (command.x, command.y) == (
                command.x2,
                command.y2,
            ):
                continue
            if source_has_image and (
                command.kind == "clear"
                or getattr(command, "space", "") in {"diagram", "source"}
            ):
                continue
            if (
                getattr(command, "space", "") == "diagram"
                and command.kind not in {"erase", "clear", "camera"}
            ):
                signature = json.dumps(
                    command.model_dump(mode="json", exclude={"id"}),
                    sort_keys=True,
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
                if command.kind == "venn" and not venn_is_relevant:
                    continue
                if command.kind == "bar_chart" and not bars_are_relevant:
                    continue
                if command.kind == "bar_chart":
                    labels = [bar.label.strip() for bar in command.bars]
                    if len(set(labels)) != len(labels) or all(
                        re.fullmatch(r"[A-Da-d](?:[).:]?)", label)
                        for label in labels
                    ):
                        continue
                if visual_family is None:
                    visual_family = command.kind
                if command.kind != visual_family:
                    continue
                # One panel means one chart, not one *kind* of chart. The
                # renderer only ever shows the last, so extra copies just burn
                # the beat's command budget.
                if visual_emitted:
                    continue
                visual_emitted = True
            commands.append(command)
        if not commands:
            # Some OpenAI-compatible structured-output providers choose an
            # empty decoration from a large command union. Keep the verified
            # lesson teachable by turning the beat caption into visible board
            # writing; invalid decorations never reach the browser.
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


def _snap_vertices(analysis: ImageQuestionAnalysis) -> "_VertexSnapper":
    """
    Cluster near-coincident endpoints so a shared corner is exactly shared.

    A vision model estimates each vertex independently, so the two ends of a
    triangle's base can land 0.006 apart — enough to render as a visible gap
    or a hairline overshoot at every corner of the figure.
    """
    points: list[tuple[float, float]] = []
    for line in analysis.lines:
        points.append((line.x, line.y))
        points.append((line.x2, line.y2))
    for polyline in analysis.polylines:
        points.extend((point.x, point.y) for point in polyline.points)
    for rect in analysis.rects:
        points.extend(
            [
                (rect.x, rect.y),
                (rect.x + rect.width, rect.y),
                (rect.x, rect.y + rect.height),
                (rect.x + rect.width, rect.y + rect.height),
            ]
        )

    clusters: list[list[tuple[float, float]]] = []
    for point in points:
        for cluster in clusters:
            anchor = cluster[0]
            if (
                abs(point[0] - anchor[0]) <= VERTEX_SNAP_TOLERANCE
                and abs(point[1] - anchor[1]) <= VERTEX_SNAP_TOLERANCE
            ):
                cluster.append(point)
                break
        else:
            clusters.append([point])
    return _VertexSnapper(
        [
            (
                cluster[0],
                (
                    sum(item[0] for item in cluster) / len(cluster),
                    sum(item[1] for item in cluster) / len(cluster),
                ),
            )
            for cluster in clusters
        ]
    )


class _VertexSnapper:
    def __init__(self, clusters: list[tuple[tuple[float, float], tuple[float, float]]]) -> None:
        self._clusters = clusters

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        for anchor, centroid in self._clusters:
            if (
                abs(x - anchor[0]) <= VERTEX_SNAP_TOLERANCE
                and abs(y - anchor[1]) <= VERTEX_SNAP_TOLERANCE
            ):
                return round(centroid[0], 4), round(centroid[1], 4)
        return x, y


def _compile_diagram(analysis: ImageQuestionAnalysis) -> list[dict[str, Any]]:
    """Compile the small vision contract into trusted scene command payloads."""
    if not analysis.should_reconstruct:
        return []

    snap = _snap_vertices(analysis)
    geometry: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    def add(target: list[dict[str, Any]], kind: str, raw_id: str, payload: dict[str, Any]) -> None:
        command_id = f"rebuild:{kind}:{raw_id}"
        if command_id in used_ids:
            return
        used_ids.add(command_id)
        target.append({"id": command_id, "kind": kind, "space": "diagram", **payload})

    for rect in analysis.rects:
        add(
            geometry,
            "rect",
            rect.id,
            {
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
                "color": rect.color,
                "size": 0.025,
                "opacity": 1.0,
                "preserve_aspect": rect.preserve_aspect,
            },
        )
    for line in analysis.lines:
        start_x, start_y = snap(line.x, line.y)
        end_x, end_y = snap(line.x2, line.y2)
        if (start_x, start_y) == (end_x, end_y):
            # A segment whose ends snapped together carried no length to begin
            # with; drawing it would just thicken a vertex.
            continue
        add(
            geometry,
            "line",
            line.id,
            {
                "x": start_x,
                "y": start_y,
                "x2": end_x,
                "y2": end_y,
                "color": line.color,
                "size": 0.025,
                "opacity": 1.0,
            },
        )
    for polyline in analysis.polylines:
        points: list[dict[str, float]] = []
        for item in polyline.points:
            snapped_x, snapped_y = snap(item.x, item.y)
            candidate = {"x": snapped_x, "y": snapped_y}
            if not points or points[-1] != candidate:
                points.append(candidate)
        if polyline.closed and len(points) > 2 and points[0] != points[-1]:
            points.append(points[0])
        if len(points) < 2:
            continue
        add(
            geometry,
            "polyline",
            polyline.id,
            {
                "points": points,
                "color": polyline.color,
                "size": 0.03,
                "opacity": 1.0,
            },
        )
    for circle in analysis.circles:
        center_x, center_y = snap(circle.x, circle.y)
        add(
            geometry,
            "circle",
            circle.id,
            {
                "x": center_x,
                "y": center_y,
                "radius": circle.radius,
                "color": circle.color,
                "size": 0.025,
                "opacity": 1.0,
            },
        )
    for angle in analysis.angles:
        vertex_x, vertex_y = snap(angle.x, angle.y)
        add(
            geometry,
            "angle",
            angle.id,
            {
                "x": vertex_x,
                "y": vertex_y,
                "radius": angle.radius,
                "start_angle": angle.start_angle,
                "end_angle": angle.end_angle,
                "color": angle.color,
                "size": 0.025,
                "opacity": 1.0,
            },
        )
    for label in analysis.labels:
        add(
            labels,
            "text",
            label.id,
            {
                "layout": "absolute",
                "text": label.text,
                "x": label.x,
                "y": label.y,
                # No width/height: a fixed box clipped longer labels and the
                # renderer measures the real text anyway.
                "color": label.color,
                "size": label.size,
                "opacity": 1.0,
            },
        )

    geometry = geometry[:MAX_DIAGRAM_GEOMETRY]
    return (geometry + labels[: MAX_DIAGRAM_COMMANDS - len(geometry)])[:MAX_DIAGRAM_COMMANDS]


def _inject_diagram(
    lesson: LessonPlan,
    diagram_commands: list[dict[str, Any]],
) -> LessonPlan:
    if not diagram_commands:
        return lesson
    payload = lesson.model_dump(mode="json")
    for beat in payload["beats"]:
        beat["commands"] = [
            command
            for command in beat["commands"]
            if command["kind"] not in {"graph", "bar_chart", "venn", "clear"}
            and command.get("space") != "diagram"
        ]
    first_commands = payload["beats"][0]["commands"]
    # `max(0, ...)`: a negative slice bound would silently drop notes from the
    # end of the list instead of keeping none of them.
    room = max(0, MAX_BEAT_COMMANDS - len(diagram_commands))
    payload["beats"][0]["commands"] = diagram_commands + first_commands[:room]
    return LessonPlan.model_validate(payload)


def _voice_associated_data(session_id: str, generation: int) -> bytes:
    return make_associated_data(
        session_id=session_id,
        purpose=f"deepgram-browser-token:{generation}",
    )


def _message_index_id(session_id: str, revision: int) -> str:
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return f"sat-chat:{session_key}:{revision}"


def _message_key(generation: int, role: str) -> str:
    role_order = 0 if role == "user" else 1
    return f"{generation:020d}:{role_order}"


def _message_id(session_id: str, revision: int, generation: int, role: str) -> str:
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return f"sat-message:{session_key}:{revision}:{generation}:{role}"


def _assistant_message_text(lesson: LessonPlan) -> str:
    narration = " ".join(
        beat.spoken_text.strip() for beat in lesson.beats if beat.spoken_text.strip()
    )
    return f"{narration or lesson.answer_explanation}\n\nAnswer: {lesson.final_answer}"


class TutorMessageServicer(TutorMessage.Servicer):
    def authorizer(self):
        return allow_if(any=[has_verified_token, is_app_internal])

    async def set(
        self,
        context: WriterContext,
        request: TutorMessage.SetRequest,
    ) -> None:
        self.state.role = request.role
        self.state.text = request.text
        self.state.lesson_json = request.lesson_json
        self.state.source_kind = request.source_kind
        self.state.generation = request.generation
        self.state.status = request.status

    async def snapshot(
        self,
        context: ReaderContext,
    ) -> TutorMessage.SnapshotResponse:
        return TutorMessage.SnapshotResponse(
            id=self.ref().state_id,
            role=self.state.role,
            text=self.state.text,
            lesson_json=self.state.lesson_json,
            source_kind=self.state.source_kind,
            generation=self.state.generation,
            status=self.state.status,
        )


class TutorSessionServicer(TutorSession.Servicer):
    def authorizer(self):
        # Browser calls carry a verified OAuth identity; scheduled lesson and
        # voice workflows re-enter this actor as app-internal calls.
        return allow_if(any=[has_verified_token, is_app_internal])

    async def ensure(self, context: WriterContext) -> None:
        # Additively migrate existing browser sessions to the durable chat index.
        if not self.state.message_index_id:
            self.state.message_index_id = _message_index_id(
                self.ref().state_id,
                self.state.chat_revision,
            )

    async def snapshot(
        self,
        context: ReaderContext,
    ) -> TutorSession.SnapshotResponse:
        return TutorSession.SnapshotResponse(
            question_text=self.state.question_text,
            source_kind=self.state.source_kind,
            lesson_json=self.state.lesson_json,
            status=self.state.status,
            error_message=self.state.error_message,
            revision=self.state.revision,
            last_student_message=self.state.last_student_message,
            generation=self.state.generation,
            voice_generation=self.state.voice_generation,
            voice_status=self.state.voice_status,
            voice_error=self.state.voice_error,
        )

    async def messages(
        self,
        context: ReaderContext,
        request: TutorSession.MessagesRequest,
    ) -> TutorSession.MessagesResponse:
        if not self.state.message_index_id or self.state.message_count == 0:
            return TutorSession.MessagesResponse()
        limit = min(100, max(1, request.limit or 80))
        page = await OrderedMap.ref(self.state.message_index_id).range(
            context,
            start_key=request.cursor,
            limit=limit,
        )
        message_ids = [entry.bytes.decode("utf-8") for entry in page.entries]
        snapshots = await asyncio.gather(
            *(TutorMessage.ref(message_id).snapshot(context) for message_id in message_ids)
        )
        messages = [
            ChatMessage(
                id=message.id,
                role=message.role,
                text=message.text,
                lesson_json=message.lesson_json,
                source_kind=message.source_kind,
                generation=message.generation,
                status=message.status,
            )
            for message in snapshots
        ]
        next_cursor = f"{page.entries[-1].key}\x00" if len(page.entries) == limit else ""
        return TutorSession.MessagesResponse(messages=messages, next_cursor=next_cursor)

    async def reset(self, context: WriterContext) -> None:
        self.state.question_text = ""
        self.state.source_kind = ""
        self.state.lesson_json = ""
        self.state.status = ""
        self.state.error_message = ""
        self.state.revision += 1
        self.state.last_student_message = ""
        self.state.generation += 1
        self.state.voice_generation += 1
        self.state.voice_status = ""
        self.state.voice_error = ""
        self.state.voice_token_ciphertext_id = ""
        self.state.tts_model = ""
        self.state.chat_revision += 1
        self.state.message_count = 0
        self.state.message_index_id = _message_index_id(
            self.ref().state_id,
            self.state.chat_revision,
        )

    async def _append_user_message(
        self,
        context: TransactionContext,
        *,
        generation: int,
        text: str,
        source_kind: str,
    ) -> None:
        if not self.state.message_index_id:
            self.state.message_index_id = _message_index_id(
                self.ref().state_id,
                self.state.chat_revision,
            )
        message_id = _message_id(
            self.ref().state_id,
            self.state.chat_revision,
            generation,
            "user",
        )
        await TutorMessage.ref(message_id).set(
            context,
            role="user",
            text=text,
            lesson_json="",
            source_kind=source_kind,
            generation=generation,
            status="ready",
        )
        await OrderedMap.ref(self.state.message_index_id).insert(
            context,
            key=_message_key(generation, "user"),
            bytes=message_id.encode("utf-8"),
        )
        self.state.message_count += 1

    async def start_lesson(
        self,
        context: TransactionContext,
        request: TutorSession.StartLessonRequest,
    ) -> TutorSession.StartLessonResponse:
        self.state.generation += 1
        generation = self.state.generation
        self.state.question_text = request.question_text.strip()
        self.state.source_kind = request.source_kind
        self.state.lesson_json = ""
        self.state.status = "thinking"
        self.state.error_message = ""
        self.state.last_student_message = ""
        question_message = request.question_text.strip()
        if request.source_kind == "image":
            question_message = (
                f"{question_message}\n\nUploaded an SAT question image."
                if question_message
                else "Uploaded an SAT question image."
            )
        await self._append_user_message(
            context,
            generation=generation,
            text=question_message,
            source_kind=request.source_kind,
        )
        await self.ref().schedule().prepare_lesson(
            context,
            question_text=request.question_text,
            source_kind=request.source_kind,
            source_media_type=request.source_media_type,
            source_base64=request.source_base64,
            generation=generation,
        )
        return TutorSession.StartLessonResponse(generation=generation)

    async def start_replan(
        self,
        context: TransactionContext,
        request: TutorSession.StartReplanRequest,
    ) -> TutorSession.StartReplanResponse:
        self.state.generation += 1
        generation = self.state.generation
        self.state.status = "thinking"
        self.state.error_message = ""
        self.state.last_student_message = request.student_message.strip()
        await self._append_user_message(
            context,
            generation=generation,
            text=request.student_message.strip(),
            source_kind="text",
        )
        await self.ref().schedule().replan_lesson(
            context,
            student_message=request.student_message,
            completed_beat_index=request.completed_beat_index,
            source_media_type=request.source_media_type,
            source_base64=request.source_base64,
            generation=generation,
        )
        return TutorSession.StartReplanResponse(generation=generation)

    @classmethod
    async def prepare_lesson(
        cls,
        context: WorkflowContext,
        request: TutorSession.PrepareLessonRequest,
    ) -> None:
        question_text = request.question_text.strip()
        if not question_text and not request.source_base64:
            await cls._store_lesson_error(
                context,
                request.generation,
                "Paste a question or upload a clear screenshot/PDF page.",
                "Store empty question error",
            )
            return

        has_image = bool(request.source_base64)
        lesson_planner = planner_agent
        lesson_reviewer = vision_reviewer_agent if has_image else reviewer_agent
        if (
            lesson_planner is None
            or lesson_reviewer is None
            or (has_image and vision_diagram_agent is None)
        ):
            await cls._store_lesson_error(
                context,
                request.generation,
                vision_configuration_message() if has_image else llm_configuration_message(),
                "Store LLM configuration error",
            )
            return

        try:
            diagram_analysis: ImageQuestionAnalysis | None = None
            diagram_commands: list[dict[str, Any]] = []
            student_material = question_text
            if has_image:
                assert vision_diagram_agent is not None
                analysis_prompt = (
                    "Extract the complete SAT question and create a faithful enlarged semantic copy of any "
                    "diagram needed to solve it. Optional student context:\n"
                    f"{question_text or '[none]'}"
                )
                analysis_content = _source_content(
                    analysis_prompt,
                    request.source_media_type,
                    request.source_base64,
                )
                analyzed = await vision_diagram_agent.run(context, analysis_content)
                diagram_analysis = analyzed.output
                diagram_commands = _compile_diagram(diagram_analysis)
                student_material = (
                    f"{question_text}\n\nImage transcription:\n{diagram_analysis.extracted_question}"
                    if question_text
                    else diagram_analysis.extracted_question
                )

            prompt = (
                "Prepare a verified, visual SAT lesson for the following student submission.\n\n"
                f"Student material:\n{student_material}\n\n"
                f"Source kind: {request.source_kind or 'text'}\n\n"
                + (
                    "A trusted renderer will insert the enlarged diagram from this vision summary:\n"
                    f"{diagram_analysis.diagram_summary}\n"
                    "Do not emit space='diagram' commands, graph, bar_chart, or venn. Use concise flowing board "
                    "notes that teach from the reconstructed diagram."
                    if diagram_analysis and diagram_analysis.should_reconstruct
                    else ""
                )
            )
            planned = await lesson_planner.run(context, prompt)
            lesson = _inject_diagram(
                _normalize_lesson(
                    planned.output,
                    source_has_image=has_image,
                    question_text=student_material,
                ),
                diagram_commands,
            )
            review_prompt = (
                "Verify this proposed SAT lesson against the original submission.\n\n"
                f"Student material:\n{student_material}\n\n"
                f"Proposed lesson JSON:\n{lesson.model_dump_json()}"
            )
            review_content = _source_content(
                review_prompt,
                request.source_media_type,
                request.source_base64,
            )
            reviewed = await lesson_reviewer.run(context, review_content)
            review = reviewed.output
            if not review.approved:
                issue_text = "; ".join(review.issues[:3]) or "the solution could not be verified"
                logger.warning("Initial SAT lesson was rejected: %s", issue_text)
                if has_image and diagram_analysis and diagram_analysis.should_reconstruct:
                    assert vision_diagram_agent is not None
                    diagram_correction_prompt = (
                        "Correct this diagram extraction using every verifier issue. Return one clean replacement "
                        "ImageQuestionAnalysis with no duplicate geometry or IDs.\n\n"
                        f"Verifier issues:\n{issue_text}\n\n"
                        f"Prior analysis:\n{diagram_analysis.model_dump_json()}"
                    )
                    diagram_correction_content = _source_content(
                        diagram_correction_prompt,
                        request.source_media_type,
                        request.source_base64,
                    )
                    corrected_analysis = await vision_diagram_agent.run(
                        context,
                        diagram_correction_content,
                        variant="review-correction",
                    )
                    diagram_analysis = corrected_analysis.output
                    diagram_commands = _compile_diagram(diagram_analysis)
                    student_material = (
                        f"{question_text}\n\nImage transcription:\n{diagram_analysis.extracted_question}"
                        if question_text
                        else diagram_analysis.extracted_question
                    )
                correction_prompt = (
                    "Correct the proposed SAT lesson using every reviewer issue below. "
                    "Return a complete replacement LessonPlan and keep the correct final answer.\n\n"
                    f"Student material:\n{student_material}\n\n"
                    f"Reviewer issues:\n{issue_text}\n\n"
                    f"Rejected lesson JSON:\n{lesson.model_dump_json()}\n\n"
                    "Delete every visual command criticized by the reviewer unless you can correct it confidently. "
                    "Do not replace a rejected chart with decorative data or a chart of answer choices. A clear "
                    "equation and concise source annotation are better than an unrelated visualization.\n\n"
                    "The trusted renderer owns any image-derived diagram. Do not emit space='diagram', graph, "
                    "bar_chart, or venn commands; correct only the reasoning and flowing board notes."
                )
                corrected = await lesson_planner.run(
                    context,
                    correction_prompt,
                    variant="review-correction",
                )
                lesson = _inject_diagram(
                    _normalize_lesson(
                        corrected.output,
                        source_has_image=has_image,
                        question_text=student_material,
                    ),
                    diagram_commands,
                )
                corrected_review_prompt = (
                    "Verify this corrected SAT lesson against the original submission and the prior "
                    "review issues. Approve only if every issue is resolved.\n\n"
                    f"Student material:\n{student_material}\n\n"
                    f"Prior issues:\n{issue_text}\n\n"
                    f"Corrected lesson JSON:\n{lesson.model_dump_json()}"
                )
                corrected_review_content = _source_content(
                    corrected_review_prompt,
                    request.source_media_type,
                    request.source_base64,
                )
                corrected_reviewed = await lesson_reviewer.run(
                    context,
                    corrected_review_content,
                    variant="correction-review",
                )
                review = corrected_reviewed.output
                if not review.approved:
                    corrected_issue_text = (
                        "; ".join(review.issues[:3]) or "the corrected solution could not be verified"
                    )
                    logger.warning("Corrected SAT lesson was rejected: %s", corrected_issue_text)
                    await cls._store_lesson_error(
                        context,
                        request.generation,
                        "I couldn’t verify this explanation confidently. Try the question again or paste a little more context.",
                        "Store corrected verification failure",
                    )
                    return

            lesson_json = lesson.model_dump_json()

            async def store_lesson(state: Any) -> int:
                if state.generation != request.generation:
                    return -1
                state.lesson_json = lesson_json
                state.status = "ready"
                state.error_message = ""
                state.revision += 1
                return state.revision

            await TutorSession.ref().per_workflow("Store verified lesson").write(
                context,
                store_lesson,
            )
            await cls._append_assistant_message(
                context,
                request.generation,
                _assistant_message_text(lesson),
                lesson_json,
                "ready",
                "Append verified assistant reply",
            )
        except Exception as error:
            await cls._store_lesson_error(
                context,
                request.generation,
                _safe_error(error),
                "Store lesson generation error",
            )

    @classmethod
    async def replan_lesson(
        cls,
        context: WorkflowContext,
        request: TutorSession.ReplanLessonRequest,
    ) -> None:
        student_message = request.student_message.strip()
        if not student_message:
            await cls._store_lesson_error(
                context,
                request.generation,
                "Tell the tutor what is confusing or what you want explained differently.",
                "Store empty follow-up error",
            )
            return

        # The replan prompt must remain byte-for-byte stable across workflow
        # replay. A live read here would observe the replacement lesson after
        # we store it and turn the replay into a different model request.
        current = await TutorSession.ref().per_workflow(
            "Read original lesson for replan"
        ).read(context)
        if not current.lesson_json:
            await cls._store_lesson_error(
                context,
                request.generation,
                "Start a lesson before asking a follow-up.",
                "Store missing lesson error",
            )
            return
        has_image = current.source_kind == "image"
        lesson_replanner = replanner_agent
        if lesson_replanner is None:
            await cls._store_lesson_error(
                context,
                request.generation,
                llm_configuration_message(),
                "Store replanner configuration error",
            )
            return

        prompt = (
            f"Student interruption: {student_message}\n"
            f"Completed beat index: {request.completed_beat_index}\n"
            f"Original question: {current.question_text}\n"
            f"Current verified lesson: {current.lesson_json}\n"
            "Create a focused replacement explanation that directly resolves the interruption."
        )
        try:
            result = await lesson_replanner.run(context, prompt)
            lesson: LessonPlan = _normalize_lesson(
                result.output,
                source_has_image=has_image,
                question_text=current.question_text,
            )
            old_answer = LessonPlan.model_validate_json(current.lesson_json).final_answer
            if lesson.final_answer.strip() != old_answer.strip():
                await cls._store_lesson_error(
                    context,
                    request.generation,
                    "I stopped because the follow-up changed the verified answer. Please retry the original question.",
                    "Reject answer drift",
                )
                return

            lesson_json = lesson.model_dump_json()

            async def store_replanned_lesson(state: Any) -> int:
                if state.generation != request.generation:
                    return -1
                state.lesson_json = lesson_json
                state.status = "ready"
                state.error_message = ""
                state.revision += 1
                return state.revision

            await TutorSession.ref().per_workflow("Store replanned lesson").write(
                context,
                store_replanned_lesson,
            )
            await cls._append_assistant_message(
                context,
                request.generation,
                _assistant_message_text(lesson),
                lesson_json,
                "ready",
                "Append follow-up assistant reply",
            )
        except Exception as error:
            await cls._store_lesson_error(
                context,
                request.generation,
                _safe_error(error),
                "Store follow-up error",
            )

    async def request_voice_token(
        self,
        context: WriterContext,
    ) -> TutorSession.RequestVoiceTokenResponse:
        self.state.voice_generation += 1
        generation = self.state.voice_generation
        self.state.voice_status = "requesting"
        self.state.voice_error = ""
        self.state.voice_token_ciphertext_id = ""
        await self.ref().schedule().grant_voice_token(context, generation=generation)
        return TutorSession.RequestVoiceTokenResponse(generation=generation)

    @classmethod
    async def grant_voice_token(
        cls,
        context: WorkflowContext,
        request: TutorSession.GrantVoiceTokenRequest,
    ) -> None:
        api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        tts_model = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en").strip()
        if not api_key:
            await cls._store_voice_error(
                context,
                request.generation,
                "Add DEEPGRAM_API_KEY to the project .env file, then restart the backend.",
            )
            return

        async def grant_token() -> str:
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    response = await client.post(
                        "https://api.deepgram.com/v1/auth/grant",
                        headers={"Authorization": f"Token {api_key}"},
                        json={"ttl_seconds": 60},
                    )
                if response.status_code >= 400:
                    return json.dumps(
                        {"error": f"Deepgram token request failed ({response.status_code})"}
                    )
                return response.text
            except Exception as error:
                return json.dumps({"error": f"Could not contact Deepgram: {str(error)[:160]}"})

        payload_text = await at_least_once(
            "Grant temporary Deepgram token",
            context,
            grant_token,
        )
        payload = json.loads(payload_text)
        access_token = str(payload.get("access_token", ""))
        if not access_token:
            await cls._store_voice_error(
                context,
                request.generation,
                str(payload.get("error", "Deepgram did not return an access token")),
            )
            return

        try:
            ciphertext, _ = await Ciphertext.encrypt(
                context,
                plaintext=access_token.encode("utf-8"),
                associated_data=_voice_associated_data(context.state_id, request.generation),
                scope=f"voice-token:{context.state_id}:{request.generation}",
                key_manager_id=APP_SHARED_KEY_MANAGER_ID,
            )
        except Exception as error:
            await cls._store_voice_error(
                context,
                request.generation,
                f"Could not protect the temporary voice token: {str(error)[:160]}",
            )
            return
        ciphertext_id = ciphertext.state_id

        async def store_voice_token(state: Any) -> None:
            if state.voice_generation != request.generation:
                return
            state.voice_token_ciphertext_id = ciphertext_id
            state.voice_status = "ready"
            state.voice_error = ""
            state.tts_model = tts_model

        await TutorSession.ref().per_workflow("Store encrypted voice token").write(
            context,
            store_voice_token,
        )

    async def consume_voice_token(
        self,
        context: WriterContext,
        request: TutorSession.ConsumeVoiceTokenRequest,
    ) -> TutorSession.ConsumeVoiceTokenResponse:
        if request.generation != self.state.voice_generation:
            return TutorSession.ConsumeVoiceTokenResponse(
                ok=False,
                message="This voice token request was superseded.",
            )
        ciphertext_id = self.state.voice_token_ciphertext_id
        if self.state.voice_status != "ready" or not ciphertext_id:
            return TutorSession.ConsumeVoiceTokenResponse(
                ok=False,
                message=self.state.voice_error or "The temporary voice token is not ready.",
            )
        try:
            decrypted = await Ciphertext.ref(ciphertext_id).decrypt(
                context,
                associated_data=_voice_associated_data(
                    self.ref().state_id,
                    request.generation,
                ),
            )
        except Ciphertext.DecryptAborted:
            self.state.voice_status = "error"
            self.state.voice_error = "The temporary voice token could not be decrypted."
            return TutorSession.ConsumeVoiceTokenResponse(
                ok=False,
                message=self.state.voice_error,
            )
        self.state.voice_token_ciphertext_id = ""
        self.state.voice_status = "consumed"
        return TutorSession.ConsumeVoiceTokenResponse(
            ok=True,
            access_token=decrypted.plaintext.decode("utf-8"),
            expires_in=60,
            tts_model=self.state.tts_model,
            message="Voice ready",
        )

    @classmethod
    async def _append_assistant_message(
        cls,
        context: WorkflowContext,
        generation: int,
        text: str,
        lesson_json: str,
        status: str,
        alias: str,
    ) -> None:
        current = await TutorSession.ref().always().read(context)
        if current.generation != generation or not current.message_index_id:
            return
        message_id = _message_id(
            context.state_id,
            current.chat_revision,
            generation,
            "assistant",
        )
        await TutorMessage.ref(message_id).per_workflow(f"{alias} body").set(
            context,
            role="assistant",
            text=text,
            lesson_json=lesson_json,
            source_kind=current.source_kind,
            generation=generation,
            status=status,
        )
        await OrderedMap.ref(current.message_index_id).per_workflow(
            f"{alias} index"
        ).insert(
            context,
            key=_message_key(generation, "assistant"),
            bytes=message_id.encode("utf-8"),
        )

    @classmethod
    async def _store_lesson_error(
        cls,
        context: WorkflowContext,
        generation: int,
        message: str,
        alias: str,
    ) -> None:
        async def store_error(state: Any) -> None:
            if state.generation != generation:
                return
            state.status = "error"
            state.error_message = message

        await TutorSession.ref().per_workflow(alias).write(context, store_error)
        await cls._append_assistant_message(
            context,
            generation,
            message,
            "",
            "error",
            f"{alias} assistant reply",
        )

    @classmethod
    async def _store_voice_error(
        cls,
        context: WorkflowContext,
        generation: int,
        message: str,
    ) -> None:
        async def store_error(state: Any) -> None:
            if state.voice_generation != generation:
                return
            state.voice_status = "error"
            state.voice_error = message

        await TutorSession.ref().per_workflow("Store voice token error").write(
            context,
            store_error,
        )

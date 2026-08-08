import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from datetime import timedelta
import time
from typing import Any, Sequence, Union

import httpx
import rbt.v1alpha1.errors_pb2 as errors
from pydantic_ai import BinaryContent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import UserContent
from rbt.std.ciphertext.v1.ciphertext_rbt import Ciphertext
from reboot.aio.auth.authorizers import (
    Authorizer,
    AuthorizerRule,
    allow_if,
    is_app_internal,
)
from reboot.aio.contexts import ReaderContext, TransactionContext, WorkflowContext, WriterContext
from reboot.aio.workflows import at_least_once
from reboot.std.ciphertext.v1.ciphertext import (
    APP_SHARED_KEY_MANAGER_ID,
    KeyManager,
    make_associated_data,
)
from reboot.std.collections.ordered_map.v1.ordered_map import OrderedMap
from sat_tutor.v1.tutor import ChatMessage, TutorSessionState
from sat_tutor.v1.tutor_rbt import TutorMessage, TutorSession, UsageLedger

from observability import log_event, timed
from lesson_models import (
    HighlightCommand,
    ImageQuestionAnalysis,
    LessonPlan,
    SegmentCommand,
    TeachingBeat,
    TextCommand,
    WorkDiagnosis,
)
from tutor_agents import (
    diagnosis_reviewer_agent,
    diagnostician_agent,
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
# Erasure runs in one transaction, so it works in pages.
FORGET_PAGE = 100
# A lesson costs four to six provider calls, so an uncapped account is an
# uncapped bill. Deliberately generous: a real student doing a full practice
# set stays well under, and only a runaway loop notices.
DAILY_LESSON_LIMIT = int(os.environ.get("DAILY_LESSON_LIMIT", "40"))
DAILY_CHECK_LIMIT = int(os.environ.get("DAILY_CHECK_LIMIT", "80"))
BURST_LIMIT = int(os.environ.get("BURST_LIMIT", "8"))
BURST_WINDOW = timedelta(minutes=1)
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


# Statuses worth trying again: rate limits, timeouts, and anything the
# provider says is its own fault.
RETRYABLE_STATUSES = {408, 409, 425, 429}


def _is_transient(error: Exception) -> bool:
    """
    Is this the provider having a bad minute, or the request being wrong?

    Reboot already retries: a workflow step that raises is replayed, and every
    completed step returns its memoized result instead of re-running. Catching
    everything defeated that and turned a passing 503 into a dead lesson. Only
    permanent failures should reach the student.
    """
    if isinstance(error, ModelHTTPError):
        return error.status_code in RETRYABLE_STATUSES or error.status_code >= 500
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    # ModelAPIError that is not an HTTP error means the request never landed.
    return isinstance(error, ModelAPIError)


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


def _note(index: int, text: str, *, color: str = "#1769e0") -> TextCommand:
    return TextCommand(
        id=f"work-note-{index}",
        kind="text",
        space="board",
        layout="flow",
        text=text[:240],
        color=color,
        size=0.05,
    )


def _beat(
    identifier: str,
    goal: str,
    spoken: str,
    caption: str,
    strategy: str,
    commands: list[Any],
) -> TeachingBeat:
    return TeachingBeat(
        id=identifier,
        teaching_goal=goal[:180],
        spoken_text=(spoken or goal)[:900],
        caption=caption[:220],
        strategy=strategy[:80],
        commands=commands,
    )


def _explanation(text: str, fallback: str) -> str:
    """
    `answer_explanation` needs 5 characters; `misconception` has no minimum.
    A model answering "N/A" is truthy but too short, which failed validation
    and lost the whole diagnosis after it had already been verified.
    """
    cleaned = text.strip()
    return cleaned if len(cleaned) >= 5 else fallback


def _diagnosis_to_lesson(diagnosis: WorkDiagnosis, question_text: str) -> LessonPlan:
    """
    Turn a verified diagnosis into board work.

    Deterministic on purpose: asking a second model to dress the verdict up as
    a lesson would give it a chance to contradict the verdict that was just
    verified.
    """
    summary = (question_text.strip() or "The student's submitted working")[:600]
    steps = [step.strip() for step in diagnosis.restated_steps if step.strip()]

    if diagnosis.verdict == "correct":
        confirmed: list[Any] = [
            _note(index, f"{index + 1}. {step}") for index, step in enumerate(steps[:6])
        ]
        return LessonPlan(
            domain="math",
            question_summary=summary,
            final_answer=diagnosis.correct_answer,
            answer_explanation=_explanation(
                diagnosis.misconception, "Every step in the submitted work is correct."
            ),
            confidence=diagnosis.confidence,
            beats=[
                _beat(
                    "work:confirm",
                    "Confirm the work is correct",
                    "I checked every step, and this is right. Let me show you what you did well.",
                    "Your work checks out",
                    "confirm",
                    confirmed or [_note(0, "Your working is correct.")],
                ),
                _beat(
                    "work:answer",
                    "State the verified answer",
                    f"Your answer, {diagnosis.correct_answer}, is the one I get too. {diagnosis.next_hint}",
                    f"Answer: {diagnosis.correct_answer}",
                    "confirm",
                    [_note(90, f"Answer: {diagnosis.correct_answer}", color="#1a7f37")],
                ),
            ],
        )

    if diagnosis.verdict == "unclear":
        return LessonPlan(
            domain="math",
            question_summary=summary,
            final_answer="I need one more detail before I can check this.",
            answer_explanation=_explanation(
                diagnosis.misconception, "The submitted work could not be read confidently."
            ),
            confidence=diagnosis.confidence,
            beats=[
                _beat(
                    "work:unclear",
                    "Say honestly that the work cannot be judged yet",
                    "I don't want to guess and tell you something wrong, so let me ask first.",
                    "I want to make sure I'm following you",
                    "clarify",
                    [_note(0, "I couldn't follow every step here.")],
                ),
                _beat(
                    "work:ask",
                    "Ask the question that would settle it",
                    diagnosis.next_hint,
                    diagnosis.next_hint[:220],
                    "clarify",
                    [_note(1, diagnosis.next_hint, color="#b26a00")],
                ),
            ],
        )

    error_index = diagnosis.first_error_step - 1
    recap: list[Any] = []
    for index, step in enumerate(steps[:6]):
        correct_so_far = index < error_index
        recap.append(
            _note(
                index,
                f"{index + 1}. {step}",
                color="#1a7f37" if correct_so_far else ("#d93025" if index == error_index else "#5f6b76"),
            )
        )
    if error_index < len(recap):
        recap.append(
            HighlightCommand(
                id="work-error-highlight",
                kind="highlight",
                space="board",
                target_id=f"work-note-{error_index}",
            )
        )

    good_steps = error_index
    if good_steps == 0:
        opening = "Let's look at the very first step together."
    elif good_steps == 1:
        opening = "The first step is right — the break comes after that."
    else:
        opening = f"The first {good_steps} steps are right — the break comes after that."
    return LessonPlan(
        domain="math",
        question_summary=summary,
        final_answer=diagnosis.correct_answer,
        answer_explanation=_explanation(
            diagnosis.misconception, "The submitted work goes wrong at the marked step."
        ),
        confidence=diagnosis.confidence,
        beats=[
            _beat(
                "work:recap",
                "Show the student their own steps",
                f"Here's what you did. {opening}",
                "Here's your working",
                "diagnose",
                recap or [_note(0, "I read through your working.")],
            ),
            _beat(
                "work:error",
                "Point at the first step that breaks",
                f"Step {diagnosis.first_error_step} is where it goes wrong. {diagnosis.misconception}",
                f"Step {diagnosis.first_error_step} is the first slip",
                "diagnose",
                [_note(80, f"Step {diagnosis.first_error_step}: {diagnosis.error_quote}"[:240], color="#d93025")],
            ),
            _beat(
                "work:hint",
                "Hand back the next move without solving it",
                diagnosis.next_hint,
                "Try this next",
                "hint",
                [_note(81, diagnosis.next_hint, color="#b26a00")],
            ),
        ],
    )


def _voice_scope(session_id: str) -> str:
    """Crypto-shredding is per scope, so keep it per session, not per token."""
    return f"voice-token:{session_id}"


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


def _is_session_owner(
    *,
    context: ReaderContext,
    state: TutorSessionState | None = None,
    **kwargs: Any,
) -> Authorizer.Decision:
    """
    A session belongs to one account.

    The session id is a random value the browser chose, so "is the caller
    signed in" is not a boundary — it lets any signed-in account read any
    session whose id it learns. An unclaimed session is still open, because
    `ensure` has to be able to stamp it; from then on it is that account's.
    """
    if context.auth is None or not context.auth.user_id:
        return errors.Unauthenticated()
    # `state` is None while the actor is still being constructed, which is
    # exactly the `ensure` call that claims it — denying that locks every
    # student out of their own first session.
    if state is None or not state.owner_id:
        return errors.Ok()
    if state.owner_id == context.auth.user_id:
        return errors.Ok()
    return errors.PermissionDenied()


def _session_access() -> AuthorizerRule[TutorSessionState, Any]:
    # Scheduled lesson, replan, and voice workflows re-enter this actor as
    # app-internal calls and carry no end-user identity.
    return allow_if(any=[_is_session_owner, is_app_internal])


class UsageLedgerServicer(UsageLedger.Servicer):
    """
    One ledger per account, capping how much provider spend it can cause.

    Counters are reset by scheduled calls rather than by reading the clock:
    a writer that consults wall time produces a different result when Reboot
    re-runs it to validate effects. `schedule(when=...)` is persisted, so the
    resets survive a restart.
    """

    def authorizer(self):
        return allow_if(all=[is_app_internal])

    async def consume(
        self,
        context: WriterContext,
        request: UsageLedger.ConsumeRequest,
    ) -> UsageLedger.ConsumeResponse:
        is_check = request.kind == "check"
        used = self.state.checks_today if is_check else self.state.lessons_today
        limit = DAILY_CHECK_LIMIT if is_check else DAILY_LESSON_LIMIT

        if self.state.recent_calls >= BURST_LIMIT:
            return UsageLedger.ConsumeResponse(
                allowed=False,
                message="That is a lot of requests at once. Give me a minute to catch up.",
            )
        if used >= limit:
            noun = "work checks" if is_check else "lessons"
            return UsageLedger.ConsumeResponse(
                allowed=False,
                message=f"You have used today's {noun}. This resets in a day.",
            )

        if is_check:
            self.state.checks_today += 1
        else:
            self.state.lessons_today += 1
        self.state.recent_calls += 1

        if not self.state.day_reset_scheduled:
            self.state.day_reset_scheduled = True
            await self.ref().schedule(when=timedelta(days=1)).reset_day(context)
        if not self.state.window_reset_scheduled:
            self.state.window_reset_scheduled = True
            await self.ref().schedule(when=BURST_WINDOW).reset_window(context)

        return UsageLedger.ConsumeResponse(allowed=True)

    async def reset_day(self, context: WriterContext) -> None:
        self.state.lessons_today = 0
        self.state.checks_today = 0
        self.state.day_reset_scheduled = False

    async def reset_window(self, context: WriterContext) -> None:
        self.state.recent_calls = 0
        self.state.window_reset_scheduled = False

    async def snapshot(self, context: ReaderContext) -> UsageLedger.SnapshotResponse:
        return UsageLedger.SnapshotResponse(
            lessons_today=self.state.lessons_today,
            checks_today=self.state.checks_today,
            recent_calls=self.state.recent_calls,
        )


class TutorMessageServicer(TutorMessage.Servicer):
    def authorizer(self):
        # Browsers never address a message directly; they read the thread
        # through `TutorSession.messages`, which is itself owner-gated.
        return allow_if(all=[is_app_internal])

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
        return _session_access()

    async def ensure(self, context: WriterContext) -> None:
        # Claim the session for whoever is signed in. Every later call is
        # checked against this, so an id leaking to another account is no
        # longer enough to read the student's lessons.
        if not self.state.owner_id and context.auth is not None and context.auth.user_id:
            self.state.owner_id = context.auth.user_id
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

    async def forget(
        self,
        context: TransactionContext,
    ) -> TutorSession.ForgetResponse:
        """
        Erase everything this session holds about the student.

        Blanking is the honest part: questions, working, and lessons live in
        plain actor state, so they have to be overwritten rather than merely
        unlinked. The crypto-shred then makes any encrypted remnant — voice
        tokens sealed under this session's scope — permanently undecryptable,
        even with database and root-key access.
        """
        erased = 0
        more = False
        if self.state.message_index_id and self.state.message_count:
            page = await OrderedMap.ref(self.state.message_index_id).range(
                context,
                start_key="",
                limit=FORGET_PAGE,
            )
            for entry in page.entries:
                await TutorMessage.ref(entry.bytes.decode("utf-8")).set(
                    context,
                    role="",
                    text="",
                    lesson_json="",
                    source_kind="",
                    generation=0,
                    status="erased",
                )
                erased += 1
            more = len(page.entries) == FORGET_PAGE

        await KeyManager.ref(APP_SHARED_KEY_MANAGER_ID).shred(
            context,
            scope=_voice_scope(self.ref().state_id),
        )

        self.state.question_text = ""
        self.state.source_kind = ""
        self.state.lesson_json = ""
        self.state.status = ""
        self.state.error_message = ""
        self.state.last_student_message = ""
        self.state.voice_token_ciphertext_id = ""
        self.state.voice_status = ""
        self.state.voice_error = ""
        self.state.tts_model = ""
        self.state.generation += 1
        self.state.voice_generation += 1
        if not more:
            # A fresh index; the blanked messages are no longer reachable.
            self.state.chat_revision += 1
            self.state.message_count = 0
            self.state.message_index_id = _message_index_id(
                self.ref().state_id,
                self.state.chat_revision,
            )

        log_event(
            "account.forgotten",
            session=self.ref().state_id,
            messages_erased=erased,
            more_remaining=more,
        )
        return TutorSession.ForgetResponse(messages_erased=erased, more_remaining=more)

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

    async def _within_limits(
        self,
        context: TransactionContext,
        kind: str,
    ) -> str:
        """Charge this request to the account, or say why it cannot run."""
        # Sessions predating ownership have no account, so fall back to the
        # session itself — an uncapped path is worse than a coarse one.
        account = self.state.owner_id or f"session:{self.ref().state_id}"
        allowance = await UsageLedger.ref(account).consume(context, kind=kind)
        if not allowance.allowed:
            log_event("usage.refused", session=self.ref().state_id, kind=kind)
        return "" if allowance.allowed else allowance.message

    async def _refuse(
        self,
        context: TransactionContext,
        message: str,
    ) -> int:
        """Report a refusal through the same path the student already knows."""
        self.state.generation += 1
        self.state.status = "error"
        self.state.error_message = message
        return self.state.generation

    async def start_lesson(
        self,
        context: TransactionContext,
        request: TutorSession.StartLessonRequest,
    ) -> TutorSession.StartLessonResponse:
        refusal = await self._within_limits(context, "lesson")
        if refusal:
            return TutorSession.StartLessonResponse(
                generation=await self._refuse(context, refusal)
            )
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
        refusal = await self._within_limits(context, "lesson")
        if refusal:
            return TutorSession.StartReplanResponse(
                generation=await self._refuse(context, refusal)
            )
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

    async def check_work(
        self,
        context: TransactionContext,
        request: TutorSession.CheckWorkRequest,
    ) -> TutorSession.CheckWorkResponse:
        refusal = await self._within_limits(context, "check")
        if refusal:
            return TutorSession.CheckWorkResponse(
                generation=await self._refuse(context, refusal)
            )
        self.state.generation += 1
        generation = self.state.generation
        self.state.status = "thinking"
        self.state.error_message = ""
        self.state.last_student_message = request.student_work.strip()[:400]
        await self._append_user_message(
            context,
            generation=generation,
            text=f"Here's my working:\n\n{request.student_work.strip()}",
            source_kind="work",
        )
        await self.ref().schedule().review_work(
            context,
            student_work=request.student_work,
            question_text=request.question_text,
            generation=generation,
        )
        return TutorSession.CheckWorkResponse(generation=generation)

    @classmethod
    async def review_work(
        cls,
        context: WorkflowContext,
        request: TutorSession.ReviewWorkRequest,
    ) -> None:
        started = time.monotonic()
        student_work = request.student_work.strip()
        if not student_work:
            await cls._store_lesson_error(
                context,
                request.generation,
                "Type the steps you tried and I'll check them.",
                "Store empty work error",
            )
            return

        diagnostician = diagnostician_agent
        diagnosis_reviewer = diagnosis_reviewer_agent
        if diagnostician is None or diagnosis_reviewer is None:
            await cls._store_lesson_error(
                context,
                request.generation,
                llm_configuration_message(),
                "Store diagnostician configuration error",
            )
            return

        # Read once, memoized, so a replay builds the identical prompt.
        current = await TutorSession.ref().per_workflow("Read question for work check").read(context)
        # Working submitted with its own question wins: the session may still
        # be sitting on an unrelated lesson from earlier in the conversation.
        question_text = (
            request.question_text.strip()
            or current.question_text.strip()
            or "The student did not paste the original question."
        )

        try:
            prompt = (
                "Diagnose this student's own working.\n\n"
                f"Question:\n{question_text}\n\n"
                f"Student's work:\n{student_work}"
            )
            diagnosed = await diagnostician.run(context, prompt)
            diagnosis: WorkDiagnosis = diagnosed.output

            review_prompt = (
                "Verify this diagnosis of the student's work.\n\n"
                f"Question:\n{question_text}\n\n"
                f"Student's work:\n{student_work}\n\n"
                f"Proposed diagnosis JSON:\n{diagnosis.model_dump_json()}"
            )
            reviewed = await diagnosis_reviewer.run(context, review_prompt)
            if not reviewed.output.approved:
                issues = "; ".join(reviewed.output.issues[:3]) or "the diagnosis could not be verified"
                logger.warning("Initial work diagnosis was rejected: %s", issues)
                corrected = await diagnostician.run(
                    context,
                    (
                        "Your diagnosis was rejected by an independent verifier. Produce one corrected "
                        "replacement diagnosis that resolves every issue. If the issues show you wrongly "
                        "flagged a correct step, return verdict='correct'. If you cannot judge the work "
                        "confidently, return verdict='unclear'.\n\n"
                        f"Question:\n{question_text}\n\n"
                        f"Student's work:\n{student_work}\n\n"
                        f"Verifier issues:\n{issues}\n\n"
                        f"Rejected diagnosis:\n{diagnosis.model_dump_json()}"
                    ),
                    variant="diagnosis-correction",
                )
                diagnosis = corrected.output
                rereviewed = await diagnosis_reviewer.run(
                    context,
                    (
                        "Verify this corrected diagnosis. Approve only if every prior issue is resolved.\n\n"
                        f"Question:\n{question_text}\n\n"
                        f"Student's work:\n{student_work}\n\n"
                        f"Prior issues:\n{issues}\n\n"
                        f"Corrected diagnosis JSON:\n{diagnosis.model_dump_json()}"
                    ),
                    variant="diagnosis-correction-review",
                )
                if not rereviewed.output.approved:
                    logger.warning(
                        "Corrected work diagnosis was rejected: %s",
                        "; ".join(rereviewed.output.issues[:3]),
                    )
                    # Never fall back to asserting an unverified verdict: a
                    # wrong "you made a mistake" costs more than no feedback.
                    log_event(
                        "work.withheld",
                        session=context.state_id,
                        generation=request.generation,
                        reason="unverified-after-correction",
                    )
                    await cls._store_lesson_error(
                        context,
                        request.generation,
                        "I couldn’t check this confidently enough to tell you where it goes wrong. "
                        "Paste the original question with your steps and I’ll try again.",
                        "Store unverified diagnosis",
                    )
                    return

            lesson = _normalize_lesson(
                _diagnosis_to_lesson(diagnosis, current.question_text),
                question_text=current.question_text,
            )
            lesson_json = lesson.model_dump_json()

            async def store_diagnosis(state: Any) -> None:
                if state.generation != request.generation:
                    return
                state.lesson_json = lesson_json
                state.status = "ready"
                state.error_message = ""
                state.revision += 1

            log_event(
                "work.diagnosed",
                session=context.state_id,
                generation=request.generation,
                ms=round((time.monotonic() - started) * 1000),
                verdict=diagnosis.verdict,
                error_step=diagnosis.first_error_step,
                confidence=round(diagnosis.confidence, 2),
                steps=len(diagnosis.restated_steps),
            )
            await TutorSession.ref().per_workflow("Store verified diagnosis").write(
                context,
                store_diagnosis,
            )
            await cls._append_assistant_message(
                context,
                request.generation,
                _assistant_message_text(lesson),
                lesson_json,
                "ready",
                "Append work diagnosis reply",
            )
        except Exception as error:
            if _is_transient(error):
                # Let it out: Reboot replays the workflow and the completed
                # steps return memoized results, so only this call runs again.
                log_event(
                    "provider.transient",
                    session=context.state_id,
                    generation=request.generation,
                    stage="diagnosis",
                    error=type(error).__name__,
                )
                raise
            await cls._store_lesson_error(
                context,
                request.generation,
                _safe_error(error),
                "Store work diagnosis error",
            )

    @classmethod
    async def prepare_lesson(
        cls,
        context: WorkflowContext,
        request: TutorSession.PrepareLessonRequest,
    ) -> None:
        started = time.monotonic()
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
                    planned.output.to_plan(),
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
            corrected_once = not review.approved
            if not review.approved:
                issue_text = "; ".join(review.issues[:3]) or "the solution could not be verified"
                logger.warning("Initial SAT lesson was rejected: %s", issue_text)
                log_event(
                    "lesson.rejected",
                    session=context.state_id,
                    generation=request.generation,
                    pass_number=1,
                )
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
                    "Return a complete replacement lesson and keep the correct final answer.\n\n"
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
                        corrected.output.to_plan(),
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

            log_event(
                "lesson.prepared",
                session=context.state_id,
                generation=request.generation,
                source=request.source_kind or "text",
                ms=round((time.monotonic() - started) * 1000),
                beats=len(lesson.beats),
                commands=sum(len(beat.commands) for beat in lesson.beats),
                corrected=corrected_once,
            )
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
            if _is_transient(error):
                # Let it out: Reboot replays the workflow and the completed
                # steps return memoized results, so only this call runs again.
                log_event(
                    "provider.transient",
                    session=context.state_id,
                    generation=request.generation,
                    stage="lesson",
                    error=type(error).__name__,
                )
                raise
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
                result.output.to_plan(),
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
            if _is_transient(error):
                # Let it out: Reboot replays the workflow and the completed
                # steps return memoized results, so only this call runs again.
                log_event(
                    "provider.transient",
                    session=context.state_id,
                    generation=request.generation,
                    stage="replan",
                    error=type(error).__name__,
                )
                raise
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
                scope=_voice_scope(context.state_id),
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

        log_event(
            "student.error",
            session=context.state_id,
            generation=generation,
            stage=alias,
        )
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

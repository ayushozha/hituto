import asyncio
import unittest
from typing import Any

from reboot.aio.applications import Application
from reboot.aio.contexts import WorkflowContext
from reboot.aio.tests import Reboot
from reboot.std.ciphertext.v1.ciphertext import ciphertext_library
from reboot.std.collections.ordered_map.v1.ordered_map import ordered_map_library
from sat_tutor.v1.tutor_rbt import TutorMessage, TutorSession, UsageLedger

from lesson_models import (
    HighlightCommand,
    ImageQuestionAnalysis,
    LessonPlan,
    TextCommand,
    WorkDiagnosis,
)
import tutor_servicer
from tutor_servicer import (
    TutorMessageServicer,
    TutorSessionServicer,
    UsageLedgerServicer,
    _assistant_message_text,
    _compile_diagram,
    _diagnosis_to_lesson,
    _inject_diagram,
    _normalize_lesson,
)


def _lesson(*, follow_up: bool = False) -> LessonPlan:
    return LessonPlan.model_validate(
        {
            "domain": "math",
            "question_summary": "Find the vertex of a quadratic graph.",
            "final_answer": "A) (2, -1)",
            "answer_explanation": "Completing the square gives a vertex at (2, -1).",
            "confidence": 0.99,
            "beats": [
                {
                    "id": "beat:one",
                    "teaching_goal": "Show the key representation",
                    "spoken_text": "Let’s look at the same idea in a different way." if follow_up else "First, rewrite the quadratic in vertex form.",
                    "caption": "A different visual explanation" if follow_up else "Rewrite in vertex form",
                    "strategy": "visual" if follow_up else "algebra",
                    "commands": [
                        {
                            "id": "note:form",
                            "kind": "math",
                            "layout": "flow",
                            "text": "y=(x-2)^2-1",
                        }
                    ],
                    "pause_after_ms": 0,
                    "checkpoint": False,
                },
                {
                    "id": "beat:two",
                    "teaching_goal": "Connect the equation to the graph",
                    "spoken_text": "The graph bottoms out at two, negative one.",
                    "caption": "Mark the vertex",
                    "strategy": "graph",
                    "commands": [
                        {
                            "id": "graph:quadratic",
                            "kind": "graph",
                            "curves": [{"id": "curve", "formula": "(x-2)^2-1"}],
                            "markers": [{"id": "vertex", "x": 2, "y": -1, "label": "(2, -1)"}],
                            "x_min": -1,
                            "x_max": 5,
                            "y_min": -2,
                            "y_max": 8,
                        }
                    ],
                    "pause_after_ms": 0,
                    "checkpoint": False,
                },
            ],
        }
    )


class DeterministicTutorSessionServicer(TutorSessionServicer):
    @classmethod
    async def _store_ready_lesson(
        cls,
        context: WorkflowContext,
        generation: int,
        lesson: LessonPlan,
        alias: str,
    ) -> None:
        lesson_json = lesson.model_dump_json()

        async def store(state: Any) -> None:
            if state.generation != generation:
                return
            state.lesson_json = lesson_json
            state.status = "ready"
            state.error_message = ""
            state.revision += 1

        await TutorSession.ref().per_workflow(alias).write(context, store)
        await cls._append_assistant_message(
            context,
            generation,
            _assistant_message_text(lesson),
            lesson_json,
            "ready",
            f"{alias} assistant reply",
        )

    @classmethod
    async def prepare_lesson(
        cls,
        context: WorkflowContext,
        request: TutorSession.PrepareLessonRequest,
    ) -> None:
        await cls._store_ready_lesson(context, request.generation, _lesson(), "Store deterministic lesson")

    @classmethod
    async def replan_lesson(
        cls,
        context: WorkflowContext,
        request: TutorSession.ReplanLessonRequest,
    ) -> None:
        await cls._store_ready_lesson(context, request.generation, _lesson(follow_up=True), "Store deterministic follow-up")


class TestTutorSession(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.rbt = Reboot()
        await self.rbt.start()
        await self.rbt.up(
            Application(
                servicers=[
                    DeterministicTutorSessionServicer,
                    TutorMessageServicer,
                    UsageLedgerServicer,
                ],
                # Same libraries main.py registers: `forget` crypto-shreds,
                # which needs the KeyManager from the ciphertext library.
                libraries=[ciphertext_library(), ordered_map_library()],
            )
        )
        self.context = await self.rbt.create_external_context_as(
            name=f"test-{self.id()}",
            user_id=f"student-{self.id()}",
        )
        self.session_id = f"session-{self.id()}"
        self.session = TutorSession.ref(self.session_id)
        await self.session.ensure(self.context)

    async def asyncTearDown(self) -> None:
        await self.rbt.stop()

    async def _ready_snapshot(self, generation: int) -> TutorSession.SnapshotResponse:
        updates = self.session.reactively().snapshot(self.context)
        while True:
            snapshot = await asyncio.wait_for(anext(updates), timeout=10)
            if snapshot.generation == generation and snapshot.status in {"ready", "error"}:
                return snapshot

    async def test_a_runaway_account_is_capped_without_an_error_page(self) -> None:
        # Spend the allowance directly rather than by running real lessons:
        # eight lessons take longer than the burst window, so the window would
        # reset mid-test and the assertion would depend on the clock.
        internal = self.rbt.create_external_context(
            name=f"internal-{self.id()}", app_internal=True
        )
        ledger = UsageLedger.ref(f"student-{self.id()}")
        for _ in range(tutor_servicer.BURST_LIMIT):
            await ledger.consume(internal, kind="lesson")

        blocked = await self.session.start_lesson(
            self.context, question_text="What is 2 + 2?", source_kind="text"
        )
        snapshot = await self.session.snapshot(self.context)

        # Refused through the status the student already understands, not an
        # exception that would surface as a broken page.
        self.assertEqual(snapshot.status, "error")
        self.assertIn("minute", snapshot.error_message)
        self.assertEqual(snapshot.generation, blocked.generation)

    async def test_work_checks_and_lessons_have_separate_allowances(self) -> None:
        # The ledger is app-internal only: a student must not be able to read
        # or spend their own allowance directly.
        internal = self.rbt.create_external_context(
            name=f"internal-{self.id()}", app_internal=True
        )
        ledger = UsageLedger.ref(f"student-{self.id()}")
        for _ in range(3):
            await ledger.consume(internal, kind="check")

        usage = await ledger.snapshot(internal)

        self.assertEqual(usage.checks_today, 3)
        self.assertEqual(usage.lessons_today, 0)

    async def test_forget_erases_the_student_content(self) -> None:
        started = await self.session.start_lesson(
            self.context,
            question_text="For y=x^2-4x+3, what is the vertex?",
            source_kind="text",
        )
        await self._ready_snapshot(started.generation)
        before = await self.session.messages(self.context, cursor="", limit=20)
        self.assertTrue(any(message.text for message in before.messages))

        erasure = await self.session.forget(self.context)
        after = await self.session.snapshot(self.context)
        remaining = await self.session.messages(self.context, cursor="", limit=20)

        self.assertGreater(erasure.messages_erased, 0)
        # Content is overwritten, not merely unlinked.
        self.assertEqual(after.question_text, "")
        self.assertEqual(after.lesson_json, "")
        self.assertEqual(after.last_student_message, "")
        self.assertEqual(remaining.messages, [])

    async def test_forget_leaves_nothing_readable_behind(self) -> None:
        started = await self.session.start_lesson(
            self.context,
            question_text="A private question about my own weak spots",
            source_kind="text",
        )
        await self._ready_snapshot(started.generation)
        before = await self.session.messages(self.context, cursor="", limit=20)
        message_ids = [message.id for message in before.messages]

        await self.session.forget(self.context)

        # Addressing an erased message directly must not resurrect its text.
        internal = self.rbt.create_external_context(
            name=f"internal-{self.id()}", app_internal=True
        )
        for message_id in message_ids:
            snapshot = await TutorMessage.ref(message_id).snapshot(internal)
            self.assertEqual(snapshot.text, "")
            self.assertEqual(snapshot.lesson_json, "")
            self.assertEqual(snapshot.status, "erased")

    async def test_another_account_cannot_read_or_write_this_session(self) -> None:
        await self.session.start_lesson(
            self.context,
            question_text="For y=x^2-4x+3, what is the vertex?",
            source_kind="text",
        )
        intruder = await self.rbt.create_external_context_as(
            name=f"intruder-{self.id()}",
            user_id=f"intruder-{self.id()}",
        )
        # A ref belongs to the context that first used it, so the intruder
        # needs its own — same session id, different caller.
        as_intruder = TutorSession.ref(self.session_id)

        # The session id is a random browser value, so knowing it must not be
        # enough — the caller has to be the account that claimed it.
        with self.assertRaises(TutorSession.SnapshotAborted):
            await as_intruder.snapshot(intruder)
        with self.assertRaises(TutorSession.MessagesAborted):
            await as_intruder.messages(intruder, cursor="", limit=20)
        with self.assertRaises(TutorSession.ResetAborted):
            await as_intruder.reset(intruder)

        # The owner is unaffected.
        snapshot = await self.session.snapshot(self.context)
        self.assertEqual(snapshot.question_text, "For y=x^2-4x+3, what is the vertex?")

    async def test_the_first_signed_in_caller_claims_the_session(self) -> None:
        session_id = f"unclaimed-{self.id()}"
        await TutorSession.ref(session_id).ensure(self.context)

        stranger = await self.rbt.create_external_context_as(
            name=f"stranger-{self.id()}",
            user_id=f"stranger-{self.id()}",
        )
        with self.assertRaises(TutorSession.SnapshotAborted):
            await TutorSession.ref(session_id).snapshot(stranger)

    async def test_student_starts_a_visual_lesson_and_sees_verified_state(self) -> None:
        started = await self.session.start_lesson(
            self.context,
            question_text="For y=x^2-4x+3, what is the vertex? A) (2,-1) B) (-2,-1)",
            source_kind="text",
        )
        snapshot = await self._ready_snapshot(started.generation)
        lesson = LessonPlan.model_validate_json(snapshot.lesson_json)

        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(lesson.final_answer, "A) (2, -1)")
        graph = lesson.beats[1].commands[0]
        self.assertEqual(graph.kind, "graph")
        assert graph.kind == "graph"
        self.assertEqual((graph.markers[0].x, graph.markers[0].y), (2, -1))

    async def test_student_interrupts_and_receives_a_replacement_explanation(self) -> None:
        started = await self.session.start_lesson(
            self.context,
            question_text="For y=x^2-4x+3, what is the vertex?",
            source_kind="text",
        )
        await self._ready_snapshot(started.generation)

        replanned = await self.session.start_replan(
            self.context,
            student_message="I’m confused. Show me visually.",
            completed_beat_index=0,
        )
        snapshot = await self._ready_snapshot(replanned.generation)
        lesson = LessonPlan.model_validate_json(snapshot.lesson_json)

        self.assertEqual(snapshot.last_student_message, "I’m confused. Show me visually.")
        self.assertEqual(lesson.final_answer, "A) (2, -1)")
        self.assertEqual(lesson.beats[0].caption, "A different visual explanation")

        conversation = await self.session.messages(self.context, cursor="", limit=20)
        self.assertEqual([message.role for message in conversation.messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual(conversation.messages[2].text, "I’m confused. Show me visually.")
        self.assertTrue(conversation.messages[3].lesson_json)
        self.assertIn("same idea in a different way", conversation.messages[3].text)
        self.assertNotEqual(conversation.messages[1].text, conversation.messages[3].text)

    async def test_student_uploads_an_image_question(self) -> None:
        started = await self.session.start_lesson(
            self.context,
            question_text="",
            source_kind="image",
            source_media_type="image/png",
            source_base64="iVBORw0KGgo=",
        )
        snapshot = await self._ready_snapshot(started.generation)

        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(snapshot.source_kind, "image")
        self.assertTrue(snapshot.lesson_json)

    def test_image_lesson_compiles_one_trusted_enlarged_reconstruction(self) -> None:
        payload = _lesson().model_dump(mode="json")
        payload["beats"][0]["commands"].extend(
            [
                {"id": "line:one", "kind": "line", "space": "diagram", "x": 0.1, "y": 0.2, "x2": 0.8, "y2": 0.2},
                {"id": "line:two", "kind": "line", "space": "diagram", "x": 0.1, "y": 0.2, "x2": 0.8, "y2": 0.2},
                {"id": "source:focus", "kind": "highlight", "space": "source", "target_id": "", "x": 0.1, "y": 0.2, "width": 0.4, "height": 0.2},
                {"id": "chart:bad", "kind": "bar_chart", "bars": [{"label": "DC", "value": 6}, {"label": "DC", "value": 6}]},
                {"id": "clear:bad", "kind": "clear"},
            ]
        )
        normalized = _normalize_lesson(
            LessonPlan.model_validate(payload),
            source_has_image=True,
        )
        analysis = ImageQuestionAnalysis.model_validate(
            {
                "extracted_question": "Square ABCD has side 6. Find the area of triangle ECD.",
                "diagram_summary": "A square with E at the midpoint of AB and triangle ECD.",
                "should_reconstruct": True,
                "rects": [
                    {
                        "id": "square",
                        "x": 0.1,
                        "y": 0.1,
                        "width": 0.8,
                        "height": 0.8,
                        "preserve_aspect": True,
                    }
                ],
                "polylines": [
                    {
                        "id": "triangle",
                        "points": [
                            {"x": 0.5, "y": 0.1},
                            {"x": 0.9, "y": 0.9},
                            {"x": 0.1, "y": 0.9},
                            {"x": 0.5, "y": 0.1},
                        ],
                    }
                ],
                "labels": [
                    {"id": "A", "text": "A", "x": 0.06, "y": 0.06},
                    {"id": "E", "text": "E", "x": 0.48, "y": 0.04},
                    {"id": "six", "text": "6", "x": 0.48, "y": 0.92},
                ],
            }
        )
        lesson = _inject_diagram(normalized, _compile_diagram(analysis))
        commands = lesson.beats[0].commands

        self.assertTrue(any(command.id == "rebuild:rect:square" for command in commands))
        self.assertTrue(any(command.id == "rebuild:polyline:triangle" for command in commands))
        self.assertTrue(any(command.id == "rebuild:text:E" for command in commands))
        self.assertFalse(any(command.id in {"line:one", "line:two"} for command in commands))
        self.assertFalse(any(command.kind in {"bar_chart", "graph", "clear"} for beat in lesson.beats for command in beat.commands))
        self.assertFalse(any(command.id == "source:focus" for command in commands))

    def test_invalid_decorations_fall_back_to_visible_board_writing(self) -> None:
        payload = _lesson().model_dump(mode="json")
        payload["beats"][0]["commands"] = [
            {
                "id": "empty:highlight",
                "kind": "highlight",
                "space": "board",
                "target_id": "",
            },
            {"id": "clear:scene", "kind": "clear"},
            {"id": "math:fragment", "kind": "math", "layout": "flow", "text": "m"},
        ]

        normalized = _normalize_lesson(LessonPlan.model_validate(payload))

        self.assertEqual(len(normalized.beats[0].commands), 1)
        fallback = normalized.beats[0].commands[0]
        assert fallback.kind == "text"
        self.assertEqual(fallback.layout, "flow")
        self.assertEqual(fallback.text, normalized.beats[0].caption)

    def test_near_coincident_vertices_snap_into_one_shared_corner(self) -> None:
        analysis = ImageQuestionAnalysis.model_validate(
            {
                "extracted_question": "Triangle ABC sits on base AC. Find its area.",
                "should_reconstruct": True,
                "lines": [
                    # The vision model estimated the shared apex twice, a few
                    # thousandths apart, which renders as a visible gap.
                    {"id": "left", "x": 0.1, "y": 0.9, "x2": 0.5, "y2": 0.104},
                    {"id": "right", "x": 0.502, "y": 0.1, "x2": 0.9, "y2": 0.9},
                    {"id": "degenerate", "x": 0.3, "y": 0.5, "x2": 0.304, "y2": 0.5},
                ],
            }
        )

        compiled = _compile_diagram(analysis)
        segments = {command["id"]: command for command in compiled}

        self.assertNotIn("rebuild:line:degenerate", segments)
        apexes = {
            (segments["rebuild:line:left"]["x2"], segments["rebuild:line:left"]["y2"]),
            (segments["rebuild:line:right"]["x"], segments["rebuild:line:right"]["y"]),
        }
        self.assertEqual(len(apexes), 1)

    def test_compiled_labels_are_not_boxed_or_starved(self) -> None:
        analysis = ImageQuestionAnalysis.model_validate(
            {
                "extracted_question": "Rectangle ABCD has the given side lengths.",
                "should_reconstruct": True,
                "rects": [{"id": "frame", "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.6}],
                "labels": [
                    {"id": f"label-{index}", "text": f"P{index}", "x": 0.1 + index / 40, "y": 0.5}
                    for index in range(14)
                ],
            }
        )

        compiled = _compile_diagram(analysis)
        labels = [command for command in compiled if command["kind"] == "text"]

        # A fixed box clipped anything longer than a few characters, and the
        # old budget dropped most of a figure's labels without saying so.
        self.assertEqual(len(labels), 14)
        self.assertNotIn("width", labels[0])
        self.assertNotIn("height", labels[0])

    def test_a_full_diagram_keeps_the_planner_board_notes(self) -> None:
        payload = _lesson().model_dump(mode="json")
        diagram_commands = _compile_diagram(
            ImageQuestionAnalysis.model_validate(
                {
                    "extracted_question": "A labelled polygon.",
                    "should_reconstruct": True,
                    "rects": [{"id": "frame", "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.6}],
                    "labels": [
                        {"id": f"label-{index}", "text": f"P{index}", "x": 0.2 + index / 40, "y": 0.5}
                        for index in range(14)
                    ],
                }
            )
        )

        lesson = _inject_diagram(LessonPlan.model_validate(payload), diagram_commands)

        # A negative slice bound used to drop notes from the end of the list
        # rather than keeping none of them.
        self.assertIn("note:form", [command.id for command in lesson.beats[0].commands])

    def test_a_wrong_step_is_marked_without_condemning_the_correct_ones(self) -> None:
        lesson = _diagnosis_to_lesson(
            WorkDiagnosis.model_validate(
                {
                    "verdict": "incorrect",
                    "restated_steps": ["3x + 7 = 22", "3x = 29", "x = 9.67"],
                    "first_error_step": 2,
                    "error_quote": "3x = 29",
                    "misconception": "Added 7 to both sides instead of subtracting it.",
                    "next_hint": "What happens if you subtract 7 from each side?",
                    "correct_answer": "B) 21",
                    "confidence": 0.92,
                }
            ),
            "If 3x + 7 = 22, what is 5x - 4?",
        )
        notes = {
            command.id: command
            for command in lesson.beats[0].commands
            if isinstance(command, TextCommand)
        }
        highlights = [
            command for command in lesson.beats[0].commands
            if isinstance(command, HighlightCommand)
        ]

        # Step 1 was fine and must not be painted as an error.
        self.assertEqual(notes["work-note-0"].color, "#1a7f37")
        self.assertEqual(notes["work-note-1"].color, "#d93025")
        self.assertEqual([item.target_id for item in highlights], ["work-note-1"])
        self.assertEqual(lesson.final_answer, "B) 21")
        self.assertIn("subtract 7", lesson.beats[2].spoken_text)
        # One good step reads "step is", not "1 step are".
        self.assertIn("The first step is right", lesson.beats[0].spoken_text)

    def test_step_count_copy_agrees_with_itself(self) -> None:
        def opening(first_error_step: int) -> str:
            return _diagnosis_to_lesson(
                WorkDiagnosis.model_validate(
                    {
                        "verdict": "incorrect",
                        "restated_steps": ["a = 1", "b = 2", "c = 3", "d = 4"],
                        "first_error_step": first_error_step,
                        "error_quote": "x",
                        "next_hint": "Try again from there.",
                        "correct_answer": "7",
                        "confidence": 0.8,
                    }
                ),
                "question",
            ).beats[0].spoken_text

        self.assertIn("very first step", opening(1))
        self.assertIn("The first step is right", opening(2))
        self.assertIn("The first 2 steps are right", opening(3))

    def test_correct_work_is_confirmed_rather_than_re_solved(self) -> None:
        lesson = _diagnosis_to_lesson(
            WorkDiagnosis.model_validate(
                {
                    "verdict": "correct",
                    "restated_steps": ["3x + 7 = 22", "3x = 15", "x = 5"],
                    "first_error_step": 0,
                    "next_hint": "Same idea works when the coefficient is a fraction.",
                    "correct_answer": "B) 21",
                    "confidence": 0.95,
                }
            ),
            "If 3x + 7 = 22, what is 5x - 4?",
        )

        self.assertNotIn(
            "work-error-highlight",
            [command.id for beat in lesson.beats for command in beat.commands],
        )
        self.assertIn("checks out", lesson.beats[0].caption)

    def test_a_terse_misconception_still_renders(self) -> None:
        # "N/A" is truthy but shorter than answer_explanation's minimum, which
        # threw away diagnoses that had already passed review.
        for verdict, step in (("correct", 0), ("unclear", 0), ("incorrect", 1)):
            with self.subTest(verdict=verdict):
                lesson = _diagnosis_to_lesson(
                    WorkDiagnosis.model_validate(
                        {
                            "verdict": verdict,
                            "restated_steps": ["x = 5"],
                            "first_error_step": step,
                            "error_quote": "x = 5" if step else "",
                            "misconception": "N/A",
                            "next_hint": "Check the substitution.",
                            "correct_answer": "21",
                            "confidence": 0.8,
                        }
                    ),
                    "question",
                )
                self.assertGreaterEqual(len(lesson.answer_explanation), 5)

    def test_unclear_work_asks_instead_of_accusing(self) -> None:
        lesson = _diagnosis_to_lesson(
            WorkDiagnosis.model_validate(
                {
                    "verdict": "unclear",
                    "restated_steps": ["3x + 7 = 22", "??"],
                    "first_error_step": 0,
                    "next_hint": "Can you write out what you did between those two lines?",
                    "correct_answer": "B) 21",
                    "confidence": 0.3,
                }
            ),
            "If 3x + 7 = 22, what is 5x - 4?",
        )
        spoken = " ".join(beat.spoken_text for beat in lesson.beats)
        captions = " ".join(beat.caption for beat in lesson.beats)
        command_ids = [command.id for beat in lesson.beats for command in beat.commands]

        # An unreadable submission must ask, never locate a fault: no error
        # highlight, no "step N is the slip", and no claimed answer.
        self.assertNotIn("work-error-highlight", command_ids)
        self.assertNotRegex(captions, r"[Ss]tep \d")
        self.assertNotIn("B) 21", lesson.final_answer)
        self.assertIn("write out what you did", spoken)

    def test_zero_length_label_segments_fall_back_to_visible_writing(self) -> None:
        payload = _lesson().model_dump(mode="json")
        payload["beats"][0]["commands"] = [
            # The planner reaches for 'line' when it means 'text', leaving the
            # spoken beat describing vertex labels that never render.
            {"id": "labA", "kind": "line", "space": "diagram", "x": 0.1, "y": 0.1, "x2": 0.1, "y2": 0.1},
            {"id": "labB", "kind": "line", "space": "diagram", "x": 0.9, "y": 0.1, "x2": 0.9, "y2": 0.1},
            {"id": "realEdge", "kind": "line", "space": "diagram", "x": 0.1, "y": 0.1, "x2": 0.9, "y2": 0.1},
        ]

        normalized = _normalize_lesson(LessonPlan.model_validate(payload))
        commands = normalized.beats[0].commands

        self.assertNotIn("labA", [command.id for command in commands])
        self.assertNotIn("labB", [command.id for command in commands])
        self.assertIn("realEdge", [command.id for command in commands])

    def test_only_one_semantic_chart_survives(self) -> None:
        payload = _lesson().model_dump(mode="json")
        payload["beats"][0]["commands"] = [
            {
                "id": f"chart:{index}",
                "kind": "bar_chart",
                "bars": [{"label": "red", "value": 4}, {"label": "blue", "value": 6}],
            }
            for index in range(7)
        ]

        normalized = _normalize_lesson(
            LessonPlan.model_validate(payload),
            question_text="What is the probability of drawing a red marble?",
        )
        charts = [command for command in normalized.beats[0].commands if command.kind == "bar_chart"]

        self.assertEqual(len(charts), 1)

    def test_semantic_visuals_must_match_the_question_type(self) -> None:
        payload = _lesson().model_dump(mode="json")
        payload["beats"][0]["commands"] = [
            {
                "id": "venn:wrong",
                "kind": "venn",
                "left_label": "Equation",
                "right_label": "Answer",
                "left_only": "factor",
                "overlap": "roots",
                "right_only": "choice",
            }
        ]
        proposed = LessonPlan.model_validate(payload)

        quadratic = _normalize_lesson(
            proposed,
            question_text="Solve x^2 - 5x + 6 = 0.",
        )
        survey = _normalize_lesson(
            proposed,
            question_text="In a survey, how many students chose both music and art?",
        )

        self.assertEqual(quadratic.beats[0].commands[0].kind, "text")
        self.assertEqual(survey.beats[0].commands[0].kind, "venn")

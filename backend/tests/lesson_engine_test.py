from lesson_engine import (
    _compile_diagram,
    _diagnosis_to_lesson,
    _inject_diagram,
    _normalize_lesson,
)
from lesson_models import HighlightCommand, ImageQuestionAnalysis, LessonPlan, TextCommand, WorkDiagnosis


def _lesson() -> LessonPlan:
    return LessonPlan.model_validate(
        {
            "domain": "math",
            "question_summary": "Find the vertex of a quadratic graph.",
            "final_answer": "A) (2, -1)",
            "answer_explanation": "Completing the square gives the vertex.",
            "confidence": 0.99,
            "beats": [
                {
                    "id": "beat:one",
                    "teaching_goal": "Rewrite the quadratic",
                    "spoken_text": "First rewrite the quadratic in vertex form.",
                    "caption": "Rewrite in vertex form",
                    "strategy": "algebra",
                    "commands": [
                        {"id": "note:form", "kind": "math", "layout": "flow", "text": "y=(x-2)^2-1"}
                    ],
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
                            "markers": [{"id": "vertex", "x": 2, "y": -1}],
                            "x_min": -1,
                            "x_max": 5,
                            "y_min": -2,
                            "y_max": 8,
                        }
                    ],
                },
            ],
        }
    )


def test_invalid_decorations_fall_back_to_visible_writing() -> None:
    payload = _lesson().model_dump(mode="json")
    payload["beats"][0]["commands"] = [
        {"id": "empty:highlight", "kind": "highlight", "target_id": ""},
        {"id": "clear:scene", "kind": "clear"},
        {"id": "math:fragment", "kind": "math", "layout": "flow", "text": "m"},
    ]

    normalized = _normalize_lesson(LessonPlan.model_validate(payload))

    assert len(normalized.beats[0].commands) == 1
    assert normalized.beats[0].commands[0].kind == "text"
    assert normalized.beats[0].commands[0].text == normalized.beats[0].caption


def test_image_diagram_is_rebuilt_once_and_keeps_board_notes() -> None:
    analysis = ImageQuestionAnalysis.model_validate(
        {
            "extracted_question": "Square ABCD has side 6.",
            "diagram_summary": "A labelled square.",
            "should_reconstruct": True,
            "rects": [{"id": "square", "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}],
            "labels": [{"id": "A", "text": "A", "x": 0.06, "y": 0.06}],
        }
    )

    lesson = _inject_diagram(_lesson(), _compile_diagram(analysis))
    command_ids = [command.id for command in lesson.beats[0].commands]

    assert command_ids.count("rebuild:rect:square") == 1
    assert "rebuild:text:A" in command_ids
    assert "note:form" in command_ids


def test_near_vertices_snap_to_a_shared_corner() -> None:
    analysis = ImageQuestionAnalysis.model_validate(
        {
            "extracted_question": "Triangle ABC.",
            "should_reconstruct": True,
            "lines": [
                {"id": "left", "x": 0.1, "y": 0.9, "x2": 0.5, "y2": 0.104},
                {"id": "right", "x": 0.502, "y": 0.1, "x2": 0.9, "y2": 0.9},
                {"id": "degenerate", "x": 0.3, "y": 0.5, "x2": 0.304, "y2": 0.5},
            ],
        }
    )

    segments = {command["id"]: command for command in _compile_diagram(analysis)}

    assert "rebuild:line:degenerate" not in segments
    assert (segments["rebuild:line:left"]["x2"], segments["rebuild:line:left"]["y2"]) == (
        segments["rebuild:line:right"]["x"],
        segments["rebuild:line:right"]["y"],
    )


def test_wrong_work_marks_only_the_first_bad_step() -> None:
    diagnosis = WorkDiagnosis.model_validate(
        {
            "verdict": "incorrect",
            "restated_steps": ["3x + 7 = 22", "3x = 29", "x = 9.67"],
            "first_error_step": 2,
            "error_quote": "3x = 29",
            "misconception": "Added 7 instead of subtracting it.",
            "next_hint": "Subtract 7 from each side.",
            "correct_answer": "B) 21",
            "confidence": 0.92,
        }
    )

    lesson = _diagnosis_to_lesson(diagnosis, "If 3x + 7 = 22, what is 5x - 4?")
    notes = {
        command.id: command
        for command in lesson.beats[0].commands
        if isinstance(command, TextCommand)
    }
    highlights = [
        command for command in lesson.beats[0].commands if isinstance(command, HighlightCommand)
    ]

    assert notes["work-note-0"].color == "#1a7f37"
    assert notes["work-note-1"].color == "#d93025"
    assert [highlight.target_id for highlight in highlights] == ["work-note-1"]


def test_only_a_relevant_semantic_visual_survives() -> None:
    payload = _lesson().model_dump(mode="json")
    payload["beats"][0]["commands"] = [
        {
            "id": "venn:clubs",
            "kind": "venn",
            "left_label": "Music",
            "right_label": "Art",
            "left_only": "10",
            "overlap": "5",
            "right_only": "8",
        }
    ]
    proposed = LessonPlan.model_validate(payload)

    assert _normalize_lesson(proposed, question_text="Solve x^2 - 5x + 6 = 0.").beats[0].commands[0].kind == "text"
    assert _normalize_lesson(proposed, question_text="How many students chose both music and art?").beats[0].commands[0].kind == "venn"

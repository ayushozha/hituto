import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

from lesson_models import LessonPlan, SceneCommand, WorkDiagnosis


scene_command: TypeAdapter[SceneCommand] = TypeAdapter(SceneCommand)


def _diagnosis(**overrides: object) -> dict:
    payload: dict = {
        "verdict": "incorrect",
        "restated_steps": ["3x + 7 = 22", "3x = 29", "x = 9.67"],
        "first_error_step": 2,
        "error_quote": "3x = 29",
        "misconception": "Added 7 to both sides instead of subtracting it.",
        "next_hint": "What do you get if you take 7 away from each side?",
        "correct_answer": "B) 21",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def test_an_incorrect_verdict_must_locate_the_error() -> None:
    with pytest.raises(ValidationError):
        WorkDiagnosis.model_validate(_diagnosis(first_error_step=0))


def test_a_correct_verdict_cannot_also_flag_a_step() -> None:
    # The shape forbids expressing "your work is right, and step 2 is wrong".
    with pytest.raises(ValidationError):
        WorkDiagnosis.model_validate(_diagnosis(verdict="correct"))


def test_the_flagged_step_must_point_at_a_real_step() -> None:
    with pytest.raises(ValidationError):
        WorkDiagnosis.model_validate(_diagnosis(first_error_step=9))


def test_an_unclear_verdict_needs_no_error_step() -> None:
    diagnosis = WorkDiagnosis.model_validate(
        _diagnosis(verdict="unclear", first_error_step=0, error_quote="")
    )
    assert diagnosis.verdict == "unclear"


def test_scene_command_rejects_out_of_bounds_coordinate() -> None:
    with pytest.raises(ValidationError):
        scene_command.validate_python(
            {"id": "mark:one", "kind": "circle", "x": 1.2, "y": 0.4, "radius": 0.1}
        )


def test_erase_requires_target_id() -> None:
    with pytest.raises(ValidationError):
        scene_command.validate_python({"id": "erase:one", "kind": "erase"})


def test_graph_has_real_markers_instead_of_point_formulas() -> None:
    command = scene_command.validate_python(
        {
            "id": "graph:quadratic",
            "kind": "graph",
            "curves": [{"id": "curve", "formula": "x^2 - 4*x + 3"}],
            "markers": [{"id": "vertex", "x": 2, "y": -1, "label": "(2, -1)"}],
            "x_min": -1,
            "x_max": 5,
            "y_min": -2,
            "y_max": 8,
        }
    )
    assert command.kind == "graph"
    assert command.markers[0].x == 2
    assert command.markers[0].y == -1


def test_graph_rejects_unsafe_formulas_and_off_canvas_markers() -> None:
    with pytest.raises(ValidationError):
        scene_command.validate_python(
            {
                "id": "graph:unsafe",
                "kind": "graph",
                "curves": [{"id": "curve", "formula": "import(os)"}],
                "x_min": -2,
                "x_max": 2,
                "y_min": -2,
                "y_max": 2,
            }
        )
    with pytest.raises(ValidationError):
        scene_command.validate_python(
            {
                "id": "graph:marker",
                "kind": "graph",
                "markers": [{"id": "point", "x": 4, "y": 0}],
                "x_min": -2,
                "x_max": 2,
                "y_min": -2,
                "y_max": 2,
            }
        )


def test_semantic_bar_chart_and_venn_have_renderer_owned_geometry() -> None:
    chart = scene_command.validate_python(
        {
            "id": "chart:distribution",
            "kind": "bar_chart",
            "title": "Probability distribution",
            "bars": [
                {"label": "0", "value": 0.2},
                {"label": "1", "value": 0.5},
                {"label": "2", "value": 0.3},
            ],
        }
    )
    venn = scene_command.validate_python(
        {
            "id": "venn:clubs",
            "kind": "venn",
            "left_label": "Art",
            "right_label": "Music",
            "left_only": "35%",
            "overlap": "25%",
            "right_only": "20%",
            "outside": "20%",
        }
    )
    assert chart.kind == "bar_chart"
    assert [bar.value for bar in chart.bars] == [0.2, 0.5, 0.3]
    assert venn.kind == "venn"
    assert venn.overlap == "25%"


def test_plain_prose_cannot_be_disguised_as_math() -> None:
    with pytest.raises(ValidationError):
        scene_command.validate_python(
            {"id": "note:bad", "kind": "math", "layout": "flow", "text": "clearly much too big"}
        )


def test_named_quantities_are_still_maths() -> None:
    # Rejecting this cost whole lessons: it is notation, not prose.
    command = scene_command.validate_python(
        {
            "id": "note:area",
            "kind": "math",
            "layout": "flow",
            "text": "Area = ½ · base · height = ½ · 6 · 6",
        }
    )
    assert command.kind == "math"


def test_constructed_geometry_has_a_square_unit_space() -> None:
    command = scene_command.validate_python(
        {"id": "diagram:circle", "kind": "circle", "space": "diagram", "x": 0.25, "y": 0.5, "radius": 0.1}
    )
    assert command.kind == "circle"
    assert command.space == "diagram"


def test_lesson_plan_requires_multiple_beats() -> None:
    with pytest.raises(ValidationError):
        LessonPlan.model_validate(
            {
                "domain": "math",
                "question_summary": "A complete SAT question.",
                "final_answer": "B",
                "answer_explanation": "The equation simplifies to choice B.",
                "confidence": 0.9,
                "beats": [],
            }
        )


def test_a_provider_having_a_bad_minute_is_retryable() -> None:
    from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

    from tutor_service import _is_transient

    # These failures are safe candidates for an explicit request retry.
    assert _is_transient(ModelHTTPError(status_code=503, model_name="m"))
    assert _is_transient(ModelHTTPError(status_code=429, model_name="m"))
    assert _is_transient(httpx.ConnectError("refused"))
    assert _is_transient(httpx.ReadTimeout("slow"))
    assert _is_transient(ModelAPIError(model_name="m", message="never landed"))


def test_a_bad_request_is_not_retried_forever() -> None:
    from pydantic_ai.exceptions import ModelHTTPError, UserError

    from tutor_service import _is_transient

    # Retrying these just burns the student's time and the account's quota.
    assert not _is_transient(ModelHTTPError(status_code=400, model_name="m"))
    assert not _is_transient(ModelHTTPError(status_code=401, model_name="m"))
    assert not _is_transient(UserError("bad output type"))
    assert not _is_transient(ValueError("Upload a PNG or JPEG image"))


def test_the_same_answer_written_differently_is_the_same_answer() -> None:
    from lesson_engine import _same_answer

    # A follow-up that kept the answer must not be thrown away over typography.
    assert _same_answer("A) (2, -1)", "A) (2, −1)")      # Unicode minus
    assert _same_answer("C) 36π", "C) 36pi")             # pi
    assert _same_answer("A) 500 · 2^(t/3)", "A) 500 * 2^(t/3)")
    assert _same_answer("B) 21", "B)  21 ")


def test_a_genuinely_different_answer_is_still_caught() -> None:
    from lesson_engine import _same_answer

    # The guard exists so a follow-up cannot quietly teach a new answer.
    assert not _same_answer("A) (2, -1)", "B) (-2, -1)")
    assert not _same_answer("C) 18", "D) 24")
    assert not _same_answer("B) 21", "B) 12")

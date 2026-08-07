import pytest
from pydantic import TypeAdapter, ValidationError

from lesson_models import LessonPlan, SceneCommand


scene_command: TypeAdapter[SceneCommand] = TypeAdapter(SceneCommand)


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

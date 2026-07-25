from app.coursegen.mesh import craft_mesh_prompt
from app.coursegen.studio_catalog import propose_studio_subjects
from app.providers.mesh import _mesh_ref_image_prompt


def test_mesh_prompt_preserves_non_cell_subject():
    prompt = craft_mesh_prompt(
        "Orchid Bee Studio",
        topic="Orchid Bee anatomy, scent collection, and pollination",
    )

    assert "Orchid Bee anatomy" in prompt
    assert "plant cell" not in prompt


def test_mesh_prompt_keeps_specialized_plant_cell_structure():
    prompt = craft_mesh_prompt("Plant cell anatomy")

    assert "plant cell cross-section" in prompt
    assert "chloroplast" in prompt


def test_mesh_reference_prompt_enforces_one_isolated_view():
    prompt = _mesh_ref_image_prompt("Plant cell with visible nucleus and chloroplasts")

    assert "exactly one complete subject" in prompt
    assert "one single three-quarter camera view only" in prompt
    assert "uniform pure white background" in prompt
    assert "do not add any separate objects" in prompt
    assert "Do not create a collage" in prompt
    assert "Every visible part must be physically connected" in prompt
    assert "thin appendages deliberately thick" in prompt
    assert "transparent ghost layers" in prompt
    assert "Output only the isolated subject image" in prompt


def test_pollinator_lab_routes_each_subject_through_image_to_mesh_with_image_fallback():
    subjects = propose_studio_subjects(
        "Pollinator Lab: Orchid Bee (Euglossa dilemma) — explore anatomy, orchids, and ecology",
        "Pollinator Lab: Orchid Bee (Euglossa dilemma) — explore anatomy and scent collection",
    )

    assert [subject.name for subject in subjects] == [
        "Orchid Bee",
        "Garden Tiger Moth",
        "Jewel Beetle",
        "Ruby-throated Hummingbird",
        "Lesser Long-nosed Bat",
    ]
    assert all(subject.mesh_strategy == "hunyuan" for subject in subjects)
    assert all(subject.prompt for subject in subjects)
    assert "Euglossa dilemma" in subjects[0].prompt
    assert "complete full body" in subjects[0].prompt
    assert all(subject.stage_image_query for subject in subjects)
    assert "uniform warm ivory background" in subjects[0].stage_image_query
    assert "no flower" in subjects[0].stage_image_query
    assert len(subjects[0].field_notes) == 5


def test_plural_cells_routes_to_isolated_cell_catalog():
    subjects = propose_studio_subjects(
        "Many Types of Cells — compare plant, animal, bacterial, neuron, and muscle cells"
    )

    assert [subject.name for subject in subjects] == [
        "Plant Cell",
        "Animal Cell",
        "Bacteria Cell",
        "Neuron",
        "Muscle Cell",
    ]
    assert subjects[0].prompt.startswith("One cohesive plant cell educational sculpture")
    assert "Many Types" not in subjects[0].prompt
    assert [subject.mesh_strategy for subject in subjects] == [
        "hunyuan",
        "procedural",
        "procedural",
        "procedural",
        "procedural",
    ]
    assert [subject.procedural_kind for subject in subjects] == [
        "plant-cell",
        "animal-cell",
        "bacteria",
        "neuron",
        "muscle-fiber",
    ]
    assert all(subject.prompt is None for subject in subjects[1:])

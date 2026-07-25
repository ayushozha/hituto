import pytest
from pydantic import ValidationError

from app.capsule.postprocess import ensure_artifact_runtime, postprocess
from app.coursegen.studio_catalog import propose_studio_subjects, studio_subjects_for_prompt
from app.coursegen.studio_manifest import (
    StudioManifest,
    build_studio_manifest,
    prepare_studio_plan,
    resolve_studio_mode,
)
from app.coursegen.studio_renderer import render_studio_manifest, studio_artifact_metadata


def _plan(**updates):
    plan = {
        "title": "Orbital Motion",
        "subtitle": "Change the rate and observe how the system responds.",
        "archetype": "simulation",
        "presentation": "studio",
        "estimated_duration": "10m",
        "sections": [
            {
                "id": "force",
                "title": "Central force",
                "objective": "Connect inward force with the curved path.",
                "body": "The direction changes continuously while speed can remain stable.",
            },
            {
                "id": "trajectory",
                "title": "Trajectory",
                "objective": "Observe the resulting path.",
                "body": "The visible path responds to the model rate.",
            },
        ],
        "facts": [
            {
                "claim": "Orbital paths reflect continuous acceleration toward the center.",
                "source_url": "https://example.edu/orbits",
            }
        ],
    }
    return {**plan, **updates}


def test_explicit_studio_mode_wins_over_heuristics() -> None:
    assert resolve_studio_mode(_plan(title="Inside a jet engine"), {"studio_mode": "specimen"}) == "specimen"


def test_studio_mode_router_selects_each_milestone_mode() -> None:
    assert resolve_studio_mode(_plan(title="Cell anatomy", archetype="explainer")) == "specimen"
    assert resolve_studio_mode(_plan(title="Robot gait simulator")) == "simulation"
    assert resolve_studio_mode(_plan(title="Inside a jet engine", archetype="explainer")) == "process-cutaway"


def test_prepare_studio_plan_aligns_simulation_archetype() -> None:
    plan = prepare_studio_plan(_plan(archetype="explainer"), {"studio_mode": "simulation"})
    assert plan["presentation"] == "studio"
    assert plan["studio_mode"] == "simulation"
    assert plan["archetype"] == "simulation"


def test_simulation_manifest_has_supported_working_controls() -> None:
    manifest = build_studio_manifest(_plan())
    assert manifest.mode == "simulation"
    assert manifest.stage.asset.kind == "procedural_simulation"
    assert {control.kind for control in manifest.controls} >= {"range", "playback", "button"}
    assert manifest.parts[0].evidence_ids == ["e1"]
    assert "studio_control_changed" in manifest.learning_events
    assert "studio_reset" in manifest.learning_events


def test_process_cutaway_has_at_least_two_stages() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Water pump process",
            archetype="explainer",
            sections=[{"id": "intake", "title": "Intake", "objective": "Water enters."}],
        )
    )
    assert manifest.mode == "process-cutaway"
    assert len(manifest.parts) == 2
    assert any(control.kind == "timeline" for control in manifest.controls)


def test_specimen_uses_managed_mesh_and_procedural_fallback() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Plant cell",
            archetype="explainer",
            mesh_catalog=[
                {
                    "id": "plant",
                    "name": "Plant cell",
                    "subtitle": "Eukaryotic cell",
                    "path": "/build/mesh/plant.glb",
                }
            ],
        ),
        {"studio_mode": "specimen"},
    )
    assert manifest.stage.asset.kind == "generated_mesh"
    assert manifest.stage.asset.src == "/build/mesh/plant.glb"
    assert manifest.stage.asset.fallback == "procedural_specimen"
    assert "studio_degraded" in manifest.learning_events


def test_cell_subjects_keep_unique_meshes_images_and_matching_focus() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Many Types of Cells",
            archetype="explainer",
            sections=[
                {
                    "id": "intro",
                    "title": "Welcome to the Cell Studio",
                    "objective": "Compare plant, animal, bacterial, neuron, and muscle cells.",
                },
                {"id": "plant", "title": "Plant Cell", "objective": "Inspect chloroplasts."},
                {"id": "animal", "title": "Animal Cell", "objective": "Inspect its membrane."},
                {
                    "id": "bacteria",
                    "title": "Bacterial Cells",
                    "objective": "Inspect the bacterial nucleoid.",
                },
            ],
            mesh_catalog=[
                {
                    "id": "plant",
                    "name": "Plant Cell",
                    "path": "/build/mesh/plant.glb",
                    "procedural_kind": "plant-cell",
                },
                {
                    "id": "animal",
                    "name": "Animal Cell",
                    "path": "/build/mesh/animal.glb",
                    "procedural_kind": "animal-cell",
                },
                {
                    "id": "bacteria",
                    "name": "Bacteria Cell",
                    "path": "/build/mesh/bacteria.glb",
                    "procedural_kind": "bacteria",
                },
            ],
        ),
        {"studio_mode": "specimen"},
    )

    assert [subject.mesh_src for subject in manifest.subjects] == [
        "/build/mesh/plant.glb",
        "/build/mesh/animal.glb",
        "/build/mesh/bacteria.glb",
    ]
    assert len({subject.image_query for subject in manifest.subjects}) == 3
    assert manifest.subjects[2].image_query.startswith("Single isolated Bacteria Cell")
    assert [subject.procedural_kind for subject in manifest.subjects] == [
        "plant-cell",
        "animal-cell",
        "bacteria",
    ]
    assert [subject.default_part_id for subject in manifest.subjects] == [
        "plant",
        "animal",
        "bacteria",
    ]


def test_subject_without_mesh_does_not_inherit_primary_mesh() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Cell comparison",
            archetype="explainer",
            mesh_catalog=[
                {"id": "plant", "name": "Plant Cell", "path": "/build/mesh/plant.glb"},
                {"id": "animal", "name": "Animal Cell"},
            ],
        ),
        {"studio_mode": "specimen"},
    )

    assert manifest.stage.asset.src == "/build/mesh/plant.glb"
    assert manifest.subjects[0].mesh_src == "/build/mesh/plant.glb"
    assert manifest.subjects[1].mesh_src is None
    html = render_studio_manifest(manifest)
    assert 'reason_code: "subject_mesh_missing"' in html
    assert "subject.image_query" in html
    assert "syncPanelAccessibility();\n    // Apply the first subject" in html
    assert "all initialized.\n    selectSubject(0);" in html


def test_procedural_cell_subject_gets_owned_three_runtime() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Neuron Studio",
            archetype="explainer",
            mesh_catalog=[
                {
                    "id": "neuron",
                    "name": "Neuron",
                    "procedural_kind": "neuron",
                }
            ],
        ),
        {"studio_mode": "specimen"},
    )

    assert manifest.stage.asset.kind == "procedural_specimen"
    assert manifest.subjects[0].procedural_kind == "neuron"
    rendered = render_studio_manifest(manifest)
    assert 'data-procedural-kind=""' in rendered

    cleaned, checks = postprocess(rendered)
    cleaned = ensure_artifact_runtime(cleaned)
    assert checks["passed"] is True
    assert "hituto-mesh-runtime v15" in cleaned
    assert "function makeNeuron(group)" in cleaned
    assert "window.__hitutoClearMesh = clearMesh" in cleaned
    assert "'lesser-long-nosed-bat': { yaw: -1.5708, pitch: 0 }" in cleaned


def test_pollinator_lab_uses_real_mesh_stage_with_image_fallback() -> None:
    catalog = studio_subjects_for_prompt(propose_studio_subjects("Pollinator Lab"))
    for subject in catalog:
        subject["meshSrc"] = f"/build/mesh/{subject['id']}.glb"
    manifest = build_studio_manifest(
        _plan(
            title="Pollinator Lab",
            archetype="explainer",
            mesh_catalog=catalog,
        ),
        {"studio_mode": "specimen"},
    )

    assert manifest.theme == "field-guide"
    assert manifest.stage.asset.kind == "generated_mesh"
    assert manifest.stage.asset.fallback == "image_reference"
    assert len(manifest.subjects) == 5
    assert manifest.subjects[0].stage_image_query.startswith(
        "Ultra-detailed macro field-guide photograph"
    )
    assert len(manifest.subjects[0].field_notes) == 5
    assert manifest.subjects[0].tags[0] == "Neotropical"
    assert manifest.subjects[0].initial_yaw is None
    assert manifest.subjects[1].initial_yaw == 0.0
    assert manifest.subjects[1].initial_pitch == 0.0
    assert manifest.subjects[2].initial_yaw == pytest.approx(3.14159)
    assert manifest.subjects[4].initial_yaw == pytest.approx(-1.5708)

    rendered = render_studio_manifest(manifest)
    assert 'data-studio-theme="field-guide"' in rendered
    assert 'id="stage-image"' in rendered
    assert 'id="image-angle"' in rendered
    assert "Image view" in rendered
    assert "360°" not in rendered
    assert '"kind":"generated_mesh"' in rendered
    assert 'data-mesh-src=""' in rendered
    assert 'data-mesh-yaw=""' in rendered
    assert '"initial_yaw":-1.5708' in rendered
    assert "if (subjectUsesThree(subject))" in rendered


@pytest.mark.asyncio
async def test_non_specimen_studio_skips_every_mesh_path(monkeypatch) -> None:
    from app.coursegen.agents import roles

    calls: list[str] = []

    async def track_catalog(**_kwargs):
        calls.append("catalog")
        return None, None

    async def track_mesh(**_kwargs):
        calls.append("mesh")
        return None

    monkeypatch.setattr(roles, "run_studio_mesh_catalog", track_catalog)
    monkeypatch.setattr(roles, "run_mesh_generation", track_mesh)

    await roles.run_asset_plan_pipeline(
        concept="Inside a water pump",
        archetype="explainer",
        knobs={"presentation": "studio", "studio_mode": "process-cutaway"},
    )

    assert calls == []


def test_manifest_rejects_control_without_asset_capability() -> None:
    payload = build_studio_manifest(_plan()).model_dump()
    payload["controls"][0]["capability"] = "isolate"
    try:
        StudioManifest.model_validate(payload)
    except ValidationError as error:
        assert "unsupported capabilities" in str(error)
    else:
        raise AssertionError("manifest accepted an unsupported control")


def test_owned_renderer_passes_capsule_structure_gate() -> None:
    manifest = build_studio_manifest(_plan())
    html = render_studio_manifest(manifest)
    cleaned, checks = postprocess(html)

    assert checks["passed"] is True
    assert checks["canvas_count"] == 1
    assert checks["img_count"] == 2
    assert checks["control_count"] >= 1
    assert "__STUDIO_MANIFEST__" not in cleaned
    assert "attributeFilter: ['go-data-src']" in cleaned
    assert studio_artifact_metadata(cleaned) == {
        "presentation": "studio",
        "studio_manifest_version": "2.0",
        "studio_mode": "simulation",
    }


def test_non_mesh_mode_does_not_request_three_runtime() -> None:
    html = render_studio_manifest(build_studio_manifest(_plan()))
    assert "data-mesh-src" not in html


def test_mesh_mode_declares_runtime_holder() -> None:
    manifest = build_studio_manifest(
        _plan(
            title="Artifact",
            archetype="explainer",
            mesh_artifact={"path": "/build/mesh/model.glb"},
        ),
        {"studio_mode": "specimen"},
    )
    html = render_studio_manifest(manifest)
    assert 'data-mesh-src=""' in html

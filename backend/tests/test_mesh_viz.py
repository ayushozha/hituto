from types import SimpleNamespace

from app.coursegen.agents.roles import mesh_viz
from app.providers import registry


async def test_studio_mesh_uses_configured_high_detail_face_budget(monkeypatch):
    calls: list[dict] = []

    class FakeMesh:
        async def generate_mesh(self, **kwargs):
            calls.append(kwargs)
            return b"generated-glb"

    async def fake_persist(_: bytes) -> str:
        return "mesh-cache-key"

    settings = SimpleNamespace(
        mesh_studio_max_hunyuan=3,
        mesh_studio_face_count=1_000_000,
    )
    monkeypatch.setattr(mesh_viz, "get_settings", lambda: settings)
    monkeypatch.setattr(mesh_viz, "needs_3d_mesh", lambda **_: True)
    monkeypatch.setattr(mesh_viz, "persist_mesh_bytes_async", fake_persist)
    monkeypatch.setattr(registry, "get_mesh", lambda: FakeMesh())

    artifact = await mesh_viz.run_mesh_generation(
        concept="Neuron",
        archetype="explainer",
        knobs={"presentation": "studio", "needs_3d": True},
        prompt="One isolated neuron",
        subject_id="neuron",
    )

    assert artifact is not None
    assert artifact.face_count == 1_000_000
    assert calls == [
        {
            "prompt": "One isolated neuron",
            "enable_pbr": True,
            "face_count": 1_000_000,
            "generate_type": "Normal",
        }
    ]


async def test_cell_catalog_spends_gpu_only_on_plant_and_keeps_procedural_models(monkeypatch):
    calls: list[str] = []

    async def fake_run_mesh_generation(**kwargs):
        calls.append(kwargs["subject_id"])
        return SimpleNamespace(
            path=f"/build/mesh/{kwargs['subject_id']}.glb",
            cache_key="plant-cache-key",
        )

    monkeypatch.setattr(
        mesh_viz,
        "get_settings",
        lambda: SimpleNamespace(mesh_studio_max_hunyuan=5),
    )
    monkeypatch.setattr(mesh_viz, "run_mesh_generation", fake_run_mesh_generation)

    primary, catalog = await mesh_viz.run_studio_mesh_catalog(
        concept="Many Types of Cells Studio",
        archetype="explainer",
        knobs={"presentation": "studio", "needs_3d": True},
        specialist_name="science-specialist",
        topic="Compare plant, animal, bacteria, neuron, and muscle cells",
    )

    assert primary is not None
    assert calls == ["plant"]
    assert [entry["procedural_kind"] for entry in catalog] == [
        "plant-cell",
        "animal-cell",
        "bacteria",
        "neuron",
        "muscle-fiber",
    ]
    assert [entry["mesh_strategy"] for entry in catalog] == [
        "hunyuan",
        "procedural",
        "procedural",
        "procedural",
        "procedural",
    ]


async def test_pollinator_field_guide_generates_one_unique_mesh_per_subject(monkeypatch):
    calls: list[str] = []

    async def fake_run_mesh_generation(**kwargs):
        calls.append(kwargs["subject_id"])
        return SimpleNamespace(
            path=f"/build/mesh/{kwargs['subject_id']}.glb",
            cache_key=f"{kwargs['subject_id']}-cache-key",
        )

    monkeypatch.setattr(
        mesh_viz,
        "get_settings",
        lambda: SimpleNamespace(mesh_studio_max_hunyuan=5),
    )
    monkeypatch.setattr(mesh_viz, "needs_3d_mesh", lambda **_: True)
    monkeypatch.setattr(mesh_viz, "run_mesh_generation", fake_run_mesh_generation)

    primary, catalog = await mesh_viz.run_studio_mesh_catalog(
        concept="Pollinator Lab",
        archetype="explainer",
        knobs={"presentation": "studio", "needs_3d": True},
        topic="Pollinator field guide with bees, moths, beetles, birds, and bats",
    )

    assert primary is not None
    assert calls == [
        "orchid-bee",
        "garden-tiger",
        "jewel-beetle",
        "ruby-hummingbird",
        "lesser-long-nosed-bat",
    ]
    assert len(catalog) == 5
    assert len({entry.get("meshSrc") for entry in catalog}) == 5
    assert all(entry.get("stage_image_query") for entry in catalog)

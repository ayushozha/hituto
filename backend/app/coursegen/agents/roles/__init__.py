"""Role subagent hooks for coursegen (Phase 2).

Deterministic / best-effort helpers invoked from `asset_plan` today.
When Deep Agents lesson orchestration lands, the same contracts become `task` targets.

fast_gen Phase 3 split the pipeline into `run_mesh_stage` (slow, network — can run as a
background job) and `run_compute_stage` (fast, local sandbox — stays inline);
`run_asset_plan_pipeline` composes both for the synchronous path.
"""
from __future__ import annotations

from ...compute import ComputeArtifact, validate_compute_output
from ...mesh import MeshArtifact
from ...sandbox import run_viz_lab
from .data_synthesizer import synthesize_dataset
from .mesh_viz import run_mesh_generation, run_studio_mesh_catalog


def _asset_modes(
    concept: str, archetype: str, knobs: dict, topic: str | None
) -> tuple[bool, str | None]:
    from ...presentation import resolve_presentation
    from ...studio_catalog import is_studio_knobs
    from ...studio_manifest import resolve_studio_mode

    mode = resolve_presentation(
        {"title": concept, "topic": topic, "needs_3d": knobs.get("needs_3d")},
        knobs,
    )
    studio_mode = resolve_studio_mode(
        {"title": concept, "topic": topic, "archetype": archetype}, knobs
    )
    is_studio = mode == "studio" or is_studio_knobs(knobs)
    return is_studio, studio_mode


async def run_mesh_stage(
    *,
    concept: str,
    archetype: str,
    knobs: dict | None = None,
    specialist_name: str | None = None,
    topic: str | None = None,
) -> tuple[MeshArtifact | None, list[dict] | None]:
    """Mesh half of the asset pipeline: (primary_mesh, mesh_catalog|None). Best-effort."""
    knobs = knobs or {}
    try:
        is_studio, studio_mode = _asset_modes(concept, archetype, knobs, topic)
        if is_studio and studio_mode == "specimen":
            # Ensure catalog path sees studio presentation for the Hunyuan gate
            studio_knobs = {**knobs, "presentation": "studio"}
            return await run_studio_mesh_catalog(
                concept=concept,
                archetype=str(archetype),
                knobs=studio_knobs,
                specialist_name=specialist_name,
                topic=topic,
            )
        if not is_studio:
            mesh = await run_mesh_generation(
                concept=concept,
                archetype=str(archetype),
                knobs=knobs,
                specialist_name=specialist_name,
                topic=topic,
            )
            return mesh, None
    except Exception:  # noqa: BLE001
        pass
    return None, None


def run_compute_stage(
    *,
    concept: str,
    archetype: str,
    knobs: dict | None = None,
    seed: int | None = None,
    topic: str | None = None,
) -> ComputeArtifact | None:
    """Compute half: data-synthesizer → viz-engineer (simulation/game only)."""
    knobs = knobs or {}
    try:
        is_studio, studio_mode = _asset_modes(concept, archetype, knobs, topic)
    except Exception:  # noqa: BLE001
        is_studio, studio_mode = False, None
    arch = (archetype or "explainer").lower()
    if is_studio and studio_mode == "simulation":
        arch = "simulation"
    if arch not in ("simulation", "game"):
        return None
    try:
        dataset = synthesize_dataset(concept=concept, seed=seed)
        art = run_viz_lab(concept=concept, dataset=dataset)
        art.role_log = [
            "data_synthesizer:ok",
            *list(art.role_log or []),
        ]
        art.validation = validate_compute_output(art)
        if not art.validation.get("passed"):
            art.role_log.append("qa:compute_validation_soft_fail")
        return art
    except Exception:  # noqa: BLE001
        return None


async def run_asset_plan_pipeline(
    *,
    concept: str,
    archetype: str,
    seed: int | None = None,
    knobs: dict | None = None,
    specialist_name: str | None = None,
    topic: str | None = None,
) -> tuple[ComputeArtifact | None, MeshArtifact | None, list[dict] | None]:
    """data-synthesizer → viz-engineer (+ optional Hunyuan mesh / studio catalog).

    Skips compute for non-sim/non-game archetypes (no regression for explainers).
    Mesh is best-effort when studio 3D gate matches.
    Returns (compute, primary_mesh, mesh_catalog|None).
    """
    mesh_art, mesh_catalog = await run_mesh_stage(
        concept=concept,
        archetype=archetype,
        knobs=knobs,
        specialist_name=specialist_name,
        topic=topic,
    )
    art = run_compute_stage(
        concept=concept, archetype=archetype, knobs=knobs, seed=seed, topic=topic
    )
    return art, mesh_art, mesh_catalog

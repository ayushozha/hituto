"""viz-engineer mesh generation hook (Hunyuan 3D Pro) — studio presentation only."""
from __future__ import annotations

from ....core.config import get_settings
from ...mesh import (
    MeshArtifact,
    craft_mesh_prompt,
    needs_3d_mesh,
    persist_mesh_bytes_async,
)
from ...studio_catalog import propose_studio_subjects, studio_subjects_for_prompt


async def run_mesh_generation(
    *,
    concept: str,
    archetype: str,
    knobs: dict | None = None,
    specialist_name: str | None = None,
    topic: str | None = None,
    prompt: str | None = None,
    subject_id: str | None = None,
) -> MeshArtifact | None:
    """Best-effort Hunyuan mesh for studio presentation lessons only."""
    settings = get_settings()
    # MESH_STUDIO_MAX_HUNYUAN=0 pauses all Hunyuan API spend (procedural only).
    if int(getattr(settings, "mesh_studio_max_hunyuan", 3) or 0) <= 0:
        return None
    if not needs_3d_mesh(
        concept=concept,
        archetype=archetype,
        knobs=knobs,
        specialist_name=specialist_name,
        topic=topic,
    ):
        return None
    try:
        from ....providers.registry import get_mesh

        mesh_prompt = prompt or craft_mesh_prompt(concept, topic=topic)
        face_count = int(
            getattr(settings, "mesh_studio_face_count", 1_000_000) or 1_000_000
        )
        mesh = get_mesh()
        data = await mesh.generate_mesh(
            prompt=mesh_prompt,
            enable_pbr=True,
            face_count=face_count,
            generate_type="Normal",
        )
        if not data:
            return None
        cache_key = await persist_mesh_bytes_async(data)
        sid = subject_id or "primary"
        return MeshArtifact(
            path=f"/build/mesh/{sid}.glb",
            prompt=mesh_prompt,
            cache_key=cache_key,
            data_b64=None,
            face_count=face_count,
            role_log=["viz_engineer:generate_mesh:ok", f"cache_key:{cache_key}", f"subject:{sid}"],
        )
    except Exception:  # noqa: BLE001 — never block lesson generation
        return None


async def run_studio_mesh_catalog(
    *,
    concept: str,
    archetype: str,
    knobs: dict | None = None,
    specialist_name: str | None = None,
    topic: str | None = None,
) -> tuple[MeshArtifact | None, list[dict]]:
    """Build subject catalog and generate up to N Hunyuan meshes; rest stay procedural.

    Returns (primary MeshArtifact for backward-compat embed, serialized catalog).
    """
    knobs = knobs or {}
    subjects = propose_studio_subjects(topic or concept, concept)
    settings = get_settings()
    budget = int(getattr(settings, "mesh_studio_max_hunyuan", 3) or 0)
    hunyuan_used = 0
    hunyuan_attempted = 0
    primary: MeshArtifact | None = None

    for subj in subjects:
        if subj.mesh_strategy != "hunyuan":
            continue
        if hunyuan_used >= budget:
            subj.mesh_strategy = "procedural"
            continue
        hunyuan_attempted += 1
        art = await run_mesh_generation(
            concept=subj.name,
            archetype=archetype,
            knobs={**knobs, "needs_3d": True, "presentation": "studio"},
            specialist_name=specialist_name,
            topic=topic,
            prompt=subj.prompt,
            subject_id=subj.id,
        )
        if art is None:
            subj.mesh_strategy = "procedural"
            continue
        hunyuan_used += 1
        subj.path = art.path
        subj.cache_key = art.cache_key
        if primary is None:
            primary = art

    # If nothing generated but gate says mesh wanted, try one primary Hunyuan call.
    # Catalogs with reconstruction images already attempted their own distinct subjects;
    # never replace all of them with one generic primary mesh.
    if (
        primary is None
        and budget > 0
        and hunyuan_attempted == 0
        and not any(subject.stage_image_query for subject in subjects)
        and needs_3d_mesh(
            concept=concept,
            archetype=archetype,
            knobs=knobs,
            specialist_name=specialist_name,
            topic=topic,
        )
    ):
        primary = await run_mesh_generation(
            concept=concept,
            archetype=archetype,
            knobs=knobs,
            specialist_name=specialist_name,
            topic=topic,
            subject_id="primary",
        )
        if primary and subjects:
            subjects[0].path = primary.path
            subjects[0].cache_key = primary.cache_key
            subjects[0].mesh_strategy = "hunyuan"

    catalog = studio_subjects_for_prompt(subjects)
    return primary, catalog


def mesh_viz_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: generates studio 3D meshes and writes the mesh manifest (§4.2)."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import generate_studio_meshes_tool

    return {
        "name": "mesh_viz",
        "description": "Generate studio 3D meshes and write /build/mesh/manifest.json.",
        "system_prompt": load_agent_prompt(
            "mesh_viz",
            "You are the mesh viz engineer. For studio lessons, call generate_studio_meshes_tool "
            "with the concept/topic and write the returned manifest JSON to /build/mesh/manifest.json. "
            "Mesh is best-effort — if it returns {}, tell the author to use procedural geometry.",
        ),
        "tools": [generate_studio_meshes_tool],
    }

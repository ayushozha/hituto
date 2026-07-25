"""LangChain @tool wrappers over existing coursegen functions for Deep Agent subagents.

Thin adapters — each wraps a live coursegen / rag / capsule / provider function. Tools return
JSON-serializable summaries (never multi-MB blobs); provider/DB access is lazy so import stays
cheap and offline test fakes are honored. See coursegen-agent design §10 (tool matrix).
"""
from __future__ import annotations

import json

from langchain_core.tools import tool


@tool
async def web_search(query: str, n: int = 5) -> str:
    """Search the web for grounded facts about a topic. Returns a JSON list of {title, url, text}."""
    from ...providers.registry import get_search

    results = await get_search().search(query, n=int(n))
    return json.dumps(results)[:6000]


@tool
def capsule_checks(html: str) -> str:
    """Run the capsule security + quality gate on lesson HTML. Returns JSON {passed, failed}."""
    from ...capsule.postprocess import postprocess

    _clean, checks = postprocess(html or "")
    return json.dumps({"passed": bool(checks.get("passed")), "failed": checks.get("failed", [])})


@tool
async def emit_progress(course_id: str, stage: str, detail: str, pct: int) -> str:
    """Emit an SSE progress event on the course generation stream."""
    from ..graph import _emit

    await _emit(course_id, str(stage), str(detail), int(pct))
    return "ok"


@tool
def synthesize_dataset_tool(concept: str, seed: int = 0) -> str:
    """Generate a seeded, schema-valid dataset for a data-driven lesson. Returns JSON.

    Write the returned JSON to /build/dataset.json so the viz step can read it.
    """
    from .roles.data_synthesizer import synthesize_dataset

    return json.dumps(synthesize_dataset(concept=concept, seed=int(seed) or None))[:6000]


@tool
def run_viz_lab_tool(concept: str) -> str:
    """Run the server-side visualization lab → a ComputeArtifact manifest (JSON: plots/trace/chart).

    Write the returned JSON to /build/compute/manifest.json so the host inlines the plots at persist.
    Plots run server-side only — never execute Python in the learner iframe.
    """
    from ..compute import validate_compute_output
    from ..sandbox import run_viz_lab

    art = run_viz_lab(concept=concept)
    art.validation = validate_compute_output(art)
    return art.model_dump_json()


@tool
async def generate_studio_meshes_tool(concept: str, topic: str = "") -> str:
    """Generate studio 3D meshes (Hunyuan) for a spatial/studio lesson.

    Returns a COMPACT JSON manifest {mesh_artifact, mesh_catalog} — no mesh bytes (GLBs are cached
    on disk and served via /mesh?key= at persist). Write it to /build/mesh/manifest.json. Mesh is
    best-effort: returns {} on any failure so the lesson still renders procedurally.
    """
    from .roles.mesh_viz import run_studio_mesh_catalog

    try:
        primary, catalog = await run_studio_mesh_catalog(
            concept=concept,
            archetype="explainer",
            knobs={"needs_3d": True, "presentation": "studio"},
            topic=topic or concept,
        )
    except Exception:  # noqa: BLE001 — mesh never blocks generation
        return "{}"
    manifest: dict = {"mesh_catalog": catalog or []}
    if primary is not None:
        # Exclude multi-MB bytes — persist re-reads the GLB from the disk cache by cache_key.
        manifest["mesh_artifact"] = primary.model_dump(exclude={"data_b64"})
    return json.dumps(manifest)[:8000]


@tool
def check_katex(latex: str) -> str:
    """Validate a KaTeX / LaTeX math expression. Returns JSON {ok, error?}."""
    from ..validators import check_katex as _check

    return json.dumps(_check(latex))


@tool
def balance_equation(left: str, right: str) -> str:
    """Check whether a chemical equation (left -> right) is balanced. Returns JSON."""
    from ..validators import balance_equation as _balance

    return json.dumps(_balance(left, right))


def tool_by_name(name: str):
    """Map a registry Specialist.extra_tools name to a bound @tool (or None if unknown)."""
    return {
        "check_katex": check_katex,
        "balance_equation": balance_equation,
        "run_viz_lab": run_viz_lab_tool,
        "run_simulation": run_viz_lab_tool,
        "generate_mesh": generate_studio_meshes_tool,
        "web_search": web_search,
    }.get(name)

"""Mesh artifacts for coursegen Hunyuan 3D (hunyuan-3d-agent spec)."""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ..providers.mesh import mesh_cache_key_for_bytes, sync_mesh_to_storage, write_mesh_cache

_MESH_SCRATCH_RE = re.compile(
    r"""(data-mesh-src=['"])(/build/mesh/[^'"]+)(['"])""",
    re.I,
)
_MESH_IMG_RE = re.compile(
    r"""(<(?:script|img)\b[^>]*\s(?:src|data-mesh-src)=['"])(/build/mesh/[^'"]+)(['"][^>]*>)""",
    re.I,
)


class MeshArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"mesh-{uuid.uuid4().hex[:10]}")
    path: str = "/build/mesh/model.glb"
    mime: str = "model/gltf-binary"
    prompt: str | None = None
    image_url: str | None = None
    enable_pbr: bool = True
    face_count: int | None = None
    cache_key: str | None = None
    data_b64: str | None = None
    role_log: list[str] = Field(default_factory=list)


def mesh_public_url(cache_key: str) -> str:
    return f"/mesh?key={cache_key}"


def persist_mesh_bytes(data: bytes) -> str:
    """Write mesh bytes to disk cache; return public cache key.

    Prefer `persist_mesh_bytes_async` in async paths so InsForge storage is updated.
    """
    key = mesh_cache_key_for_bytes(data)
    write_mesh_cache(data, key)
    return key


async def persist_mesh_bytes_async(data: bytes) -> str:
    """Disk cache + InsForge storage upload (durable for deployed compute)."""
    key = persist_mesh_bytes(data)
    await sync_mesh_to_storage(key, data)
    return key


def inline_mesh_urls_in_html(html: str, artifact: MeshArtifact | None) -> str:
    """Rewrite scratch `/build/mesh/...` references to same-origin `/mesh?key=`."""
    if not html or not artifact or not artifact.cache_key:
        return html
    url = mesh_public_url(artifact.cache_key)

    def repl_attr(m: re.Match) -> str:
        return f"{m.group(1)}{url}{m.group(3)}"

    out = _MESH_SCRATCH_RE.sub(repl_attr, html)
    return _MESH_IMG_RE.sub(repl_attr, out)


def inline_mesh_catalog_in_html(html: str, catalog: list[dict[str, Any]] | None) -> str:
    """Rewrite per-subject scratch mesh paths from a studio mesh_catalog."""
    if not html or not catalog:
        return html
    out = html
    for entry in catalog:
        path = entry.get("path") or entry.get("meshSrc")
        key = entry.get("cache_key")
        if not path or not key:
            continue
        url = mesh_public_url(str(key))
        # Exact path replace in attributes
        out = out.replace(str(path), url)
    return out


def needs_3d_mesh(
    *,
    concept: str,
    archetype: str,
    knobs: dict[str, Any] | None = None,
    specialist_name: str | None = None,
    topic: str | None = None,
) -> bool:
    """Gate Hunyuan mesh generation — studio presentation only (cost control)."""
    knobs = knobs or {}
    from .presentation import resolve_presentation

    plan_stub = {
        "presentation": knobs.get("design_mode") or knobs.get("presentation", "auto"),
        "needs_3d": knobs.get("needs_3d"),
        "title": concept,
        "topic": topic,
        "subtitle": concept,
    }
    if resolve_presentation(plan_stub, knobs) != "studio":
        return False
    if knobs.get("needs_3d") is True:
        return True
    if knobs.get("needs_3d") is False:
        return False
    haystack = f"{concept} {topic or ''}".lower()
    if not re.search(
        r"\b(cell|organelle|membrane|biology|eukaryotic|prokaryotic|plant cell|animal cell|"
        r"nucleus|mitochondria|chloroplast|bacteria|microscopic|anatomy|molecule|planet|"
        r"solar system|machine|circuit|cross-?section|3d|spatial)\b",
        haystack,
    ):
        return False
    if specialist_name == "science-specialist":
        return True
    return (archetype or "").lower() in ("simulation", "tool", "explainer")


def craft_mesh_prompt(concept: str, *, topic: str | None = None) -> str:
    """Educational mesh prompt that preserves the lesson's actual subject."""
    # Prefer the course topic over generic chapter titles, but never silently replace an
    # unrelated specimen with the old plant-cell demo fixture.
    base = (topic or concept or "learning specimen").strip()
    if re.search(r"^chapter\s+\d+", base, re.I):
        base = (topic or concept or "learning specimen").strip()
    base = re.sub(r"\s+", " ", base)[:280].strip(" ,.;:")
    subject = base
    if "animal" in base.lower():
        subject = "animal cell cross-section with nucleus and mitochondria"
    elif "bacteria" in base.lower() or "prokaryotic" in base.lower():
        subject = "bacterial cell with cell wall and flagella, scientific model"
    elif "plant" in base.lower():
        subject = "plant cell cross-section with cell wall, nucleus, chloroplast, and vacuole"
    return (
        f"Highly detailed 3D scientific model of {subject}, vibrant educational colors, "
        "clean solid background, single centered object, PBR materials, no text overlays"
    )

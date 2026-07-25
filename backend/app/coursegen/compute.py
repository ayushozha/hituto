"""Compute artifacts for coursegen (coursegen-agent Phase 2).

Extends — does not replace — `SimulationTrace`. Scratch `/build/compute/` is ephemeral;
persisted capsules inline plots as `data:` URLs (design §5.1).
"""
from __future__ import annotations

import base64
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from .simulation import SimulationTrace, validate_trace

_DATA_IMG_RE = re.compile(
    r"""(<img\b[^>]*\ssrc=['"])(/build/compute/[^'"]+)(['"][^>]*>)""",
    re.I,
)


class ComputeAsset(BaseModel):
    path: str  # scratch-relative, e.g. /build/compute/plots/dist.png
    mime: str  # image/png | image/svg+xml
    alt: str = ""
    # Optional in-memory bytes for MVP inlining (never persisted as a separate store).
    data_b64: str | None = None


class ComputeArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"cmp-{uuid.uuid4().hex[:10]}")
    seed: int | None = None
    dataset_path: str | None = None
    dataset: dict[str, Any] | None = None
    trace: SimulationTrace | None = None
    chart_spec: dict[str, Any] | None = None
    assets: list[ComputeAsset] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    role_log: list[str] = Field(default_factory=list)


def validate_compute_output(artifact: ComputeArtifact) -> dict[str, Any]:
    """Deterministic checks on a ComputeArtifact (trace + assets + chart_spec)."""
    failed: list[str] = []
    if artifact.trace is not None:
        tv = validate_trace(artifact.trace)
        if not tv.get("passed"):
            failed.extend(f"trace: {f}" for f in (tv.get("failed") or []))
    for a in artifact.assets:
        if not a.path:
            failed.append("asset missing path")
        if a.mime not in ("image/png", "image/svg+xml", "image/jpeg"):
            failed.append(f"unsupported asset mime: {a.mime}")
        if a.mime.startswith("image/") and not (a.data_b64 or a.path.startswith("/build/")):
            failed.append(f"asset '{a.path}' has no inline data and no scratch path")
    if artifact.chart_spec is not None:
        if not isinstance(artifact.chart_spec, dict):
            failed.append("chart_spec must be an object")
        elif "labels" not in artifact.chart_spec and "datasets" not in artifact.chart_spec:
            failed.append("chart_spec missing labels/datasets")
    return {"passed": not failed, "failed": failed}


def asset_data_url(asset: ComputeAsset) -> str | None:
    """Build a data: URL for a compute plot asset (MVP persist path)."""
    if not asset.data_b64:
        return None
    return f"data:{asset.mime};base64,{asset.data_b64}"


def inline_compute_assets_in_html(html: str, artifact: ComputeArtifact | None) -> str:
    """Replace scratch `/build/compute/...` img src with data: URLs from the artifact.

    Leaves existing `data:` src untouched (postprocess invariant).
    """
    if not html or not artifact or not artifact.assets:
        return html
    by_path = {a.path: a for a in artifact.assets if a.path}

    def repl(m: re.Match) -> str:
        prefix, path, suffix = m.group(1), m.group(2), m.group(3)
        asset = by_path.get(path)
        if not asset:
            return m.group(0)
        url = asset_data_url(asset)
        if not url:
            return m.group(0)
        return f"{prefix}{url}{suffix}"

    return _DATA_IMG_RE.sub(repl, html)


def encode_png_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def encode_svg_text(svg: str) -> str:
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


# Minimal 1x1 PNG (transparent) for stub plots when matplotlib isn't available.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def stub_plot_asset(*, name: str = "plot", alt: str = "precomputed plot") -> ComputeAsset:
    return ComputeAsset(
        path=f"/build/compute/plots/{name}.png",
        mime="image/png",
        alt=alt,
        data_b64=encode_png_bytes(_TINY_PNG),
    )

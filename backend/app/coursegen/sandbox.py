"""Sandbox lab (tasks.md #31, #32, #50): compute a VALIDATED simulation trace for a mechanism.

Providers via SANDBOX_PROVIDER:
- `none` (default): deterministic stub trace, NO code execution — safe + offline.
- `local`: run the given Python in a subprocess with a timeout + minimal env, capturing a JSON trace.

SECURITY: `local` is best-effort (timeout + stripped env), NOT real isolation — use it only for
TRUSTED, generated toy computations. For untrusted code use a real sandbox (Daytona/E2B), which slot
in behind this same `run_lab` interface. The browser renders the resulting trace as DATA (no runtime
sandbox — R6.6); see prompt.py's PRECOMPUTED SIMULATION TRACE block (task #33).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from ..core.config import get_settings
from .simulation import SimulationTrace, TraceStep, validate_trace

if TYPE_CHECKING:
    from .compute import ComputeArtifact


def _stub_trace(concept: str) -> SimulationTrace:
    """A deterministic, valid attention-style trace (softmax sums to 1) — used when no sandbox runs."""
    return SimulationTrace(
        trace_id="stub",
        concept=concept or "scaled_dot_product_attention",
        source="deterministic",
        inputs={"tokens": ["The", "cat", "sat"]},
        steps=[
            TraceStep(name="dot_products", values=[0.12, 0.91, 0.35]),
            TraceStep(name="softmax_weights", values=[0.25, 0.44, 0.31]),
        ],
        validation={"passed": True, "failed": []},
    )


def _run_local(code: str, *, concept: str, libraries: list[str] | None, timeout: int) -> SimulationTrace:
    """Run `code` in a subprocess. It MUST print a final JSON line:
    {"inputs": {...}, "steps": [{"name": str, "values": [float, ...]}, ...]}."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", "")},  # minimal env; no app secrets
        )
        if proc.returncode != 0:
            raise RuntimeError(f"lab process failed: {proc.stderr[-300:]}")
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    trace = SimulationTrace(
        trace_id="lab",
        concept=concept,
        source="sandbox_verified",
        runtime="python",
        libraries=libraries or [],
        inputs=payload.get("inputs", {}),
        steps=[TraceStep(**s) for s in payload.get("steps", [])],
    )
    trace.validation = validate_trace(trace)
    return trace


def run_lab(
    code: str | None = None, *, concept: str, libraries: list[str] | None = None, timeout: int = 20
) -> SimulationTrace:
    """Produce a validated simulation trace. `local` executes `code`; otherwise a deterministic stub."""
    if get_settings().sandbox_provider == "local" and code:
        return _run_local(code, concept=concept, libraries=libraries, timeout=timeout)
    return _stub_trace(concept)


# Alias used by viz-engineer / science specialist tooling (design §4 / §6).
run_simulation = run_lab


def run_viz_lab(
    *,
    concept: str,
    dataset: dict | None = None,
    code: str | None = None,
    timeout: int = 20,
) -> "ComputeArtifact":
    """Best-effort visualization lab → ComputeArtifact (plots + optional trace/chart_spec).

    - `SANDBOX_PROVIDER=none` (default): stub plot + deterministic trace (no code execution).
    - `local` + `code`: run Python; expect final JSON line with optional `chart_spec` and
      `svg` / `png_b64` fields in addition to the usual trace payload.
    Failures never raise to the caller — returns a validated stub artifact.
    """
    from .compute import (
        ComputeArtifact,
        stub_plot_asset,
        validate_compute_output,
    )

    role_log = [f"viz_engineer:run_viz_lab concept={concept!r}"]
    try:
        if get_settings().sandbox_provider == "local" and code:
            art = _run_local_viz(code, concept=concept, dataset=dataset, timeout=timeout)
            art.role_log = role_log + ["viz_engineer:local"]
            art.validation = validate_compute_output(art)
            return art
    except Exception as exc:  # noqa: BLE001 — best-effort
        role_log.append(f"viz_engineer:local_failed:{exc}")

    trace = _stub_trace(concept)
    chart = None
    if dataset and isinstance(dataset.get("labels"), list) and isinstance(dataset.get("values"), list):
        chart = {
            "labels": list(dataset["labels"]),
            "datasets": [{"label": concept or "series", "data": list(dataset["values"])}],
        }
    art = ComputeArtifact(
        seed=(dataset or {}).get("seed") if isinstance(dataset, dict) else None,
        dataset_path="/build/dataset.json" if dataset else None,
        dataset=dataset,
        trace=trace,
        chart_spec=chart,
        assets=[stub_plot_asset(name="stub", alt=f"{concept} plot")],
        role_log=role_log + ["viz_engineer:stub"],
    )
    art.validation = validate_compute_output(art)
    return art


def _run_local_viz(
    code: str, *, concept: str, dataset: dict | None, timeout: int
) -> "ComputeArtifact":
    from .compute import ComputeArtifact, ComputeAsset, encode_svg_text, stub_plot_asset

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        preamble = ""
        if dataset is not None:
            preamble = f"DATASET = {json.dumps(dataset)}\n"
        f.write(preamble + code)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0:
            raise RuntimeError(f"viz lab failed: {proc.stderr[-300:]}")
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    trace = SimulationTrace(
        trace_id="viz-lab",
        concept=concept,
        source="sandbox_verified",
        runtime="python",
        libraries=[],
        inputs=payload.get("inputs", {}),
        steps=[TraceStep(**s) for s in payload.get("steps", [])],
    )
    trace.validation = validate_trace(trace)

    assets: list[ComputeAsset] = []
    if payload.get("png_b64"):
        assets.append(
            ComputeAsset(
                path="/build/compute/plots/lab.png",
                mime="image/png",
                alt=concept,
                data_b64=str(payload["png_b64"]),
            )
        )
    elif payload.get("svg"):
        assets.append(
            ComputeAsset(
                path="/build/compute/plots/lab.svg",
                mime="image/svg+xml",
                alt=concept,
                data_b64=encode_svg_text(str(payload["svg"])),
            )
        )
    else:
        assets.append(stub_plot_asset(name="lab", alt=concept))

    return ComputeArtifact(
        seed=(dataset or {}).get("seed") if isinstance(dataset, dict) else None,
        dataset_path="/build/dataset.json" if dataset else None,
        dataset=dataset,
        trace=trace,
        chart_spec=payload.get("chart_spec"),
        assets=assets,
    )

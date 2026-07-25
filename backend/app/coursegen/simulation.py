"""Interaction model + simulation trace schemas and deterministic validators (tasks.md #25, #29, #30).

A simulation trace is precomputed data the browser artifact renders client-side (no runtime
sandbox — R6.6). The validators catch the failure modes that make a "simulation" fake or wrong:
empty/short steps, non-finite values, dimension mismatches, probabilities that don't sum to 1.
"""
from __future__ import annotations

import math

from pydantic import BaseModel


class LearnerControl(BaseModel):
    type: str  # slider | stepper | toggle
    name: str
    min: float | None = None
    max: float | None = None
    default: float | None = None


class InteractionModel(BaseModel):  # task 25
    concept: str
    learning_goal: str = ""
    source_chunk_ids: list[str] = []
    formula_steps: list[str] = []
    learner_controls: list[LearnerControl] = []
    visual_states: list[str] = []
    feedback: list[str] = []


class TraceStep(BaseModel):
    name: str
    values: list[float] = []


class SimulationTrace(BaseModel):  # task 29
    trace_id: str
    concept: str
    source: str = "deterministic"  # deterministic | sandbox_verified
    runtime: str = "python"
    libraries: list[str] = []
    inputs: dict = {}
    steps: list[TraceStep] = []
    validation: dict = {}


def validate_trace(trace: SimulationTrace, *, probability_steps: list[str] | None = None) -> dict:
    """Deterministic trace validation (task 30). `probability_steps` names steps that must sum to 1."""
    failed: list[str] = []
    if not trace.steps:
        failed.append("trace has no steps")
    for s in trace.steps:
        if not s.values:
            failed.append(f"step '{s.name}' has no values")
            continue
        if any((v is None or math.isnan(v) or math.isinf(v)) for v in s.values):
            failed.append(f"step '{s.name}' has non-finite values")
    lengths = {len(s.values) for s in trace.steps if s.values}
    if len(lengths) > 1:
        failed.append(f"inconsistent step dimensions: {sorted(lengths)}")
    for name in probability_steps or []:
        step = next((s for s in trace.steps if s.name == name), None)
        if step and step.values and abs(sum(step.values) - 1.0) > 1e-3:
            failed.append(f"step '{name}' is not a probability distribution (sum={sum(step.values):.4f})")
    return {"passed": not failed, "failed": failed}

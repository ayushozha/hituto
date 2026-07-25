"""data-synthesizer role — seeded pedagogical datasets (no live APIs)."""
from __future__ import annotations

import hashlib
import math
from typing import Any


def _seed_int(concept: str, seed: int | None) -> int:
    if seed is not None:
        return int(seed) & 0x7FFFFFFF
    h = hashlib.md5((concept or "concept").encode()).hexdigest()
    return int(h[:8], 16) & 0x7FFFFFFF


def synthesize_dataset(*, concept: str, seed: int | None = None, n: int = 8) -> dict[str, Any]:
    """Deterministic fake dataset for pedagogy (reproducible by seed).

    Returns a JSON-serializable dict written conceptually to `/build/dataset.json`.
    """
    s = _seed_int(concept, seed)
    # Simple LCG for offline reproducibility without numpy.
    state = s or 1

    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    labels = [f"t{i}" for i in range(n)]
    # Softmax-ish curve shaped by concept hash so different concepts differ.
    phase = (s % 360) * math.pi / 180.0
    raw = [math.sin(phase + i * 0.7) + 0.15 * rnd() for i in range(n)]
    shift = min(raw)
    vals = [round(v - shift + 0.05, 4) for v in raw]
    total = sum(vals) or 1.0
    probs = [round(v / total, 4) for v in vals]
    # Fix float drift on last bin.
    probs[-1] = round(1.0 - sum(probs[:-1]), 4)
    return {
        "seed": s,
        "concept": concept,
        "schema": {"labels": "str[]", "values": "float[]", "probs": "float[]"},
        "labels": labels,
        "values": vals,
        "probs": probs,
        "path": "/build/dataset.json",
    }


def data_synthesizer_subagent(subject: str | None = None) -> dict:
    """Deep Agent subagent dict: seeded dataset generation for data-driven lessons (§4)."""
    from ..prompt_loader import load_agent_prompt
    from ..tools import synthesize_dataset_tool

    return {
        "name": "data_synthesizer",
        "description": "Generate a seeded, schema-valid dataset for a simulation / data lesson.",
        "system_prompt": load_agent_prompt(
            "data_synthesizer",
            "You are the data synthesizer. Call synthesize_dataset_tool for the concept and write "
            "the returned JSON to /build/dataset.json. Datasets are illustrative and seeded for "
            "reproducibility — never present them as real measured data.",
        ),
        "tools": [synthesize_dataset_tool],
    }

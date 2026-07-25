"""Coursegen public façade — lesson generation + syllabus planning.

Services and API handlers import from here (or `app.coursegen`), not from `graph.py`
or `agents/` directly.
"""
from __future__ import annotations

from .agents.orchestrator import run_generation_via_orchestrator as run_generation
from .graph import recover_orphaned_generations, resume_generation, run_syllabus_planning

__all__ = [
    "recover_orphaned_generations",
    "resume_generation",
    "run_generation",
    "run_syllabus_planning",
]

"""Coursegen agents package — orchestrator, syllabus planner, role/subject subagents."""
from __future__ import annotations

from .orchestrator import deep_agents_enabled, run_generation_via_orchestrator
from .syllabus_planner import plan_free_topic_syllabus, plan_sourced_syllabus

__all__ = [
    "deep_agents_enabled",
    "plan_free_topic_syllabus",
    "plan_sourced_syllabus",
    "run_generation_via_orchestrator",
]

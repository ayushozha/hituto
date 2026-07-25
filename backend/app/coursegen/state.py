"""Typed pipeline state (design.md §3.2)."""
from __future__ import annotations

from typing import Literal, TypedDict

Archetype = Literal["explainer", "game", "simulation", "tool", "narrative"]


class GenState(TypedDict, total=False):
    course_id: str
    lesson_id: str
    topic: str
    knobs: dict
    plan: dict  # title, subtitle, archetype, difficulty, sections[], cover_prompt, facts[]
    citations: list[dict]
    html: str
    previous_html: str | None
    target_id: str | None
    target_html: str | None
    checks: dict
    attempts: int
    status: Literal["generating", "awaiting_review", "ready", "failed"]
    review_decision: dict  # set after HITL resume: {action, message?}
    error: str | None
    artifact_kind: Literal["html", "a2ui", "reading"]
    a2ui: dict  # trusted doc: RenderUiTool payload (a2ui) or ReadingDoc (reading)
    # --- source-grounded courses (specs/document-grounded-courses) ---
    source_document_id: str | None
    user_id: str
    source_query: str
    source_pack_chunk_ids: list[str]
    chapter_ids: list[str]
    grounding_repair: str
    compute_artifact: dict  # ComputeArtifact.model_dump() when asset_plan ran
    mesh_artifact: dict  # MeshArtifact.model_dump() when Hunyuan mesh ran
    # fast_gen Phase 2: interpret already ran research concurrently with planning,
    # so the research node short-circuits.
    research_done: bool

"""Shared document knowledge layer — ingest, retrieve, citations, lesson context."""

from .citations import (
    GroundingReview,
    build_repair_brief,
    check_grounding,
    review_grounding,
)
from .context import (
    ChapterContext,
    LessonRagContext,
    TeachingMapView,
    get_chapter_context,
    get_lesson_context,
    get_teaching_map,
    resolve_visual_candidates,
    validate_lesson_scopes,
)
from .ensure import backfill_maps, ensure_knowledge_tree, ensure_parse_artifacts
from .ingest import recover_orphaned_ingestions, run_source_ingestion, save_and_ingest
from .retrieve import SourceExcerpt, assemble_source_pack, retrieve_passages, search_source_pack

__all__ = [
    "ChapterContext",
    "GroundingReview",
    "LessonRagContext",
    "SourceExcerpt",
    "TeachingMapView",
    "assemble_source_pack",
    "backfill_maps",
    "build_repair_brief",
    "check_grounding",
    "ensure_knowledge_tree",
    "ensure_parse_artifacts",
    "get_chapter_context",
    "get_lesson_context",
    "get_teaching_map",
    "recover_orphaned_ingestions",
    "resolve_visual_candidates",
    "retrieve_passages",
    "review_grounding",
    "run_source_ingestion",
    "save_and_ingest",
    "search_source_pack",
    "validate_lesson_scopes",
]

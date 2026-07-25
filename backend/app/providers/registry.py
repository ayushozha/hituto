"""Resolve LLM, search, media, and embedding providers from config.

Production requires live credentials. Tests patch these getters with fakes (see tests/conftest.py).
"""
from __future__ import annotations

import os

from ..core.config import Settings, get_settings
from .embeddings import OpenAICompatEmbedding
from .llm import OpenAICompatLLM
from .media import get_image_media
from .mesh import resolve_mesh_provider
from .search import ExaSearch, YouComSearch


def _require(value: str, name: str) -> None:
    if not (value or "").strip():
        raise RuntimeError(f"{name} is required — set it in backend/.env")


def validate_provider_config(settings: Settings | None = None) -> None:
    """Fail fast at startup when required provider credentials are missing."""
    if os.environ.get("SKIP_PROVIDER_VALIDATION"):
        return
    s = settings or get_settings()
    errors: list[str] = []

    if not s.llm_api_key.strip():
        errors.append("LLM_API_KEY")
    sp = s.search_provider.lower()
    if sp == "exa":
        if not s.exa_api_key.strip():
            errors.append("EXA_API_KEY")
    elif sp in ("youcom", "you.com"):
        if not s.youcom_api_key.strip():
            errors.append("YOUCOM_API_KEY")
    else:
        errors.append(f"SEARCH_PROVIDER must be exa or youcom (got {s.search_provider!r})")
    image_key = (s.openai_image_api_key or s.openai_realtime_api_key or "").strip()
    if not image_key:
        errors.append("OPENAI_IMAGE_API_KEY (or OPENAI_API_KEY / OPENAI_REALTIME_API_KEY)")
    if s.vector_store == "pgvector" and not s.embedding_api_key.strip():
        errors.append("EMBEDDING_API_KEY (required when VECTOR_STORE=pgvector)")

    if errors:
        raise RuntimeError(
            "Missing required provider configuration in backend/.env:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )


def get_llm():
    _require(get_settings().llm_api_key, "LLM_API_KEY")
    return OpenAICompatLLM()


def get_tutor_llm():
    """LLM for the text tutor — uses TUTOR_LLM_* with fallback to LLM_*."""
    s = get_settings()
    key = s.resolved_tutor_llm_api_key()
    _require(key, "TUTOR_LLM_API_KEY / LLM_API_KEY")
    return OpenAICompatLLM(
        base_url=s.resolved_tutor_llm_base_url(),
        api_key=key,
        model=s.resolved_tutor_llm_model(),
    )


def get_coursegen_llm():
    """LLM for lesson/syllabus generation — uses COURSEGEN_LLM_* with fallback to LLM_*."""
    s = get_settings()
    key = s.resolved_coursegen_llm_api_key()
    _require(key, "COURSEGEN_LLM_API_KEY / LLM_API_KEY")
    return OpenAICompatLLM(
        base_url=s.resolved_coursegen_llm_base_url(),
        api_key=key,
        model=s.resolved_coursegen_llm_model(),
    )


def get_lesson_edit_llm():
    """LLM for surgical section/node edits — LESSON_EDIT_LLM_* → COURSEGEN_LLM_* → LLM_*."""
    s = get_settings()
    key = s.resolved_lesson_edit_llm_api_key()
    _require(key, "LESSON_EDIT_LLM_API_KEY / COURSEGEN_LLM_API_KEY / LLM_API_KEY")
    return OpenAICompatLLM(
        base_url=s.resolved_lesson_edit_llm_base_url(),
        api_key=key,
        model=s.resolved_lesson_edit_llm_model(),
    )


def get_coursegen_planner_llm():
    """Fast tier for syllabus/lesson planning (fast_gen Phase 7).

    COURSEGEN_PLANNER_LLM_* → COURSEGEN_LLM_* → LLM_*. Planning emits small structured
    JSON — a fast model here cuts a serial LLM call from every lesson's critical path.
    """
    s = get_settings()
    key = s.resolved_coursegen_planner_llm_api_key()
    _require(key, "COURSEGEN_PLANNER_LLM_API_KEY / COURSEGEN_LLM_API_KEY / LLM_API_KEY")
    return OpenAICompatLLM(
        base_url=s.resolved_coursegen_planner_llm_base_url(),
        api_key=key,
        model=s.resolved_coursegen_planner_llm_model(),
    )


def get_coursegen_review_llm():
    """Fast tier for the grounding review (fast_gen Phase 7).

    COURSEGEN_REVIEW_LLM_* → COURSEGEN_LLM_* → LLM_*. The review classifies claims
    against the source pack — structured output, no authoring.
    """
    s = get_settings()
    key = s.resolved_coursegen_review_llm_api_key()
    _require(key, "COURSEGEN_REVIEW_LLM_API_KEY / COURSEGEN_LLM_API_KEY / LLM_API_KEY")
    return OpenAICompatLLM(
        base_url=s.resolved_coursegen_review_llm_base_url(),
        api_key=key,
        model=s.resolved_coursegen_review_llm_model(),
    )


def get_search():
    s = get_settings()
    p = s.search_provider.lower()
    if p == "exa":
        _require(s.exa_api_key, "EXA_API_KEY")
        return ExaSearch()
    if p in ("youcom", "you.com"):
        _require(s.youcom_api_key, "YOUCOM_API_KEY")
        return YouComSearch()
    raise RuntimeError(f"Unsupported SEARCH_PROVIDER={s.search_provider!r}")


def get_media():
    s = get_settings()
    image_key = (s.openai_image_api_key or s.openai_realtime_api_key or "").strip()
    _require(image_key, "OPENAI_IMAGE_API_KEY / OPENAI_API_KEY / OPENAI_REALTIME_API_KEY")
    return get_image_media(s)


def get_mesh():
    """3D mesh provider — Pixal3D when configured, with legacy fallbacks."""
    return resolve_mesh_provider()


def get_embedder():
    _require(get_settings().embedding_api_key, "EMBEDDING_API_KEY")
    return OpenAICompatEmbedding()

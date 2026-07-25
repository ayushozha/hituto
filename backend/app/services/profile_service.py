"""Learner-profile store + the single preference→directive mapping both agents share.

coursegen (knobs snapshot) and the tutor (live read) must never drift apart, so the
prompt wording for every preference dimension lives here (specs/learner_profile §6).
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import LearnerProfile
from ..models.base import _now
from ..schemas.profile import LearningPreferences, ProfileHints, ProfileOut, ProfilePut


def get_or_create(db: Session, user_id: str) -> LearnerProfile:
    profile = db.get(LearnerProfile, user_id)
    if profile is None:
        profile = LearnerProfile(user_id=user_id)
        db.add(profile)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            profile = db.get(LearnerProfile, user_id)
            if profile is None:
                raise
        db.refresh(profile)
    return profile


def _preferences_of(profile: LearnerProfile) -> LearningPreferences:
    return LearningPreferences.model_validate(profile.preferences or {})


def default_hints(prefs: LearningPreferences) -> ProfileHints:
    """Course-creation form defaults derived from the profile (explicit user choices win)."""
    primary = prefs.modalities[0] if prefs.modalities else None
    design_mode = {"visual": "studio", "reading": "page"}.get(primary or "")
    archetype = {"hands_on": "simulation", "auditory": "narrative"}.get(primary or "")
    return ProfileHints(
        difficulty=prefs.prior_knowledge, design_mode=design_mode, archetype=archetype
    )


def profile_out(profile: LearnerProfile) -> ProfileOut:
    prefs = _preferences_of(profile)
    return ProfileOut(
        preferences=prefs,
        onboarded_at=profile.onboarded_at,
        updated_at=profile.updated_at,
        hints=default_hints(prefs),
    )


def update(db: Session, user_id: str, body: ProfilePut) -> ProfileOut:
    profile = get_or_create(db, user_id)
    profile.preferences = body.preferences.model_dump()
    profile.onboarded_at = _now()
    db.commit()
    db.refresh(profile)
    return profile_out(profile)


def get_preferences(db: Session, user_id: str) -> LearningPreferences | None:
    """Live read for personalization consumers — None unless onboarding completed/skipped."""
    profile = db.get(LearnerProfile, user_id)
    if profile is None or profile.onboarded_at is None:
        return None
    return _preferences_of(profile)


# --- preference → prompt mapping (specs/learner_profile §6) -----------------

_MODALITY_LABELS = {
    "visual": "visual (diagrams, spatial structure)",
    "auditory": "auditory (listening, discussion)",
    "reading": "reading/writing (text depth)",
    "hands_on": "hands-on (doing, interacting)",
}

_MODALITY_COURSEGEN = {
    "visual": "Lead key concepts with a diagram or canvas visualization; dual-code every "
    "concept (a visual plus a concise caption).",
    "auditory": "Write conversational explainer prose that reads well aloud.",
    "reading": "Go text-first and deep: precise definitions, a glossary, and summary blocks.",
    "hands_on": "Put interactive controls before explanations; give the learner sandbox-style "
    "tasks to try.",
}

_MODALITY_TUTOR = {
    "visual": "Explain with spatial/structural descriptions; offer rendered diagrams early.",
    "auditory": "Explain conversationally in short paragraphs with verbal analogies.",
    "reading": "Give thorough written explanations; define terms and use structured formatting.",
    "hands_on": "Guide the learner to try the on-screen controls; prefer interactive widgets "
    "over long prose.",
}

_STRUCTURE = {
    "examples_first": (
        "Present a worked example before each formal definition.",
        "Give a concrete example first, the formalism after.",
    ),
    "theory_first": (
        "Order sections concept → derivation → application.",
        "Explain the principle first, then illustrate it.",
    ),
}

_PACING = {
    "bite_sized": (
        "Keep sections short — one idea each.",
        "Keep answers short; offer to go deeper on request.",
    ),
    "deep_dive": (
        "Make sections dense and comprehensive.",
        "Detailed derivations and depth are welcome.",
    ),
}

_PRACTICE = {
    "frequent": (
        "Embed a short retrieval quiz or checkpoint in every section.",
        "Offer quick self-check questions often.",
    ),
    "minimal": (
        "Include at most one end-of-lesson check.",
        "Only quiz the learner when they ask.",
    ),
}

_PRIOR_KNOWLEDGE = {
    "beginner": (
        "Assume no background; build up from first principles.",
        "Avoid jargon; explain prerequisites as they come up.",
    ),
    "advanced": (
        "Assume strong background; skip the basics.",
        "Use precise technical vocabulary freely.",
    ),
}

_GOAL = {
    "exam": (
        "Optimize for exam coverage and practice.",
        "Frame explanations around what is examinable.",
    ),
    "career": (
        "Emphasize applied, project-style framing.",
        "Tie concepts to practical workplace use.",
    ),
    "school": (
        "Keep a supportive, structured classroom tone.",
        "Keep a supportive, structured classroom tone.",
    ),
}


def generation_context(prefs: LearningPreferences) -> dict:
    """Compact snapshot of the non-default choices — stored in course.knobs and tutor ctx.

    Only dimensions the user actually chose appear, so downstream prompts render nothing
    for untouched defaults.
    """
    defaults = LearningPreferences()
    context: dict = {}
    if prefs.modalities:
        context["modalities"] = list(prefs.modalities)
    for field in ("structure", "pacing", "practice", "prior_knowledge", "goal"):
        value = getattr(prefs, field)
        if value != getattr(defaults, field):
            context[field] = value
    return context


def prompt_lines(context: dict, *, consumer: Literal["coursegen", "tutor"]) -> list[str]:
    """Plain-language directives for one consumer, in a stable order."""
    idx = 0 if consumer == "coursegen" else 1
    lines: list[str] = []
    modalities = [m for m in (context.get("modalities") or []) if m in _MODALITY_LABELS]
    if modalities:
        labels = ", ".join(_MODALITY_LABELS[m] for m in modalities)
        lines.append(f"Preferred learning modalities (primary first): {labels}.")
        mapping = _MODALITY_COURSEGEN if consumer == "coursegen" else _MODALITY_TUTOR
        lines.extend(mapping[m] for m in modalities)
    for key, table in (
        ("structure", _STRUCTURE),
        ("pacing", _PACING),
        ("practice", _PRACTICE),
        ("prior_knowledge", _PRIOR_KNOWLEDGE),
        ("goal", _GOAL),
    ):
        value = context.get(key)
        if value in table:
            lines.append(table[value][idx])
    return lines


def summary_line(context: dict) -> str:
    """One-line rendering for the syllabus/lesson planner prompts."""
    parts: list[str] = []
    modalities = [m for m in (context.get("modalities") or []) if m in _MODALITY_LABELS]
    if modalities:
        parts.append("prefers " + " + ".join(m.replace("_", " ") for m in modalities) + " learning")
    for key in ("structure", "pacing", "practice", "prior_knowledge", "goal"):
        value = context.get(key)
        if isinstance(value, str) and value:
            parts.append(f"{key.replace('_', ' ')}={value.replace('_', ' ')}")
    if not parts:
        return ""
    return "Learner profile: " + "; ".join(parts) + "."

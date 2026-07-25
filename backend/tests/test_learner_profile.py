"""Learner profile (specs/learner_profile): store, mapping, and prompt injection."""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.coursegen.prompt import build_user_prompt
from app.models import LearnerProfile
from app.schemas.course import CreateCourse
from app.schemas.profile import LearningPreferences, ProfilePut
from app.services import course_service, insight_service, profile_service
from app.tutor.prompts_util import build_system_prompt


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


PREFS = LearningPreferences(
    modalities=["visual", "hands_on"],
    structure="examples_first",
    pacing="bite_sized",
    practice="frequent",
    prior_knowledge="beginner",
    goal="exam",
)


def _plan(learner_profile: dict | None = None) -> dict:
    plan = {
        "title": "Loop Engineering",
        "archetype": "explainer",
        "difficulty": "intermediate",
        "sections": [{"title": "The loop", "objective": "Trace one iteration."}],
        "interactions": [],
        "facts": [],
    }
    if learner_profile is not None:
        plan["learner_profile"] = learner_profile
    return plan


# --- store ------------------------------------------------------------------


def test_get_or_create_returns_unonboarded_defaults(tmp_path) -> None:
    with _session(tmp_path) as db:
        profile = profile_service.get_or_create(db, "user")
        assert profile.onboarded_at is None
        out = profile_service.profile_out(profile)
        assert out.preferences == LearningPreferences()
        assert out.onboarded_at is None
        # Not onboarded → personalization consumers see nothing (fail-closed).
        assert profile_service.get_preferences(db, "user") is None


def test_update_round_trips_and_unlocks_live_reads(tmp_path) -> None:
    with _session(tmp_path) as db:
        out = profile_service.update(db, "user", ProfilePut(preferences=PREFS, completed=True))
        assert out.onboarded_at is not None
        assert out.preferences == PREFS

        prefs = profile_service.get_preferences(db, "user")
        assert prefs == PREFS


def test_skip_path_sets_onboarded_with_default_preferences(tmp_path) -> None:
    with _session(tmp_path) as db:
        out = profile_service.update(db, "user", ProfilePut(completed=False))
        assert out.onboarded_at is not None
        assert out.preferences == LearningPreferences()
        # Skipped users get a live read, but the context is empty → no prompt changes.
        prefs = profile_service.get_preferences(db, "user")
        assert prefs is not None
        assert profile_service.generation_context(prefs) == {}


def test_profiles_are_isolated_per_user(tmp_path) -> None:
    with _session(tmp_path) as db:
        profile_service.update(db, "alice", ProfilePut(preferences=PREFS))
        assert profile_service.get_preferences(db, "bob") is None


def test_preferences_schema_rejects_unknown_keys_and_bad_values() -> None:
    with pytest.raises(ValidationError):
        LearningPreferences(modalities=["smell"])
    with pytest.raises(ValidationError):
        LearningPreferences(modalities=["visual"], learning_style="visual")
    with pytest.raises(ValidationError):
        LearningPreferences(modalities=["visual", "reading", "hands_on"])  # max 2


def test_delete_user_insights_also_deletes_profile(tmp_path) -> None:
    with _session(tmp_path) as db:
        profile_service.update(db, "user", ProfilePut(preferences=PREFS))
        insight_service.delete_user_insights(db, "user")
        assert db.get(LearnerProfile, "user") is None


# --- preference → prompt mapping --------------------------------------------


def test_generation_context_only_keeps_explicit_choices() -> None:
    context = profile_service.generation_context(PREFS)
    assert context == {
        "modalities": ["visual", "hands_on"],
        "structure": "examples_first",
        "pacing": "bite_sized",
        "practice": "frequent",
        "prior_knowledge": "beginner",
        "goal": "exam",
    }
    assert profile_service.generation_context(LearningPreferences()) == {}


def test_default_hints_follow_primary_modality_and_prior_knowledge() -> None:
    hints = profile_service.default_hints(PREFS)
    assert hints.difficulty == "beginner"
    assert hints.design_mode == "studio"
    assert hints.archetype is None

    hands_on = LearningPreferences(modalities=["hands_on"])
    assert profile_service.default_hints(hands_on).archetype == "simulation"

    reading = LearningPreferences(modalities=["reading"])
    assert profile_service.default_hints(reading).design_mode == "page"

    assert profile_service.default_hints(LearningPreferences()).design_mode is None


def test_prompt_lines_cover_both_consumers_and_skip_defaults() -> None:
    context = profile_service.generation_context(PREFS)
    coursegen = profile_service.prompt_lines(context, consumer="coursegen")
    tutor = profile_service.prompt_lines(context, consumer="tutor")

    assert any("worked example before each formal definition" in line for line in coursegen)
    assert any("retrieval quiz" in line for line in coursegen)
    assert any("diagram" in line for line in coursegen)  # visual modality directive
    assert any("concrete example first" in line for line in tutor)
    assert any("self-check" in line for line in tutor)
    assert coursegen != tutor  # consumer-specific wording

    assert profile_service.prompt_lines({}, consumer="coursegen") == []
    assert profile_service.prompt_lines({"structure": "balanced"}, consumer="tutor") == []


def test_summary_line_compacts_the_context() -> None:
    line = profile_service.summary_line(profile_service.generation_context(PREFS))
    assert line.startswith("Learner profile:")
    assert "visual + hands on" in line
    assert "exam" in line
    assert profile_service.summary_line({}) == ""


# --- coursegen prompt injection ---------------------------------------------


def test_build_user_prompt_renders_learner_block_only_when_present() -> None:
    plain = build_user_prompt(_plan())
    assert "LEARNER PROFILE" not in plain

    context = profile_service.generation_context(PREFS)
    adapted = build_user_prompt(_plan(learner_profile=context))
    assert "LEARNER PROFILE" in adapted
    assert "worked example before each formal definition" in adapted
    # Sections/brief content is untouched — the block is purely additive.
    assert "Include these sections:" in adapted


def test_build_lesson_plan_prompt_line_is_optional() -> None:
    from app.coursegen.planner import _learner_summary

    assert _learner_summary(None) == ""
    assert _learner_summary({}) == ""
    line = _learner_summary({"goal": "exam"})
    assert "exam" in line


def test_create_course_snapshots_profile_into_knobs(tmp_path, monkeypatch) -> None:
    # Don't kick off real syllabus planning; close the coroutine so none leaks un-awaited.
    monkeypatch.setattr(course_service, "spawn", lambda coro, **kwargs: coro.close())
    with _session(tmp_path) as db:
        profile_service.update(db, "user", ProfilePut(preferences=PREFS))
        course = course_service.create_course(db, "user", CreateCourse(topic="Biology"))
        assert course.knobs["learner_profile"]["goal"] == "exam"
        assert course.knobs["learner_profile"]["modalities"] == ["visual", "hands_on"]

        # Not onboarded → knobs unchanged.
        other = course_service.create_course(db, "stranger", CreateCourse(topic="Chemistry"))
        assert "learner_profile" not in other.knobs


# --- tutor prompt injection ---------------------------------------------------


def _ctx(learner_profile: dict | None = None) -> dict:
    ctx = {"lesson_title": "Cells", "lesson_objective": "", "lesson_archetype": "explainer"}
    if learner_profile is not None:
        ctx["learner_profile"] = learner_profile
    return ctx


def test_tutor_system_prompt_renders_learner_section_only_when_present() -> None:
    plain = build_system_prompt(_ctx())
    assert "LEARNER PROFILE" not in plain

    adapted = build_system_prompt(_ctx(learner_profile=profile_service.generation_context(PREFS)))
    assert "LEARNER PROFILE" in adapted
    assert "concrete example first" in adapted

"""Learner-profile request/response schemas (specs/learner_profile/design.md §4)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Modality = Literal["visual", "auditory", "reading", "hands_on"]
Structure = Literal["examples_first", "theory_first", "balanced"]
Pacing = Literal["bite_sized", "balanced", "deep_dive"]
Practice = Literal["frequent", "some", "minimal"]
PriorKnowledge = Literal["beginner", "intermediate", "advanced"]
Goal = Literal["curiosity", "exam", "career", "school"]


class LearningPreferences(BaseModel):
    """Evidence-informed preference dimensions — all defaulted so partial profiles validate."""

    model_config = ConfigDict(extra="forbid")

    # Ranked (first = primary), max 2. Presentation-mix preference, not a "learning style" label.
    modalities: list[Modality] = Field(default_factory=list, max_length=2)
    structure: Structure = "balanced"
    pacing: Pacing = "balanced"
    practice: Practice = "some"
    prior_knowledge: PriorKnowledge = "intermediate"
    goal: Goal = "curiosity"

    @field_validator("modalities")
    @classmethod
    def _dedupe_keep_order(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class ProfileHints(BaseModel):
    """Derived defaults for the course-creation form (authoritative mapping lives server-side)."""

    difficulty: PriorKnowledge = "intermediate"
    design_mode: str | None = None
    archetype: str | None = None


class ProfileOut(BaseModel):
    preferences: LearningPreferences
    onboarded_at: datetime | None
    updated_at: datetime
    hints: ProfileHints = ProfileHints()


class ProfilePut(BaseModel):
    """`completed=false` is the skip path: stores defaults, still sets onboarded_at."""

    model_config = ConfigDict(extra="forbid")

    preferences: LearningPreferences = LearningPreferences()
    completed: bool = True

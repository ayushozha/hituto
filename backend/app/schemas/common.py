"""Shared schema types: difficulty/depth/archetype literals + the course Knobs."""
from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

Difficulty = Literal["beginner", "intermediate", "advanced"]
Depth = Literal["single-page", "multi-lesson"]
Archetype = Literal["auto", "explainer", "simulation", "game", "tool", "narrative"]
# Capsule chrome / layout — orthogonal to archetype (pedagogy). User-facing: Design mode.
DesignMode = Literal["auto", "studio", "page", "slide"]
# Back-compat alias for older imports / OpenAPI clients.
Presentation = DesignMode
StudioMode = Literal["auto", "specimen", "simulation", "process-cutaway"]


class Knobs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    difficulty: Difficulty = "intermediate"
    depth: Depth = "single-page"
    style_theme: str | None = None  # e.g. "Classic", "Wizard Green"
    archetype: Archetype = "auto"
    # Capsule shell: studio (sidebars+canvas), page (scroll), slide (deck), or auto.
    # Stored as design_mode; `presentation` is accepted as a legacy alias.
    design_mode: DesignMode = Field(
        default="auto",
        validation_alias=AliasChoices("design_mode", "presentation"),
        serialization_alias="design_mode",
    )
    # Studio v2 interaction model; auto routes from the lesson objective.
    studio_mode: StudioMode = "auto"
    # Opt-in teacher approval before a generated lesson goes live (coursegen HITL).
    require_teacher_review: bool = False
    # Opt-in chapter-outline review before any lesson generates (course-authoring-flow).
    review_outline: bool = False
    # Hunyuan 3D mesh generation for structural biology / science lessons.
    needs_3d: bool | None = None
    subject: str | None = None  # e.g. "science" → science-specialist routing

    @property
    def presentation(self) -> DesignMode:
        """Legacy alias used by older coursegen call sites."""
        return self.design_mode

    @model_validator(mode="before")
    @classmethod
    def _prefer_design_mode(cls, data: object) -> object:
        if isinstance(data, dict) and "design_mode" not in data and "presentation" in data:
            data = {**data, "design_mode": data["presentation"]}
        return data

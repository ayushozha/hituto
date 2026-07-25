"""Chapter-outline HITL schemas (course-authoring-flow §3).

The OutlineDoc is the JSON contract between the outline planner, the review API,
and the frontend outline editor / chapter tabs. Chapter ids are stable across
revisions so human edits stay keyed to the same chapter.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OutlineLesson(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(default="", max_length=2000)
    archetype: str = "explainer"
    estimated_duration: str = "5m"
    # Grounded courses only: teaching-map chapter ids this lesson draws from.
    chapter_ids: list[str] = Field(default_factory=list)


class OutlineChapter(BaseModel):
    id: str = Field(min_length=1, max_length=64)  # stable across revisions, e.g. "ch-1"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)  # human-editable summary
    # Grounded courses only: teaching-map chapter ids backing this outline chapter.
    source_chapter_ids: list[str] = Field(default_factory=list)
    lessons: list[OutlineLesson] = Field(default_factory=list)


class OutlineDoc(BaseModel):
    version: int = 1  # doc format version
    revision: int = 0  # bumped on every agent revision / human edit
    status: Literal["outline_review", "approved"] = "outline_review"
    design: str = "page"  # resolved presentation: page | studio | slide
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(default="", max_length=1000)
    chapters: list[OutlineChapter] = Field(min_length=1)
    # Revision history (most recent last) fed back to the reviser for context.
    feedback_log: list[str] = Field(default_factory=list)

    @field_validator("chapters")
    @classmethod
    def _unique_chapter_ids(cls, v: list[OutlineChapter]) -> list[OutlineChapter]:
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("chapter ids must be unique")
        return v


class OutlineReviewRequest(BaseModel):
    """Teacher decision on a drafted outline — approve, direct edit, or ask for a revision."""

    action: Literal["approve", "edit", "revise"]
    outline: OutlineDoc | None = None  # required for action=edit
    feedback: str | None = Field(default=None, max_length=4000)  # required for action=revise

    @field_validator("feedback")
    @classmethod
    def _strip_feedback(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class OutlineOut(BaseModel):
    """GET /courses/{id}/outline response."""

    course_id: str
    course_status: str
    outline: OutlineDoc | None = None
    max_revisions: int

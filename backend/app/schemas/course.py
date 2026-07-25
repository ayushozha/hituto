"""Course request/response schemas (incl. the dashboard card projection)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .common import Archetype, DesignMode, Knobs
from .source import SourceRef


class CreateCourse(BaseModel):
    topic: str = Field(min_length=1, max_length=2000)
    knobs: Knobs = Knobs()

    @field_validator("topic")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("topic must not be empty")
        return v


class UpdateCourse(BaseModel):
    """Partial course update — currently title only (dashboard rename)."""

    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        return v


class AppendVideoSource(BaseModel):
    """Attach one analyzed video source as the next course chapter."""

    source_id: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class AppendChapter(BaseModel):
    """Add one generated chapter while inheriting the course design mode."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    archetype: Archetype = "auto"

    @field_validator("title", "description")
    @classmethod
    def _strip_chapter_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("chapter fields must not be empty")
        return value


class LessonOut(BaseModel):
    id: str
    ordinal: int
    title: str
    objective: str
    completed: bool
    status: str
    error: str | None = None
    estimated_duration: str
    archetype: str
    # 3-level roadmap grouping (null on topic courses = single implicit chapter)
    module_ordinal: int | None = None
    module_title: str | None = None
    # True when a public share link exists (the token itself is never exposed here)
    is_shared: bool = False


class CourseCard(BaseModel):
    """Dashboard card projection (design.md §6)."""

    id: str
    topic: str
    title: str | None
    archetype: str | None
    status: str
    error: str | None
    lesson_count: int
    completed_count: int
    # Dashboard card identity/meta (replaces the old AI-generated cover image).
    tagline: str | None = None
    estimated_minutes: int = 0
    design_mode: DesignMode = "auto"
    updated_at: datetime
    source: SourceRef | None = None  # present when the course was generated from a source doc


class CourseDetail(CourseCard):
    lessons: list[LessonOut]


class RefinementRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    lesson_id: str | None = None
    # Optional in-iframe selection for targeted AI refine
    target_id: str | None = Field(default=None, max_length=120)
    target_html: str | None = Field(default=None, max_length=14000)

    @field_validator("prompt")
    @classmethod
    def _strip_prompt(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty")
        return v

    @field_validator("target_html")
    @classmethod
    def _strip_target_html(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class SaveArtifactRequest(BaseModel):
    """Persist HTML edited in-iframe (Edit mode Save) — no LLM."""

    html: str = Field(min_length=1, max_length=2_000_000)


class PatchA2UISectionRequest(BaseModel):
    """Replace one A2UI section subtree (trusted path — no capsule gate)."""

    root: dict | None = Field(
        default=None, description="Replacement UiNode tree; omit when using instruction"
    )
    title: str | None = Field(default=None, max_length=200)
    instruction: str | None = Field(
        default=None,
        max_length=2000,
        description="Natural-language edit; server rewrites this section's tree",
    )
    insert: dict | None = Field(
        default=None,
        description="Catalogue insert: {type, hint?, placement?, index?}",
    )
    replace_node_path: list[int] | None = Field(
        default=None,
        description="Child-index path into the section root for subtree replace",
    )


class PatchHtmlSectionRequest(BaseModel):
    """Surgical HTML section refine — only the matched data-lesson-section is rewritten."""

    instruction: str = Field(min_length=1, max_length=2000)
    target_html: str | None = Field(default=None, max_length=14000)

    @field_validator("instruction")
    @classmethod
    def _strip_instruction(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("instruction must not be empty")
        return v

    @field_validator("target_html")
    @classmethod
    def _strip_target(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ArtifactVersionOut(BaseModel):
    id: str
    lesson_id: str
    version: int
    kind: str = "html"
    checks: dict
    created_at: datetime


class ArtifactA2UIOut(BaseModel):
    """Trusted A2UI document for lesson viewer (kind=a2ui)."""

    kind: Literal["a2ui"] = "a2ui"
    version: int
    title: str
    intent: str = ""
    root: dict
    sections: list[dict] = Field(default_factory=list)
    checks: dict = Field(default_factory=dict)


class ArtifactReadingOut(BaseModel):
    """Trusted reading companion for the lesson viewer (kind=reading).

    `doc` is a validated ReadingDoc (specs/design_agents step 4): verbatim source prose
    plus an annotation layer, rendered by trusted React — never through the capsule gate.
    """

    kind: Literal["reading"] = "reading"
    version: int
    doc: dict
    checks: dict = Field(default_factory=dict)


class ReviewLessonRequest(BaseModel):
    """Teacher approve/reject for HITL (`require_teacher_review`)."""

    action: Literal["approve", "reject"]
    message: str | None = Field(default=None, max_length=2000)


class ShareLinkOut(BaseModel):
    """Returned to the owner after minting a share link."""

    share_token: str


class SharedLessonOut(BaseModel):
    """Public, minimal lesson metadata for the read-only shared view.

    Deliberately excludes user_id, course_id, and ids — a share token exposes
    only what's needed to render a header above the artifact.
    """

    title: str
    archetype: str
    estimated_duration: str
    course_title: str | None = None

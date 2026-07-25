"""Document-grounded course request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .common import Difficulty, DesignMode, StudioMode


class SourceRef(BaseModel):
    """Lightweight source-document reference for the card/detail badge (document-grounded)."""

    id: str
    title: str | None = None
    filename: str
    source_type: str | None = None


class SourceOut(BaseModel):
    id: str
    filename: str
    mime_type: str
    # uploaded|transcribing|checkpointing|parsing|outlining|mapping|chunking|indexing|ready|failed
    status: str
    title: str | None = None
    source_type: str | None = None
    page_count: int | None = None
    duration_seconds: float | None = None
    checkpoint_count: int = 0
    error: str | None = None
    created_at: datetime


class SourceDetail(SourceOut):
    abstract: str | None = None
    extraction_quality: dict = {}
    chunk_count: int = 0


class SourceOutline(BaseModel):
    id: str
    title: str | None = None
    source_type: str | None = None
    page_count: int | None = None
    duration_seconds: float | None = None
    checkpoint_count: int = 0
    sections: list[str] = []
    warnings: list[str] = []
    suggested_modes: list[str] = []


class CreateSourceCourse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    difficulty: Difficulty = "intermediate"
    # Pricing: one course credit covers up to five interactive lessons.
    lesson_count: int = Field(5, ge=1, le=5)
    mode: str = "paper_walkthrough"
    selected_sections: list[str] = []
    style_theme: str | None = None
    design_mode: DesignMode = Field(
        default="auto",
        validation_alias=AliasChoices("design_mode", "presentation"),
        serialization_alias="design_mode",
    )
    studio_mode: StudioMode = "auto"
    # Opt-in chapter-outline review before lessons are created (course-authoring-flow).
    review_outline: bool = False

    @property
    def presentation(self) -> DesignMode:
        """Legacy alias for coursegen / older call sites."""
        return self.design_mode


class CreateVideoLinkSource(BaseModel):
    """Create a video-grounded source from a public URL (YouTube or direct media)."""

    url: HttpUrl
    title: str | None = Field(default=None, max_length=160)
    transcript: str | None = Field(default=None, max_length=500_000)


class LessonSourcePackOut(BaseModel):
    """A lesson's grounding pack for the viewer drawer (task 46)."""

    source_document_id: str
    retrieval_query: str = ""
    chunk_count: int = 0
    pages: list[int] = []
    sections: list[str] = []
    citations: list[dict] = []
    chapter_ids: list[str] = []


class VideoCheckpoint(BaseModel):
    """A transcript-grounded interaction unlocked by video playback."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", max_length=40)
    at_seconds: float = Field(ge=0)
    kind: Literal["quiz", "visual", "reading"]
    title: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=260)
    body: str = Field(default="", max_length=700)
    options: list[str] = Field(default_factory=list, max_length=4)
    answer_index: int | None = Field(default=None, ge=0, le=3)
    explanation: str = Field(default="", max_length=420)
    visual_points: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_quiz(self) -> "VideoCheckpoint":
        if self.kind == "quiz":
            if not 2 <= len(self.options) <= 4:
                raise ValueError("quiz checkpoints require 2 to 4 options")
            if self.answer_index is None or self.answer_index >= len(self.options):
                raise ValueError("quiz answer_index must point to an option")
        return self


class VideoCheckpointPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoints: list[VideoCheckpoint] = Field(min_length=1, max_length=10)


class VideoGuideOut(BaseModel):
    source_id: str
    title: str
    filename: str
    duration_seconds: float = Field(ge=0)
    transcript_provider: str = "deepgram"
    playback_kind: Literal["native", "youtube"] = "native"
    media_url: str | None = None
    youtube_video_id: str | None = None
    checkpoints: list[VideoCheckpoint] = Field(default_factory=list, max_length=10)


# kept here so `from .source import SourceRef` users (e.g. CourseCard) have no cycle
__all__ = [
    "SourceRef",
    "SourceOut",
    "SourceDetail",
    "SourceOutline",
    "CreateSourceCourse",
    "CreateVideoLinkSource",
    "LessonSourcePackOut",
    "VideoCheckpoint",
    "VideoCheckpointPlan",
    "VideoGuideOut",
]

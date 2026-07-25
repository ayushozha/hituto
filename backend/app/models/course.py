"""Course / Lesson / Artifact / Citation / GenerationRun models.

Maps to design.md §6. Artifacts are versioned so "regenerate" never destroys prior output (R7.2).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, _now, _uuid


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, default="dev", index=True)
    topic: Mapped[str] = mapped_column(Text)
    knobs: Mapped[dict] = mapped_column(JSON, default=dict)
    archetype: Mapped[str | None] = mapped_column(String, default=None)
    title: Mapped[str | None] = mapped_column(String, default=None)
    cover_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    # One-line course tagline shown on the dashboard card (the plan's LLM "subtitle").
    tagline: Mapped[str | None] = mapped_column(String, default=None)
    # generating|outline_review|ready|failed — outline_review is the HITL outline-approval state
    status: Mapped[str] = mapped_column(String, default="generating")
    # OutlineDoc draft/approved JSON when knobs.review_outline is set (course-authoring-flow §3)
    outline: Mapped[dict | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Lesson.ordinal"
    )
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String)
    objective: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[bool] = mapped_column(default=False)
    # pending|generating|awaiting_review|ready|failed — awaiting_review is HITL (not orphaned)
    status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    estimated_duration: Mapped[str] = mapped_column(String, default="5m")
    archetype: Mapped[str] = mapped_column(String, default="explainer")
    # 3-level roadmap (Course -> Chapter -> Lesson); null = ungrouped / single implicit chapter
    module_ordinal: Mapped[int | None] = mapped_column(Integer, default=None)
    module_title: Mapped[str | None] = mapped_column(String, default=None)
    # Opt-in public share: null = private; non-null = anyone with the link may read (R: public share)
    share_token: Mapped[str | None] = mapped_column(String, default=None, unique=True, index=True)

    course: Mapped[Course] = relationship(back_populates="lessons")
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="Artifact.version"
    )


class WhiteboardSession(Base):
    """Durable scene shared by one show_whiteboard tool call and its lesson agent."""

    __tablename__ = "whiteboard_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    tool_call_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, default="Whiteboard")
    intent: Mapped[str] = mapped_column(Text, default="")
    scene: Mapped[dict] = mapped_column(JSON, default=lambda: {"elements": []})
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class CodingLabSession(Base):
    """Durable coding-lab workspace shared by tutor/voice and the learner widget."""

    __tablename__ = "coding_lab_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    tool_call_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, default="Coding Lab")
    language: Mapped[str] = mapped_column(String, default="javascript")
    instructions: Mapped[str] = mapped_column(Text, default="")
    hint: Mapped[str | None] = mapped_column(Text, default=None)
    entrypoint: Mapped[str | None] = mapped_column(String, default=None)
    expected_stdout: Mapped[str | None] = mapped_column(Text, default=None)
    # {files: [{path, content}], last_run?: {...}}
    workspace: Mapped[dict] = mapped_column(JSON, default=lambda: {"files": []})
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # html (default) | a2ui — A2UI lessons store a validated component tree in `a2ui`
    kind: Mapped[str] = mapped_column(String, default="html")
    html: Mapped[str] = mapped_column(Text, default="")
    a2ui: Mapped[dict | None] = mapped_column(JSON, default=None)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    lesson: Mapped[Lesson] = relationship(back_populates="artifacts")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)

    course: Mapped[Course] = relationship(back_populates="citations")


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    stage_timings: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

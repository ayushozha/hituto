"""Lesson surface protocol (specs/design_agents §6) — peer of rag/, a2ui/, capsule/.

``build_surface(db, course, lesson)`` turns the lesson's *stored* form (latest artifact
+ source rows) into a design-agnostic :class:`LessonSurface`: grounding digest, section
outline, and control capabilities. Tutor and voice import only this module for lesson
grounding, so integrating them with any current or future design means implementing one
descriptor — never touching the agents.

Protocol-layer rules: pure reads over models, no agent imports, fail-soft (a lesson with
no artifact yet still yields a valid, empty-ish surface).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Artifact, Course, Lesson, LessonSourcePack, SourceDocument
from .digest import (
    ARTIFACT_DIGEST_CHARS,
    a2ui_to_text,
    html_outline,
    html_to_text,
    reading_to_text,
    video_guide_to_text,
)
from .model import LessonSurface, SectionRef, SurfaceCapabilities, SurfaceKind

__all__ = [
    "ARTIFACT_DIGEST_CHARS",
    "LessonSurface",
    "SectionRef",
    "SurfaceCapabilities",
    "SurfaceKind",
    "a2ui_to_text",
    "build_surface",
    "html_outline",
    "html_to_text",
    "reading_to_text",
    "video_guide_to_text",
]


def _video_block(db: Session, course: Course, lesson: Lesson) -> dict | None:
    """source_map['video'] for the lesson's source document, when it is a video."""
    pack = db.scalars(
        select(LessonSourcePack)
        .where(LessonSourcePack.lesson_id == lesson.id)
        .order_by(LessonSourcePack.created_at.desc())
        .limit(1)
    ).first()
    source_id = (
        pack.source_document_id if pack else (course.knobs or {}).get("source_document_id")
    )
    if not source_id:
        return None
    doc = db.get(SourceDocument, source_id)
    if not doc or doc.source_type != "video":
        return None
    return (doc.source_map or {}).get("video") or {}


def build_surface(db: Session, course: Course, lesson: Lesson) -> LessonSurface:
    """Latest artifact + source rows → surface. Pure read; never raises for a bare lesson."""
    latest = db.scalars(
        select(Artifact)
        .where(Artifact.lesson_id == lesson.id)
        .order_by(Artifact.version.desc())
        .limit(1)
    ).first()
    video = _video_block(db, course, lesson)

    if video is not None:
        # Video guide surface; a companion capsule (when generated) enriches the digest.
        companion = html_to_text(latest.html) if latest is not None and latest.html else ""
        digest = " ".join(p for p in (video_guide_to_text(video), companion) if p)
        return LessonSurface(
            kind="video",
            digest=digest[:ARTIFACT_DIGEST_CHARS],
            capabilities=SurfaceCapabilities(seek=True),
            artifact_version=latest.version if latest is not None else None,
        )

    if latest is None:
        return LessonSurface(kind="capsule")

    if (latest.kind or "html") == "reading":
        doc = latest.a2ui if isinstance(latest.a2ui, dict) else {}
        outline = [
            SectionRef(id=str(s.get("id") or ""), title=str(s.get("title") or ""))
            for s in doc.get("sections") or []
        ]
        return LessonSurface(
            kind="reading",
            digest=reading_to_text(doc),
            outline=outline,
            capabilities=SurfaceCapabilities(page_control=False, sections=bool(outline)),
            artifact_version=latest.version,
        )

    if (latest.kind or "html") == "a2ui":
        # Trusted node tree rendered in the host — no iframe runtime, no page tools.
        return LessonSurface(
            kind="a2ui",
            digest=a2ui_to_text(latest.a2ui),
            capabilities=SurfaceCapabilities(page_control=False),
            artifact_version=latest.version,
        )

    outline = [SectionRef(id=sid, title=title) for sid, title in html_outline(latest.html)]
    checks = latest.checks or {}
    return LessonSurface(
        kind="studio" if checks.get("presentation") == "studio" else "capsule",
        digest=html_to_text(latest.html),
        outline=outline,
        capabilities=SurfaceCapabilities(page_control=True, sections=bool(outline)),
        artifact_version=latest.version,
    )

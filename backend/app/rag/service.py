"""Document CRUD / status projections for api/v1/sources.py."""
from __future__ import annotations

from ..models import Course, SourceDocument
from ..schemas import CourseDetail, SourceDetail, SourceOut, SourceOutline, SourceRef
from ..services import course_service

SUGGESTED_MODES = ["paper_walkthrough", "textbook_chapter", "exam_prep", "code_lab", "math_lab"]


def source_out(d: SourceDocument) -> SourceOut:
    video = (d.source_map or {}).get("video") or {}
    return SourceOut(
        id=d.id,
        filename=d.filename,
        mime_type=d.mime_type,
        status=d.status,
        title=d.title,
        source_type=d.source_type,
        page_count=d.page_count,
        duration_seconds=video.get("duration_seconds"),
        checkpoint_count=len(video.get("checkpoints") or []),
        error=d.error,
        created_at=d.created_at,
    )


def source_detail(d: SourceDocument) -> SourceDetail:
    return SourceDetail(
        **source_out(d).model_dump(),
        abstract=d.abstract,
        extraction_quality=d.extraction_quality or {},
        chunk_count=len(d.chunks),
    )


def source_outline(d: SourceDocument) -> SourceOutline:
    sm = d.source_map or {}
    video = sm.get("video") or {}
    warnings: list[str] = []
    if (d.extraction_quality or {}).get("low_text"):
        warnings.append("low extracted text quality — results may be thin")
    tm = sm.get("teaching_map") or {}
    if not (tm.get("chapters") or sm.get("sections")):
        warnings.append("no teaching map or sections yet — finish ingestion or re-upload")
    elif tm.get("status") == "fallback":
        warnings.append("teaching map used fallback sequencing (no LLM map)")
    chapters = tm.get("chapters") or []
    sections = sm.get("sections") or [c.get("title") for c in chapters if c.get("title")]
    return SourceOutline(
        id=d.id,
        title=d.title,
        source_type=d.source_type,
        page_count=d.page_count,
        duration_seconds=video.get("duration_seconds"),
        checkpoint_count=len(video.get("checkpoints") or []),
        sections=sections,
        warnings=warnings,
        suggested_modes=SUGGESTED_MODES,
    )


def course_detail(c: Course) -> CourseDetail:
    lessons = [
        course_service.lesson_out(lesson)
        for lesson in sorted(c.lessons, key=lambda x: x.ordinal)
    ]
    return CourseDetail(
        id=c.id,
        topic=c.topic,
        title=c.title,
        archetype=c.archetype,
        status=c.status,
        error=c.error,
        lesson_count=len(c.lessons),
        completed_count=sum(1 for lesson in c.lessons if lesson.completed),
        tagline=c.tagline,
        updated_at=c.updated_at,
        lessons=lessons,
    )


def course_ref(d: SourceDocument) -> SourceRef:
    return SourceRef(id=d.id, title=d.title, filename=d.filename, source_type=d.source_type)

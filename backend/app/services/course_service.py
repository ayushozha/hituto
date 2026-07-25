"""Course business logic: card/detail projections, queries, and creation/orchestration.

Handlers pass already-fetched ORM objects (ownership/404 is an HTTP concern they keep);
these functions do the projection, querying, status transitions, and background scheduling.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.tasks import spawn
from ..coursegen import run_generation, run_syllabus_planning
from . import billing_service, profile_service
from ..models import (
    Artifact,
    Course,
    CourseSource,
    Lesson,
    LessonSourcePack,
    SourceChunk,
    SourceDocument,
)
from ..schemas import (
    ArtifactA2UIOut,
    ArtifactVersionOut,
    CourseCard,
    CourseDetail,
    CreateCourse,
    LessonOut,
    LessonSourcePackOut,
    SourceRef,
    UpdateCourse,
    VideoGuideOut,
)


# --- projections -----------------------------------------------------------

def lesson_out(lesson: Lesson) -> LessonOut:
    return LessonOut(
        id=lesson.id,
        ordinal=lesson.ordinal,
        title=lesson.title,
        objective=lesson.objective,
        completed=lesson.completed,
        status=lesson.status,
        error=lesson.error,
        estimated_duration=lesson.estimated_duration,
        archetype=lesson.archetype,
        module_ordinal=lesson.module_ordinal,
        module_title=lesson.module_title,
        is_shared=bool(lesson.share_token),
    )


def _lesson_minutes(value: str | None) -> int:
    """Parse a lesson's "10m"-style estimate to an int; default 5 when unparseable."""
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else 5


def card(c: Course) -> CourseCard:
    completed = sum(1 for lesson in c.lessons if lesson.completed)
    minutes = sum(_lesson_minutes(lesson.estimated_duration) for lesson in c.lessons)
    requested_design = str(
        (c.knobs or {}).get("design_mode") or (c.knobs or {}).get("presentation") or "auto"
    ).lower()
    design_mode = requested_design if requested_design in {"auto", "studio", "page", "slide"} else "auto"
    return CourseCard(
        id=c.id, topic=c.topic, title=c.title, archetype=c.archetype, status=c.status,
        error=c.error, lesson_count=len(c.lessons), completed_count=completed,
        tagline=c.tagline, estimated_minutes=minutes, design_mode=design_mode,
        updated_at=c.updated_at,
    )


def source_ref(db: Session, course: Course) -> SourceRef | None:
    sid = (course.knobs or {}).get("source_document_id")
    if not sid:
        return None
    s = db.get(SourceDocument, sid)
    if not s:
        return None
    return SourceRef(id=s.id, title=s.title, filename=s.filename, source_type=s.source_type)


def detail(db: Session, c: Course) -> CourseDetail:
    base = card(c).model_dump()
    src = source_ref(db, c)
    base["source"] = src.model_dump() if src else None
    base["lessons"] = [lesson_out(lesson) for lesson in c.lessons]
    return CourseDetail(**base)


# --- queries ---------------------------------------------------------------

def list_cards(db: Session, user_id: str, q: str | None, status: str | None) -> list[CourseCard]:
    stmt = select(Course).where(Course.user_id == user_id)
    if status:
        stmt = stmt.where(Course.status == status)
    rows = db.scalars(stmt.order_by(Course.updated_at.desc())).all()
    if q:
        needle = q.lower()
        rows = [c for c in rows if needle in c.topic.lower() or needle in (c.title or "").lower()]
    cards: list[CourseCard] = []
    for c in rows:
        cd = card(c)
        cd.source = source_ref(db, c)
        cards.append(cd)
    return cards


def lesson_source_pack(db: Session, lesson_id: str) -> LessonSourcePackOut | None:
    pack = db.scalars(
        select(LessonSourcePack)
        .where(LessonSourcePack.lesson_id == lesson_id)
        .order_by(LessonSourcePack.created_at.desc())
        .limit(1)
    ).first()
    if not pack:
        return None
    chunk_ids = pack.chunk_ids or []
    chapter_ids = list(pack.chapter_ids or [])
    chunks = db.scalars(select(SourceChunk).where(SourceChunk.id.in_(chunk_ids))).all() if chunk_ids else []
    pages = sorted({ch.page_start for ch in chunks if ch.page_start})
    sections: list[str] = []
    for ch in chunks:
        if ch.section_title and ch.section_title not in sections:
            sections.append(ch.section_title)
    # Chapter-materialized packs may have empty chunk_ids; surface chapter titles instead.
    if not sections and chapter_ids and pack.source_document_id:
        doc = db.get(SourceDocument, pack.source_document_id)
        tm_chs = ((doc.source_map or {}).get("teaching_map") or {}).get("chapters") or [] if doc else []
        by_id = {c.get("id"): c.get("title") for c in tm_chs if c.get("id")}
        for cid in chapter_ids:
            title = by_id.get(cid)
            if title and title not in sections:
                sections.append(title)
    # Prefer concrete retrieval hits; else chapter scope counts as the pack size.
    unit_count = len(chunk_ids) or len(chapter_ids)
    return LessonSourcePackOut(
        source_document_id=pack.source_document_id,
        retrieval_query=pack.retrieval_query or "",
        chunk_count=unit_count,
        pages=pages,
        sections=sections,
        citations=pack.citations or [],
        chapter_ids=chapter_ids,
    )


def _lesson_source_id(db: Session, course: Course, lesson_id: str | None = None) -> str | None:
    if lesson_id:
        pack = db.scalars(
            select(LessonSourcePack)
            .where(LessonSourcePack.lesson_id == lesson_id)
            .order_by(LessonSourcePack.created_at.desc())
            .limit(1)
        ).first()
        if pack:
            return pack.source_document_id
    return (course.knobs or {}).get("source_document_id")


def video_guide(
    db: Session, course: Course, lesson_id: str | None = None
) -> VideoGuideOut | None:
    source_id = _lesson_source_id(db, course, lesson_id)
    if not source_id:
        return None
    source = db.get(SourceDocument, source_id)
    if not source or source.source_type != "video":
        return None
    video = (source.source_map or {}).get("video") or {}
    return VideoGuideOut(
        source_id=source.id,
        title=source.title or source.filename,
        filename=source.filename,
        duration_seconds=float(video.get("duration_seconds") or 0),
        transcript_provider=str(video.get("transcript_provider") or "deepgram"),
        playback_kind=str(video.get("playback_kind") or "native"),
        media_url=video.get("external_url") if video.get("playback_kind") == "native" else None,
        youtube_video_id=video.get("youtube_video_id"),
        checkpoints=video.get("checkpoints") or [],
    )


def artifact_versions(db: Session, course: Course, lesson_id: str | None) -> list[ArtifactVersionOut]:
    lesson_ids = [lesson_id] if lesson_id else [lesson.id for lesson in course.lessons]
    if not lesson_ids:
        return []
    rows = db.scalars(
        select(Artifact)
        .where(Artifact.lesson_id.in_(lesson_ids))
        .order_by(Artifact.created_at.desc(), Artifact.version.desc())
    ).all()
    return [
        ArtifactVersionOut(
            id=a.id,
            lesson_id=a.lesson_id,
            version=a.version,
            kind=getattr(a, "kind", None) or "html",
            checks=a.checks or {},
            created_at=a.created_at,
        )
        for a in rows
    ]


def latest_artifact(db: Session, lesson_id: str, version: int | None = None) -> Artifact | None:
    stmt = select(Artifact).where(Artifact.lesson_id == lesson_id)
    if version is not None:
        stmt = stmt.where(Artifact.version == version)
    return db.scalars(stmt.order_by(Artifact.version.desc()).limit(1)).first()


def lesson_by_share_token(db: Session, token: str) -> Lesson | None:
    """Resolve a lesson from its public share token (the token IS the authorization).

    Returns None for an empty/blank token so a missing path segment can never match.
    Share links treat `awaiting_review` like not-ready (no public artifact yet).
    """
    if not token or not token.strip():
        return None
    lesson = db.scalars(select(Lesson).where(Lesson.share_token == token)).first()
    if lesson and lesson.status == "awaiting_review":
        return None
    return lesson


def first_lesson_latest_artifact(db: Session, course_id: str) -> Artifact | None:
    lesson = db.scalars(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.ordinal).limit(1)
    ).first()
    if not lesson:
        return None
    return db.scalars(
        select(Artifact).where(Artifact.lesson_id == lesson.id).order_by(Artifact.version.desc())
    ).first()


# --- creation / orchestration ---------------------------------------------

def create_course(
    db: Session,
    user_id: str,
    body: CreateCourse,
    *,
    plan_slug: str | None = None,
) -> Course:
    """Persist a new course and kick off multi-lesson syllabus planning."""
    billing_service.ensure_course_credit_available(db, user_id, plan_slug)
    knobs = body.knobs.model_dump(by_alias=True)
    # Learner profile (specs/learner_profile): snapshot the user's preferences into the
    # course knobs so generation stays reproducible if the profile changes later.
    prefs = profile_service.get_preferences(db, user_id)
    if prefs is not None:
        learner_profile = profile_service.generation_context(prefs)
        if learner_profile:
            knobs["learner_profile"] = learner_profile
    # Cap syllabus size to the pricing promise (one credit → up to N lessons).
    from .billing_plans import MAX_LESSONS_PER_COURSE_CREDIT

    knobs["max_lessons"] = MAX_LESSONS_PER_COURSE_CREDIT
    course = Course(user_id=user_id, topic=body.topic, knobs=knobs, status="generating")
    db.add(course)
    db.commit()
    db.refresh(course)
    # Spend the course credit when generation starts. With review_outline set the
    # course parks at outline_review first, and the credit is spent on approval
    # instead (pricing promise: reviewing the roadmap is free).
    if not bool(knobs.get("review_outline")):
        billing_service.spend_course_credit(db, user_id, course.id)
    spawn(run_syllabus_planning(course.id, course.topic, course.knobs), name=f"syllabus:{course.id}")
    return course


def append_video_source(
    db: Session,
    course: Course,
    source: SourceDocument,
    *,
    description: str | None = None,
) -> Lesson:
    """Append a ready video as one grounded chapter and start its companion generation."""
    if source.source_type != "video":
        raise ValueError("source must be a video")
    if source.status != "ready":
        raise ValueError("video analysis is not ready")
    if not (course.knobs or {}).get("video_sync"):
        raise ValueError("videos can only be added to a video course")

    duplicate = db.scalars(
        select(CourseSource).where(
            CourseSource.course_id == course.id,
            CourseSource.source_document_id == source.id,
        )
    ).first()
    if duplicate:
        raise ValueError("this video is already in the course")

    max_ordinal = db.scalar(select(func.max(Lesson.ordinal)).where(Lesson.course_id == course.id))
    max_module = db.scalar(
        select(func.max(Lesson.module_ordinal)).where(Lesson.course_id == course.id)
    )
    next_ordinal = int(max_ordinal if max_ordinal is not None else -1) + 1
    next_module = int(max_module if max_module is not None else -1) + 1
    title = (source.title or source.filename or "Video lesson").strip()
    source_map = source.source_map or {}
    teaching_chapters = ((source_map.get("teaching_map") or {}).get("chapters") or [])
    chapter_ids = [chapter["id"] for chapter in teaching_chapters if chapter.get("id")]
    excerpt = " ".join((source.abstract or source.full_text or "").split())[:240]
    cleaned_description = " ".join((description or "").split())
    objective = cleaned_description or f"Build intuition for {title} from the video"
    if excerpt and not cleaned_description:
        objective += f". {excerpt}"
    video = source_map.get("video") or {}
    duration_minutes = max(5, ceil(float(video.get("duration_seconds") or 0) / 60))

    lesson = Lesson(
        course_id=course.id,
        ordinal=next_ordinal,
        title=title,
        objective=objective,
        status="pending",
        estimated_duration=f"{duration_minutes}m",
        archetype="explainer",
        module_ordinal=next_module,
        module_title=f"Chapter {next_module + 1}: {title}",
    )
    db.add(lesson)
    db.flush()
    db.add(
        CourseSource(
            course_id=course.id,
            source_document_id=source.id,
            selected_sections=[],
            mode="video_companion",
        )
    )
    db.add(
        LessonSourcePack(
            lesson_id=lesson.id,
            source_document_id=source.id,
            chapter_ids=chapter_ids,
            chunk_ids=[],
            passage_ids=[],
            retrieval_query=f"{title}. {objective}",
            citations=[],
        )
    )

    knobs = dict(course.knobs or {})
    scopes = dict(knobs.get("lesson_scopes") or {})
    scopes[str(next_ordinal)] = {
        "chapter_ids": chapter_ids,
        "covers": cleaned_description or excerpt or title,
        "avoid": "",
    }
    source_ids = list(knobs.get("source_document_ids") or [])
    primary_source_id = knobs.get("source_document_id")
    for source_id in (primary_source_id, source.id):
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    knobs["lesson_scopes"] = scopes
    knobs["source_document_ids"] = source_ids
    course.knobs = knobs
    course.status = "ready"
    course.error = None
    db.commit()
    db.refresh(course)
    db.refresh(lesson)
    start_generation(db, course, lesson)
    return lesson


def append_chapter(
    db: Session,
    course: Course,
    *,
    title: str,
    description: str,
    archetype: str = "auto",
) -> Lesson:
    """Append a generated chapter that inherits the course's design settings."""
    knobs = dict(course.knobs or {})
    if knobs.get("video_sync"):
        raise ValueError("use the video chapter flow for this course")
    if course.status == "outline_review":
        raise ValueError("approve the course outline before adding a chapter")

    from .billing_plans import MAX_LESSONS_PER_COURSE_CREDIT

    existing = int(
        db.scalar(select(func.count()).select_from(Lesson).where(Lesson.course_id == course.id))
        or 0
    )
    if existing >= MAX_LESSONS_PER_COURSE_CREDIT:
        raise ValueError(
            f"this course already has {MAX_LESSONS_PER_COURSE_CREDIT} lessons — "
            "one course credit covers up to that many; start a new course for more"
        )

    from ..coursegen.planner import pick_archetype

    resolved_archetype = (
        archetype
        if archetype in {"explainer", "simulation", "game", "tool", "narrative"}
        else pick_archetype(f"{title} {description}")
    )
    max_ordinal = db.scalar(select(func.max(Lesson.ordinal)).where(Lesson.course_id == course.id))
    next_ordinal = int(max_ordinal if max_ordinal is not None else -1) + 1
    max_module = db.scalar(
        select(func.max(Lesson.module_ordinal)).where(Lesson.course_id == course.id)
    )
    modular_course = max_module is not None
    next_module = int(max_module) + 1 if modular_course else None
    duration = {
        "game": "10m",
        "simulation": "8m",
        "tool": "7m",
        "narrative": "7m",
    }.get(resolved_archetype, "5m")

    lesson = Lesson(
        course_id=course.id,
        ordinal=next_ordinal,
        title=title,
        objective=description,
        status="pending",
        estimated_duration=duration,
        archetype=resolved_archetype,
        module_ordinal=next_module,
        module_title=f"Chapter {next_module + 1}: {title}" if next_module is not None else None,
    )
    db.add(lesson)
    db.flush()

    source_document_id = knobs.get("source_document_id")
    if source_document_id:
        db.add(
            LessonSourcePack(
                lesson_id=lesson.id,
                source_document_id=source_document_id,
                chapter_ids=[],
                chunk_ids=[],
                passage_ids=[],
                retrieval_query=f"{title}. {description}",
                citations=[],
            )
        )
        scopes = dict(knobs.get("lesson_scopes") or {})
        scopes[str(next_ordinal)] = {
            "chapter_ids": [],
            "covers": description[:240],
            "avoid": "",
        }
        knobs["lesson_scopes"] = scopes
        course.knobs = knobs

    course.status = "ready"
    course.error = None
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(course)
    db.refresh(lesson)
    start_generation(db, course, lesson)
    return lesson


def update_course(db: Session, course: Course, body: UpdateCourse) -> CourseCard:
    """Rename a course (dashboard settings)."""
    course.title = body.title
    db.commit()
    db.refresh(course)
    return card(course)


def first_lesson(db: Session, course_id: str) -> Lesson | None:
    return db.scalars(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.ordinal).limit(1)
    ).first()


def start_generation(
    db: Session, course: Course, lesson: Lesson, *, refinement: str | None = None,
    mark_course: bool = False,
    target_id: str | None = None,
    target_html: str | None = None,
) -> bool:
    """Atomically claim a lesson and schedule one pipeline run.

    Returns False when another request or background path already claimed the lesson.
    """
    claimed = db.execute(
        update(Lesson)
        .where(Lesson.id == lesson.id, Lesson.status != "generating")
        .values(status="generating", error=None)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return False
    if mark_course:
        course.status = "generating"
        course.error = None
    db.commit()
    db.refresh(course)
    spawn(
        run_generation(
            course.id,
            lesson.id,
            course.topic,
            course.knobs,
            refinement=refinement,
            target_id=target_id,
            target_html=target_html,
        ),
        name=f"gen:{lesson.id}",
    )
    return True


def save_lesson_html(
    db: Session, course: Course, lesson: Lesson, html: str
) -> ArtifactVersionOut:
    """Persist in-iframe edited HTML after postprocess (no LLM)."""
    from ..capsule.postprocess import postprocess

    cleaned, checks = postprocess(html)
    from ..coursegen.studio_renderer import studio_artifact_metadata

    checks.update(studio_artifact_metadata(cleaned))
    if not checks.get("passed"):
        raise ValueError("; ".join(checks.get("failed") or ["postprocess failed"]))

    latest = db.scalars(
        select(Artifact).where(Artifact.lesson_id == lesson.id).order_by(Artifact.version.desc()).limit(1)
    ).first()
    version = (latest.version + 1) if latest else 1
    art = Artifact(
        lesson_id=lesson.id,
        version=version,
        kind="html",
        html=cleaned,
        a2ui=None,
        checks=checks,
    )
    db.add(art)
    lesson.status = "ready"
    lesson.error = None
    db.commit()
    db.refresh(art)
    return ArtifactVersionOut(
        id=art.id,
        lesson_id=art.lesson_id,
        version=art.version,
        kind=art.kind or "html",
        checks=art.checks or {},
        created_at=art.created_at,
    )


async def patch_a2ui_section(
    db: Session,
    lesson: Lesson,
    *,
    section_id: str,
    root: dict | None = None,
    title: str | None = None,
    instruction: str | None = None,
    insert: dict | None = None,
    replace_node_path: list[int] | None = None,
) -> ArtifactA2UIOut:
    """Replace one A2UI section (or insert/replace a node), re-normalize, version."""
    from ..a2ui import INSERTABLE_TYPES
    from ..coursegen.a2ui_sections import (
        author_insert_node,
        insert_node_into_section_root,
        patch_a2ui_section as _patch,
        replace_node_at_path,
        rewrite_a2ui_section_with_instruction,
    )

    latest = db.scalars(
        select(Artifact)
        .where(Artifact.lesson_id == lesson.id)
        .order_by(Artifact.version.desc())
        .limit(1)
    ).first()
    if not latest or (latest.kind or "html") != "a2ui" or not isinstance(latest.a2ui, dict):
        raise ValueError("lesson has no A2UI artifact to edit")
    doc = dict(latest.a2ui)
    sections = list(doc.get("sections") or [])
    if not sections and doc.get("root"):
        sections = [{"id": "main", "title": doc.get("title") or "Lesson", "root": doc["root"]}]
        doc["sections"] = sections
    current = next((s for s in sections if str(s.get("id")) == section_id), None)
    if current is None:
        raise ValueError(f"unknown section_id: {section_id}")
    if title:
        current["title"] = title

    new_root = root
    if insert:
        node_type = str(insert.get("type") or "").lower().strip()
        if node_type not in INSERTABLE_TYPES:
            raise ValueError(f"unknown catalogue type: {node_type or '(empty)'}")
        hint = str(insert.get("hint") or instruction or "").strip()
        node = await author_insert_node(node_type=node_type, hint=hint)
        if not node:
            raise ValueError("catalogue insert failed")
        placement = str(insert.get("placement") or "append")
        idx = insert.get("index")
        spliced = insert_node_into_section_root(
            current.get("root") or {},
            node,
            placement=placement,
            index=int(idx) if idx is not None else None,
        )
        if not spliced:
            raise ValueError("failed to splice catalogue node")
        new_root = spliced
    elif replace_node_path is not None and instruction and instruction.strip():
        # Rewrite only the addressed subtree, then splice back.
        from ..a2ui import normalize_ui_node

        cur_root = current.get("root") or {}
        # Walk to subtree for context
        node = cur_root
        for i in replace_node_path:
            kids = node.get("children") if isinstance(node, dict) else None
            if not isinstance(kids, list) or i < 0 or i >= len(kids):
                raise ValueError("invalid replace_node_path")
            node = kids[i]
        rewritten = await rewrite_a2ui_section_with_instruction(
            section_id=section_id,
            title=str(current.get("title") or section_id),
            current_root=node if isinstance(node, dict) else {},
            instruction=instruction.strip(),
        )
        if not rewritten:
            raise ValueError("node rewrite failed")
        # If model returned a full section stack, prefer its single child when path targets a leaf type
        leaf = normalize_ui_node(rewritten) or rewritten
        if (
            isinstance(leaf, dict)
            and leaf.get("type") == "stack"
            and len(leaf.get("children") or []) == 1
            and isinstance(node, dict)
            and node.get("type") != "stack"
        ):
            leaf = leaf["children"][0]
        new_root = replace_node_at_path(cur_root, list(replace_node_path), leaf)
        if not new_root:
            raise ValueError("failed to replace node at path")
    elif instruction and instruction.strip():
        rewritten = await rewrite_a2ui_section_with_instruction(
            section_id=section_id,
            title=str(current.get("title") or section_id),
            current_root=current.get("root") or {},
            instruction=instruction.strip(),
        )
        if not rewritten:
            raise ValueError("section rewrite failed")
        new_root = rewritten
    if not new_root:
        raise ValueError("root, instruction, or insert is required")
    patched = _patch(doc, section_id, new_root)
    if not patched:
        raise ValueError("invalid A2UI section tree or unknown section_id")
    version = latest.version + 1
    art = Artifact(
        lesson_id=lesson.id,
        version=version,
        kind="a2ui",
        html="",
        a2ui=patched,
        checks={"passed": True, "failed": [], "kind": "a2ui", "surgical": True},
    )
    db.add(art)
    lesson.status = "ready"
    lesson.error = None
    db.commit()
    db.refresh(art)
    out = art.a2ui if isinstance(art.a2ui, dict) else {}
    return ArtifactA2UIOut(
        version=art.version,
        title=str(out.get("title") or "Lesson"),
        intent=str(out.get("intent") or ""),
        root=out.get("root") or {"type": "stack", "props": {}, "children": []},
        sections=list(out.get("sections") or []),
        checks=art.checks or {},
    )


async def patch_html_section(
    db: Session,
    lesson: Lesson,
    *,
    section_id: str,
    instruction: str,
    target_html: str | None = None,
) -> ArtifactVersionOut:
    """Rewrite one HTML data-lesson-section; siblings unchanged; capsule gate; new version."""
    from ..coursegen.html_sections import (
        extract_section_outer,
        rewrite_html_section_with_instruction,
        splice_and_gate,
    )

    latest = db.scalars(
        select(Artifact)
        .where(Artifact.lesson_id == lesson.id)
        .order_by(Artifact.version.desc())
        .limit(1)
    ).first()
    if not latest or (latest.kind or "html") != "html" or not (latest.html or "").strip():
        raise ValueError("lesson has no HTML artifact to edit")
    current = extract_section_outer(latest.html, section_id)
    if not current:
        raise ValueError(f"unknown section_id: {section_id}")
    # Style hint from a sibling section — compact class tokens, not full HTML.
    from ..coursegen.html_sections import list_section_ids
    from ..lesson_edit import style_fingerprint

    sibling_hint = ""
    for sid in list_section_ids(latest.html):
        if sid == section_id:
            continue
        sib = extract_section_outer(latest.html, sid)
        if sib:
            sibling_hint = style_fingerprint(sib)
            if sibling_hint:
                break
    rewritten = await rewrite_html_section_with_instruction(
        section_id=section_id,
        current_html=current,
        instruction=instruction,
        target_snippet=target_html,
        sibling_style_hint=sibling_hint or None,
    )
    if not rewritten:
        raise ValueError("section rewrite failed")
    gated = splice_and_gate(latest.html, section_id, rewritten)
    if not gated:
        raise ValueError("failed to splice section")
    html, checks = gated
    if not checks.get("passed"):
        raise ValueError(f"capsule gate failed: {checks.get('failed')}")
    version = latest.version + 1
    art = Artifact(
        lesson_id=lesson.id,
        version=version,
        kind="html",
        html=html,
        a2ui=None,
        checks={**(checks or {}), "surgical": True, "section_id": section_id},
    )
    db.add(art)
    lesson.status = "ready"
    lesson.error = None
    db.commit()
    db.refresh(art)
    return ArtifactVersionOut(
        id=art.id,
        lesson_id=art.lesson_id,
        version=art.version,
        kind=art.kind or "html",
        checks=art.checks or {},
        created_at=art.created_at,
    )



def review_lesson(
    db: Session,
    course: Course,
    lesson: Lesson,
    *,
    action: str,
    message: str | None = None,
) -> None:
    """Resume HITL after teacher approve/reject. Raises ValueError if not awaiting review."""
    if lesson.status != "awaiting_review":
        raise ValueError("lesson is not awaiting review")
    if action not in ("approve", "reject"):
        raise ValueError("action must be approve or reject")
    from ..coursegen import resume_generation

    spawn(
        resume_generation(course.id, lesson.id, action=action, message=message),
        name=f"review:{lesson.id}",
    )


def complete_and_prefetch(db: Session, course: Course, lesson: Lesson) -> None:
    """Mark a lesson complete and JIT-prefetch the next pending lesson."""
    was_completed = lesson.completed
    lesson.completed = True
    if not was_completed:
        from . import insight_service

        insight_service.record_server_event(
            db,
            course.user_id,
            "lesson_completed",
            course_id=course.id,
            lesson_id=lesson.id,
            commit=False,
        )
        remaining = db.scalar(
            select(func.count(Lesson.id)).where(
                Lesson.course_id == course.id,
                Lesson.id != lesson.id,
                Lesson.completed.is_(False),
            )
        )
        if remaining == 0:
            insight_service.record_server_event(
                db,
                course.user_id,
                "course_completed",
                course_id=course.id,
                commit=False,
            )
    db.commit()
    next_lesson = db.scalars(
        select(Lesson)
        .where(Lesson.course_id == course.id, Lesson.ordinal == lesson.ordinal + 1)
        .limit(1)
    ).first()
    if next_lesson and next_lesson.status == "pending":
        next_lesson.status = "generating"
        db.commit()
        spawn(run_generation(course.id, next_lesson.id, course.topic, course.knobs), name=f"gen:{next_lesson.id}")
    db.refresh(course)

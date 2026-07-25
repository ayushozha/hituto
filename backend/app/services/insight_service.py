"""Personal learning event ingestion, deterministic metrics, and privacy controls."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..insights import generate_report
from ..models import (
    Course,
    InsightPreference,
    InsightSnapshot,
    LearnerProfile,
    LearningEvent,
    Lesson,
)
from ..schemas.insight import (
    DeleteInsightsResult,
    EventBatchResult,
    InsightAction,
    InsightEvidence,
    InsightItem,
    InsightMetrics,
    InsightPreferencesOut,
    InsightPreferencesPatch,
    InsightReport,
    InsightSummary,
    LearningInterest,
    LearningEventIn,
    LearningStruggle,
    RecentLearningActivity,
)

_CONTENT_KEYS = {"question", "answer", "content", "transcript", "selected_text"}
_ALLOWED_PAYLOAD_KEYS = {
    "artifact_version",
    "entry_source",
    "reason",
    "active_ms",
    "completion_source",
    "lesson_count",
    "score",
    "total",
    "attempt",
    "duration_ms",
    "intent",
    "widget_type",
    "control",
    "section_id",
    "response_ms",
    "status",
    "tool_name",
    "question",
    "concept",
}
_refreshing_users: set[tuple[str, str]] = set()
_insight_mutation_lock = threading.RLock()
_user_data_versions: dict[str, int] = {}
_INSIGHT_POLICY_VERSION = 2
_FORBIDDEN_AGENT_INFERENCES = (
    "great curiosity",
    "your curiosity",
    "you are curious",
    "you seem curious",
    "asking great questions",
    "great questions",
    "your engagement",
    "you are engaged",
    "highly engaged",
    "engaging so actively",
    "your motivation",
    "you are motivated",
    "highly motivated",
    "your intelligence",
    "you are smart",
    "you are talented",
    "your ability",
    "your learning style",
    "your attention",
    "you are focused",
    "your focus level",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def get_or_create_preferences(db: Session, user_id: str) -> InsightPreference:
    preference = db.get(InsightPreference, user_id)
    if preference is None:
        preference = InsightPreference(user_id=user_id)
        db.add(preference)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            preference = db.get(InsightPreference, user_id)
            if preference is None:
                raise
        db.refresh(preference)
    return preference


def preferences_out(preference: InsightPreference) -> InsightPreferencesOut:
    return InsightPreferencesOut(
        analytics_enabled=preference.analytics_enabled,
        question_content_enabled=preference.question_content_enabled,
        updated_at=preference.updated_at,
    )


def update_preferences(
    db: Session, user_id: str, patch: InsightPreferencesPatch
) -> InsightPreferencesOut:
    with _insight_mutation_lock:
        preference = get_or_create_preferences(db, user_id)
        if patch.analytics_enabled is not None:
            preference.analytics_enabled = patch.analytics_enabled
        if patch.question_content_enabled is not None:
            preference.question_content_enabled = patch.question_content_enabled
            if not patch.question_content_enabled:
                content_events = db.scalars(
                    select(LearningEvent).where(LearningEvent.user_id == user_id)
                ).all()
                for event in content_events:
                    if any(key in event.payload for key in _CONTENT_KEYS):
                        event.payload = {
                            key: value
                            for key, value in event.payload.items()
                            if key not in _CONTENT_KEYS
                        }
        preference.updated_at = _utcnow()
        db.commit()
        _user_data_versions[user_id] = _user_data_versions.get(user_id, 0) + 1
        db.refresh(preference)
        return preferences_out(preference)


def _owned_context(db: Session, user_id: str, event: LearningEventIn) -> bool:
    if event.course_id:
        course = db.get(Course, event.course_id)
        if course is None or course.user_id != user_id:
            return False
    if event.lesson_id:
        lesson = db.get(Lesson, event.lesson_id)
        if lesson is None or (event.course_id and lesson.course_id != event.course_id):
            return False
        course = db.get(Course, lesson.course_id)
        if course is None or course.user_id != user_id:
            return False
    return True


def _sanitize_payload(payload: dict, *, allow_question_content: bool) -> dict:
    sanitized = {key: value for key, value in payload.items() if key in _ALLOWED_PAYLOAD_KEYS}
    if not allow_question_content:
        for key in _CONTENT_KEYS:
            sanitized.pop(key, None)
    if question := sanitized.get("question"):
        sanitized["question"] = str(question)[:2000]
    return sanitized


def _delete_expired_events(db: Session, user_id: str) -> None:
    cutoff = _utcnow() - timedelta(days=get_settings().insights_raw_event_retention_days)
    db.execute(
        delete(LearningEvent).where(
            LearningEvent.user_id == user_id, LearningEvent.received_at < cutoff
        ).execution_options(synchronize_session=False)
    )


def record_events(db: Session, user_id: str, events: list[LearningEventIn]) -> EventBatchResult:
    settings = get_settings()
    preference = get_or_create_preferences(db, user_id)
    if not settings.insights_enabled or not preference.analytics_enabled:
        return EventBatchResult(accepted=0, duplicates=0)

    _delete_expired_events(db, user_id)

    event_ids = [event.event_id for event in events]
    existing = set(
        db.scalars(
            select(LearningEvent.event_id).where(
                LearningEvent.user_id == user_id, LearningEvent.event_id.in_(event_ids)
            )
        ).all()
    )
    accepted = 0
    duplicates = 0
    for event in events:
        if event.event_id in existing:
            duplicates += 1
            continue
        if not _owned_context(db, user_id, event):
            db.rollback()
            raise ValueError("event course or lesson is not owned by the current user")
        db.add(
            LearningEvent(
                event_id=event.event_id,
                user_id=user_id,
                course_id=event.course_id,
                lesson_id=event.lesson_id,
                session_id=event.session_id,
                event_type=event.event_type,
                source=event.source,
                authority="client",
                schema_version=event.schema_version,
                occurred_at=event.occurred_at,
                payload=_sanitize_payload(
                    event.payload, allow_question_content=preference.question_content_enabled
                ),
            )
        )
        existing.add(event.event_id)
        accepted += 1
    db.commit()
    return EventBatchResult(accepted=accepted, duplicates=duplicates)


def record_server_event(
    db: Session,
    user_id: str,
    event_type: str,
    *,
    course_id: str | None = None,
    lesson_id: str | None = None,
    payload: dict | None = None,
    source: str = "server",
    commit: bool = True,
) -> LearningEvent | None:
    preference = db.get(InsightPreference, user_id)
    analytics_enabled = preference.analytics_enabled if preference is not None else True
    question_content_enabled = (
        preference.question_content_enabled if preference is not None else False
    )
    if not get_settings().insights_enabled or not analytics_enabled:
        return None
    _delete_expired_events(db, user_id)
    event = LearningEvent(
        event_id=f"srv_{hashlib.sha256(f'{event_type}:{user_id}:{course_id}:{lesson_id}:{_utcnow().isoformat()}'.encode()).hexdigest()[:40]}",
        user_id=user_id,
        course_id=course_id,
        lesson_id=lesson_id,
        event_type=event_type,
        source=source,
        authority="server",
        schema_version=1,
        occurred_at=_utcnow(),
        payload=_sanitize_payload(
            payload or {}, allow_question_content=question_content_enabled
        ),
    )
    db.add(event)
    if commit:
        db.commit()
    return event


def _metrics(events: list[LearningEvent]) -> InsightMetrics:
    active_events = [
        event
        for event in events
        if event.event_type == "active_time_increment"
        and event.authority == "client"
        and event.source == "web"
    ]
    active_ms = sum(int(event.payload.get("active_ms", 0)) for event in active_events)
    active_by_day: dict[object, int] = {}
    for event in active_events:
        day = _aware(event.occurred_at).date()
        active_by_day[day] = active_by_day.get(day, 0) + int(event.payload.get("active_ms", 0))
    active_days = sum(day_ms >= 300_000 for day_ms in active_by_day.values())
    completed = {
        event.lesson_id
        for event in events
        if event.event_type == "lesson_completed"
        and event.authority == "server"
        and event.lesson_id
    }
    viewed = {
        event.lesson_id
        for event in events
        if event.event_type == "lesson_view_started"
        and event.authority == "client"
        and event.source == "web"
        and event.lesson_id
    }
    quizzes = [
        event
        for event in events
        if event.event_type == "quiz_submitted"
        and event.authority == "client"
        and event.source == "web"
    ]
    quiz_score = sum(int(event.payload.get("score", 0)) for event in quizzes)
    quiz_total = sum(int(event.payload.get("total", 0)) for event in quizzes)
    timed_quizzes = [
        event
        for event in quizzes
        if int(event.payload.get("duration_ms", 0)) > 0
        and int(event.payload.get("total", 0)) > 0
    ]
    timed_answers = sum(int(event.payload.get("total", 0)) for event in timed_quizzes)
    answer_duration_ms = sum(int(event.payload.get("duration_ms", 0)) for event in timed_quizzes)
    tutor_questions = [
        event
        for event in events
        if event.event_type == "tutor_question_asked" and event.authority == "server"
    ]
    tutor_responses = [
        event
        for event in events
        if event.event_type == "tutor_response_finished"
        and event.authority == "server"
        and event.payload.get("status", "completed") == "completed"
    ]
    tutor_response_times = [
        int(event.payload.get("response_ms", 0))
        for event in tutor_responses
        if int(event.payload.get("response_ms", 0)) > 0
    ]
    return InsightMetrics(
        active_minutes=round(active_ms / 60_000),
        active_days=active_days,
        lessons_viewed=len(viewed),
        lessons_completed=len(completed),
        tutor_questions=len(tutor_questions),
        tutor_responses=len(tutor_responses),
        average_tutor_response_seconds=(
            round(sum(tutor_response_times) / len(tutor_response_times) / 1000, 1)
            if tutor_response_times
            else None
        ),
        quiz_attempts=len(quizzes),
        answers_correct=quiz_score,
        answers_total=quiz_total,
        quiz_accuracy=round(quiz_score / quiz_total, 2) if quiz_total else None,
        average_answer_seconds=(
            round(answer_duration_ms / timed_answers / 1000, 1) if timed_answers else None
        ),
        hints_requested=sum(
            event.event_type == "hint_requested"
            and (
                event.authority == "server"
                or (event.authority == "client" and event.source == "web")
            )
            for event in events
        ),
        explanations_requested=sum(
            event.event_type == "explanation_requested" and event.authority == "server"
            for event in events
        ),
        practice_retries=sum(
            event.event_type == "practice_retried"
            and event.authority == "client"
            and event.source == "web"
            for event in events
        ),
    )


def _learning_profiles(
    db: Session, user_id: str, events: list[LearningEvent]
) -> tuple[list[LearningInterest], list[LearningStruggle], list[RecentLearningActivity]]:
    courses = list(
        db.scalars(
            select(Course).where(Course.user_id == user_id).order_by(Course.updated_at.desc())
        ).all()
    )
    lessons = list(
        db.scalars(
            select(Lesson).join(Course, Course.id == Lesson.course_id).where(Course.user_id == user_id)
        ).all()
    )
    course_map = {course.id: course for course in courses}
    lesson_map = {lesson.id: lesson for lesson in lessons}
    course_stats: dict[str, dict] = {}
    lesson_stats: dict[str, dict] = {}
    recent: list[RecentLearningActivity] = []

    for event in events:
        lesson = lesson_map.get(event.lesson_id or "")
        course_id = event.course_id or (lesson.course_id if lesson else None)
        course = course_map.get(course_id or "")
        if not course:
            continue
        is_active = (
            event.event_type == "active_time_increment"
            and event.authority == "client"
            and event.source == "web"
        )
        is_question = (
            event.event_type == "tutor_question_asked" and event.authority == "server"
        )
        is_quiz = (
            event.event_type == "quiz_submitted"
            and event.authority == "client"
            and event.source == "web"
        )
        is_view = (
            event.event_type == "lesson_view_started"
            and event.authority == "client"
            and event.source == "web"
        )
        is_completion = (
            event.event_type == "lesson_completed" and event.authority == "server"
        )
        if is_active or is_question or is_quiz or is_view or is_completion:
            course_stat = course_stats.setdefault(
                course.id,
                {
                    "active_ms": 0,
                    "questions": 0,
                    "answers": 0,
                    "views": 0,
                    "completions": 0,
                    "last_at": event.occurred_at,
                },
            )
            if _aware(event.occurred_at) > _aware(course_stat["last_at"]):
                course_stat["last_at"] = event.occurred_at
        else:
            course_stat = None
        if is_active and course_stat:
            course_stat["active_ms"] += int(event.payload.get("active_ms", 0))
        elif is_question and course_stat:
            course_stat["questions"] += 1
        elif is_quiz and course_stat:
            course_stat["answers"] += int(event.payload.get("total", 0))
        elif is_view and course_stat:
            course_stat["views"] += 1
        elif is_completion and course_stat:
            course_stat["completions"] += 1

        if lesson:
            lesson_stat = lesson_stats.setdefault(
                lesson.id,
                {
                    "course_id": course.id,
                    "score": 0,
                    "total": 0,
                    "attempts": 0,
                    "hints": 0,
                    "explanations": 0,
                    "retries": 0,
                },
            )
            if is_quiz:
                lesson_stat["score"] += int(event.payload.get("score", 0))
                lesson_stat["total"] += int(event.payload.get("total", 0))
                lesson_stat["attempts"] += 1
            elif event.event_type == "hint_requested" and (
                event.authority == "server"
                or (event.authority == "client" and event.source == "web")
            ):
                lesson_stat["hints"] += 1
            elif event.event_type == "explanation_requested" and event.authority == "server":
                lesson_stat["explanations"] += 1
            elif (
                event.event_type == "practice_retried"
                and event.authority == "client"
                and event.source == "web"
            ):
                lesson_stat["retries"] += 1

        title = lesson.title if lesson else (course.title or course.topic)
        href = (
            f"#dashboard/course/{course.id}/lesson/{lesson.id}"
            if lesson
            else f"#dashboard/course/{course.id}"
        )
        detail: str | None = None
        kind: Literal["lesson", "completion", "practice", "tutor"] = "lesson"
        if is_completion:
            detail, kind = "Completed this lesson", "completion"
        elif is_quiz:
            detail, kind = (
                f"Answered {int(event.payload.get('total', 0))} · "
                f"{int(event.payload.get('score', 0))} correct",
                "practice",
            )
        elif is_question:
            intent = str(event.payload.get("intent", "other")).replace("_", " ")
            detail, kind = f"Asked the tutor for {intent}", "tutor"
        elif is_view:
            detail, kind = "Opened this lesson", "lesson"
        if detail:
            recent.append(
                RecentLearningActivity(
                    kind=kind,
                    title=_bounded(title, 120),
                    detail=detail,
                    occurred_at=event.occurred_at,
                    course_id=course.id,
                    lesson_id=lesson.id if lesson else None,
                    href=href,
                )
            )

    interests: list[LearningInterest] = []
    ranked_courses = sorted(
        course_stats.items(),
        key=lambda item: (
            item[1]["active_ms"] / 60_000
            + item[1]["questions"] * 3
            + item[1]["answers"] * 0.5
            + item[1]["views"]
            + item[1]["completions"] * 2,
            _aware(item[1]["last_at"]),
        ),
        reverse=True,
    )
    for course_id, stat in ranked_courses[:3]:
        course = course_map[course_id]
        active_minutes = round(stat["active_ms"] / 60_000)
        signals = []
        if stat["active_ms"]:
            signals.append(f"{active_minutes} active min" if active_minutes else "<1 active min")
        if stat["questions"]:
            signals.append(f"{stat['questions']} tutor question{'s' if stat['questions'] != 1 else ''}")
        if stat["answers"]:
            signals.append(f"{stat['answers']} graded answers")
        if stat["completions"]:
            signals.append(
                f"{stat['completions']} lesson{'s' if stat['completions'] != 1 else ''} completed"
            )
        if stat["views"] and len(signals) < 3:
            signals.append(f"opened {stat['views']} time{'s' if stat['views'] != 1 else ''}")
        if not signals:
            signals.append("recent lesson activity")
        interests.append(
            LearningInterest(
                course_id=course.id,
                title=_bounded(course.title or course.topic, 120),
                evidence=" · ".join(signals)[:180],
                active_minutes=active_minutes,
                tutor_questions=stat["questions"],
                answers_total=stat["answers"],
                basis="activity",
            )
        )
    for course in courses:
        if len(interests) >= 3:
            break
        if any(item.course_id == course.id for item in interests):
            continue
        interests.append(
            LearningInterest(
                course_id=course.id,
                title=_bounded(course.title or course.topic, 120),
                evidence="On your course shelf",
                basis="course_selection",
            )
        )

    struggles: list[LearningStruggle] = []
    for lesson_id, stat in lesson_stats.items():
        total = stat["total"]
        if total < 3:
            continue
        accuracy = stat["score"] / total
        help_requests = stat["hints"] + stat["explanations"]
        if accuracy >= 0.6 or (help_requests == 0 and stat["retries"] == 0):
            continue
        lesson = lesson_map[lesson_id]
        evidence_parts = [f"{stat['score']}/{total} correct"]
        if help_requests:
            evidence_parts.append(f"{help_requests} help request{'s' if help_requests != 1 else ''}")
        if stat["retries"]:
            evidence_parts.append(f"{stat['retries']} retr{'ies' if stat['retries'] != 1 else 'y'}")
        struggles.append(
            LearningStruggle(
                course_id=stat["course_id"],
                lesson_id=lesson.id,
                title=_bounded(lesson.title, 120),
                evidence=" · ".join(evidence_parts)[:220],
                confidence=(
                    "high" if total >= 6 and help_requests + stat["retries"] >= 2 else "medium"
                ),
                answers_correct=stat["score"],
                answers_total=total,
                accuracy=round(accuracy, 2),
                quiz_attempts=stat["attempts"],
                help_requests=help_requests,
                retries=stat["retries"],
                href=f"#dashboard/course/{stat['course_id']}/lesson/{lesson.id}",
            )
        )
    struggles.sort(key=lambda item: (item.accuracy, -item.answers_total))
    recent.sort(key=lambda item: _aware(item.occurred_at), reverse=True)
    unique_recent: list[RecentLearningActivity] = []
    seen_recent: set[tuple[str, str | None, str]] = set()
    for item in recent:
        key = (item.kind, item.lesson_id or item.course_id, item.detail)
        if key in seen_recent:
            continue
        seen_recent.add(key)
        unique_recent.append(item)
        if len(unique_recent) == 5:
            break
    return interests[:3], struggles[:3], unique_recent


def _evidence(
    metrics: InsightMetrics,
    interests: list[LearningInterest],
    struggles: list[LearningStruggle],
) -> dict[str, InsightEvidence]:
    evidence = {
        "active_time": InsightEvidence(
            label="Active learning time", value=f"{metrics.active_minutes} min"
        ),
        "active_days": InsightEvidence(label="Active days", value=str(metrics.active_days)),
        "lessons": InsightEvidence(label="Lessons completed", value=str(metrics.lessons_completed)),
        "questions": InsightEvidence(label="Tutor questions", value=str(metrics.tutor_questions)),
        "answers": InsightEvidence(
            label="Correct answers",
            value=f"{metrics.answers_correct} of {metrics.answers_total}",
        ),
    }
    if metrics.quiz_accuracy is not None:
        evidence["accuracy"] = InsightEvidence(
            label="Practice accuracy", value=f"{round(metrics.quiz_accuracy * 100)}%"
        )
    if metrics.average_answer_seconds is not None:
        evidence["answer_speed"] = InsightEvidence(
            label="Average quiz answer time", value=f"{metrics.average_answer_seconds}s"
        )
    if metrics.average_tutor_response_seconds is not None:
        evidence["tutor_reply_time"] = InsightEvidence(
            label="Average tutor reply time",
            value=f"{metrics.average_tutor_response_seconds}s",
        )
    for index, interest in enumerate(interests):
        evidence[f"interest_{index}"] = InsightEvidence(
            label=f"Exploring {interest.title}", value=interest.evidence
        )
    for index, struggle in enumerate(struggles):
        evidence[f"struggle_{index}"] = InsightEvidence(
            label=f"Challenge in {struggle.title}", value=struggle.evidence
        )
    return evidence


def _deterministic_report(
    metrics: InsightMetrics,
    interests: list[LearningInterest],
    struggles: list[LearningStruggle],
) -> InsightReport:
    items: list[InsightItem] = []
    if struggles:
        struggle = struggles[0]
        items.append(
            InsightItem(
                kind="challenge",
                title=_bounded(f"Revisit {struggle.title}", 90),
                body=(
                    f"This is the clearest supported challenge right now: {struggle.evidence}. "
                    "Review one explanation, then try a short practice set."
                )[:280],
                evidence_keys=["struggle_0"],
            )
        )
    if metrics.lessons_completed:
        items.append(
            InsightItem(
                kind="achievement",
                title="Lessons are turning into real progress",
                body=f"You completed {metrics.lessons_completed} lesson{'s' if metrics.lessons_completed != 1 else ''} in this period.",
                evidence_keys=["lessons"],
            )
        )
    if not struggles and metrics.answers_total >= 5 and metrics.quiz_accuracy is not None:
        if metrics.quiz_accuracy >= 0.8:
            items.append(
                InsightItem(
                    kind="strength",
                    title="Practice is looking confident",
                    body="Your recent quiz answers show a strong grasp of the material you practiced.",
                    evidence_keys=["accuracy"],
                )
            )
    if interests and len(items) < 3:
        interest = interests[0]
        items.append(
            InsightItem(
                kind="habit",
                title=_bounded(f"You’re exploring {interest.title}", 90),
                body=f"The evidence is straightforward: {interest.evidence}.",
                evidence_keys=["interest_0"],
            )
        )
    if not items:
        items.append(
            InsightItem(
                kind="momentum",
                title="Your learning pulse is starting",
                body="Keep learning and Hi Tuto will turn your activity into useful, private patterns.",
                evidence_keys=["active_time", "active_days"],
            )
        )
    headline = "Here’s what your learning data shows"
    summary_parts = [f"{metrics.active_minutes} active minutes"]
    if metrics.answers_total:
        summary_parts.append(f"{metrics.answers_correct}/{metrics.answers_total} correct answers")
    if metrics.tutor_questions:
        summary_parts.append(f"{metrics.tutor_questions} tutor questions")
    summary = " · ".join(summary_parts) + "."
    return InsightReport(headline=headline, summary=summary, insights=items[:3])


def _insufficient_report(interests: list[LearningInterest]) -> InsightReport:
    interest_item = (
        InsightItem(
            kind="habit",
            title=_bounded(f"You’re exploring {interests[0].title}", 90),
            body=(
                "This comes from your course choices. Time, practice, and tutor patterns will "
                "make the feedback more specific."
            ),
            evidence_keys=["interest_0"],
        )
        if interests
        else InsightItem(
            kind="momentum",
            title="Start with one lesson",
            body="Active time, graded answers, and tutor questions will appear here as you learn.",
            evidence_keys=[],
        )
    )
    return InsightReport(
        headline="More evidence will sharpen this feedback",
        summary=(
            "The sidebar is already tracking observable activity. A few active minutes or graded "
            "answers are enough to start forming stronger patterns."
        ),
        insights=[interest_item],
    )


def _recommended_action(
    db: Session, user_id: str, struggles: list[LearningStruggle]
) -> InsightAction | None:
    if struggles:
        struggle = struggles[0]
        return InsightAction(
            label=_bounded(f"Review {struggle.title}", 60),
            href=struggle.href,
            course_id=struggle.course_id,
            lesson_id=struggle.lesson_id,
        )
    row = db.execute(
        select(Course, Lesson)
        .join(Lesson, Lesson.course_id == Course.id)
        .where(
            Course.user_id == user_id,
            Course.status == "ready",
            Lesson.completed.is_(False),
            Lesson.status == "ready",
        )
        .order_by(Course.updated_at.desc(), Lesson.ordinal.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    course, lesson = row
    return InsightAction(
        label=_bounded(f"Continue {lesson.title}", 60),
        href=f"#dashboard/course/{course.id}/lesson/{lesson.id}",
        course_id=course.id,
        lesson_id=lesson.id,
    )


def _fingerprint(
    metrics: InsightMetrics,
    interests: list[LearningInterest],
    struggles: list[LearningStruggle],
    window: str,
) -> str:
    raw = json.dumps(
        {
            "policy_version": _INSIGHT_POLICY_VERSION,
            "window": window,
            "metrics": metrics.model_dump(),
            "interests": [item.model_dump() for item in interests],
            "struggles": [item.model_dump() for item in struggles],
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _context(
    metrics: InsightMetrics,
    evidence: dict[str, InsightEvidence],
    interests: list[LearningInterest],
    struggles: list[LearningStruggle],
    supported_report: InsightReport,
) -> dict:
    return {
        "metrics": metrics.model_dump(),
        "evidence": {key: value.model_dump() for key, value in evidence.items()},
        "supported_interests": [item.model_dump() for item in interests],
        "supported_struggles": [item.model_dump() for item in struggles],
        "supported_observations": supported_report.model_dump(),
        "rules": {
            "private": True,
            "no_diagnosis": True,
            "no_sensitive_inference": True,
            "no_motivation_or_personality_inference": True,
            "timing_is_not_quality": True,
        },
    }


def _validated_agent_report(
    report: InsightReport | None,
    supported_report: InsightReport,
    allowed_evidence: set[str],
) -> InsightReport | None:
    if report is None:
        return None
    supported_items = {
        tuple(sorted(item.evidence_keys)): item for item in supported_report.insights
    }
    validated_items: list[InsightItem] = []
    for item in report.insights:
        evidence_key = tuple(sorted(item.evidence_keys))
        supported = supported_items.get(evidence_key)
        if (
            not evidence_key
            or not set(evidence_key) <= allowed_evidence
            or supported is None
            or item.kind != supported.kind
        ):
            return None
        body = item.body.casefold()
        if any(phrase in body for phrase in _FORBIDDEN_AGENT_INFERENCES):
            return None
        validated_items.append(
            item.model_copy(
                update={
                    "title": supported.title,
                    "kind": supported.kind,
                    "evidence_keys": supported.evidence_keys,
                }
            )
        )
    return InsightReport(
        headline=supported_report.headline,
        summary=supported_report.summary,
        insights=validated_items,
    )


def get_summary(db: Session, user_id: str, window: str = "7d") -> InsightSummary:
    settings = get_settings()
    preference = get_or_create_preferences(db, user_id)
    _delete_expired_events(db, user_id)
    db.commit()
    days = 30 if window == "30d" else 7
    since = _utcnow() - timedelta(days=days)
    events = list(
        db.scalars(
            select(LearningEvent)
            .where(LearningEvent.user_id == user_id, LearningEvent.occurred_at >= since)
            .order_by(LearningEvent.occurred_at.asc())
        ).all()
    )
    metrics = _metrics(events)
    if not settings.insights_enabled or not preference.analytics_enabled:
        return InsightSummary(
            window=window,
            status="disabled",
            generated_by="deterministic",
            metrics=metrics,
            evidence=_evidence(metrics, [], []),
            updated_at=preference.updated_at,
        )

    interests, struggles, recent_activity = _learning_profiles(db, user_id, events)
    evidence = _evidence(metrics, interests, struggles)
    recommended_action = _recommended_action(db, user_id, struggles)
    evidence_updated_at = _aware(events[-1].occurred_at) if events else preference.updated_at
    enough_data = bool(events) and (
        metrics.active_minutes >= 2
        or metrics.lessons_completed > 0
        or metrics.quiz_attempts > 0
        or metrics.tutor_questions > 0
    )
    if not enough_data:
        return InsightSummary(
            window=window,
            status="insufficient_data",
            generated_by="deterministic",
            metrics=metrics,
            report=_insufficient_report(interests),
            evidence=evidence,
            interests=interests,
            struggles=struggles,
            recent_activity=recent_activity,
            recommended_action=recommended_action,
            updated_at=evidence_updated_at,
        )

    fingerprint = _fingerprint(metrics, interests, struggles, window)
    snapshot = db.scalars(
        select(InsightSnapshot)
        .where(
            InsightSnapshot.user_id == user_id,
            InsightSnapshot.window == window,
            InsightSnapshot.evidence_fingerprint == fingerprint,
        )
        .order_by(InsightSnapshot.created_at.desc())
        .limit(1)
    ).first()
    report = (
        InsightReport.model_validate(snapshot.report)
        if snapshot
        else _deterministic_report(metrics, interests, struggles)
    )
    return InsightSummary(
        window=window,
        status="ready",
        generated_by=(
            "agent" if snapshot and snapshot.generator.startswith("agent") else "deterministic"
        ),
        metrics=metrics,
        report=report,
        evidence=evidence,
        interests=interests,
        struggles=struggles,
        recent_activity=recent_activity,
        recommended_action=recommended_action,
        updated_at=snapshot.created_at if snapshot else evidence_updated_at,
    )


async def refresh_snapshot(user_id: str, window: str = "7d") -> None:
    """Create an agent snapshot with its own request-independent DB session."""
    refresh_key = (user_id, window)
    with _insight_mutation_lock:
        if refresh_key in _refreshing_users or not get_settings().insights_agent_enabled:
            return
        _refreshing_users.add(refresh_key)
        data_version = _user_data_versions.get(user_id, 0)
    try:
        with SessionLocal() as db:
            summary = get_summary(db, user_id, window)
            if summary.status != "ready" or summary.generated_by == "agent":
                return
            fingerprint = _fingerprint(
                summary.metrics, summary.interests, summary.struggles, window
            )
            recent = db.scalars(
                select(InsightSnapshot)
                .where(
                    InsightSnapshot.user_id == user_id,
                    InsightSnapshot.window == window,
                    InsightSnapshot.generator == f"agent-v{_INSIGHT_POLICY_VERSION}",
                )
                .order_by(InsightSnapshot.created_at.desc())
                .limit(1)
            ).first()
            refresh_after = timedelta(minutes=get_settings().insights_agent_refresh_minutes)
            if recent and _utcnow() - _aware(recent.created_at) < refresh_after:
                return
            supported_report = _deterministic_report(
                summary.metrics, summary.interests, summary.struggles
            )
            agent_context = _context(
                summary.metrics,
                summary.evidence,
                summary.interests,
                summary.struggles,
                supported_report,
            )
            allowed_evidence = set(summary.evidence)

        report = _validated_agent_report(
            await generate_report(agent_context), supported_report, allowed_evidence
        )
        if report is None:
            return

        with _insight_mutation_lock:
            if _user_data_versions.get(user_id, 0) != data_version:
                return
            with SessionLocal() as db:
                preference = db.get(InsightPreference, user_id)
                if preference is None or not preference.analytics_enabled:
                    return
                current = get_summary(db, user_id, window)
                current_fingerprint = _fingerprint(
                    current.metrics, current.interests, current.struggles, window
                )
                if (
                    current.status != "ready"
                    or current.generated_by == "agent"
                    or current_fingerprint != fingerprint
                ):
                    return
                db.add(
                    InsightSnapshot(
                        user_id=user_id,
                        window=window,
                        evidence_fingerprint=fingerprint,
                        generator=f"agent-v{_INSIGHT_POLICY_VERSION}",
                        report=report.model_dump(),
                    )
                )
                db.commit()
    finally:
        with _insight_mutation_lock:
            _refreshing_users.discard(refresh_key)


def delete_user_insights(db: Session, user_id: str) -> DeleteInsightsResult:
    with _insight_mutation_lock:
        _user_data_versions[user_id] = _user_data_versions.get(user_id, 0) + 1
        events = (
            db.execute(delete(LearningEvent).where(LearningEvent.user_id == user_id)).rowcount or 0
        )
        snapshots = (
            db.execute(delete(InsightSnapshot).where(InsightSnapshot.user_id == user_id)).rowcount
            or 0
        )
        # Learner profile is user-owned personal data — deleted alongside insights.
        db.execute(delete(LearnerProfile).where(LearnerProfile.user_id == user_id))
        db.commit()
        return DeleteInsightsResult(deleted_events=events, deleted_snapshots=snapshots)


def trim_expired_events(db: Session, user_id: str) -> None:
    _delete_expired_events(db, user_id)
    db.commit()


def classify_question_intent(question: str) -> str:
    text = question.casefold()
    if any(token in text for token in ("hint", "clue", "nudge")):
        return "hint"
    if any(token in text for token in ("quiz", "test me", "practice question")):
        return "quiz"
    if any(token in text for token in ("example", "show me", "demonstrate")):
        return "example"
    if any(token in text for token in ("simpler", "simple terms", "easier", "eli5")):
        return "simplify"
    if any(token in text for token in ("diagram", "visual", "draw", "whiteboard")):
        return "visualize"
    if any(token in text for token in ("explain", "why", "how does", "what is")):
        return "explain"
    return "other"


def record_tutor_question(
    db: Session,
    user_id: str,
    course_id: str,
    lesson_id: str,
    question: str,
    source: str = "tutor",
) -> None:
    """Best-effort immediate hook; tutor availability never depends on analytics."""
    try:
        intent = classify_question_intent(question)
        record_server_event(
            db,
            user_id,
            "tutor_question_asked",
            course_id=course_id,
            lesson_id=lesson_id,
            payload={"intent": intent, "question": question},
            source=source,
        )
        if intent == "hint":
            record_server_event(
                db,
                user_id,
                "hint_requested",
                course_id=course_id,
                lesson_id=lesson_id,
                source=source,
            )
        elif intent in {"explain", "simplify", "example", "visualize"}:
            record_server_event(
                db,
                user_id,
                "explanation_requested",
                course_id=course_id,
                lesson_id=lesson_id,
                payload={"intent": intent},
                source=source,
            )
    except Exception:
        db.rollback()


def record_tutor_finished(
    db: Session,
    user_id: str,
    course_id: str,
    lesson_id: str,
    response_ms: int,
    source: str = "tutor",
    status: str = "completed",
) -> None:
    try:
        record_server_event(
            db,
            user_id,
            "tutor_response_finished",
            course_id=course_id,
            lesson_id=lesson_id,
            payload={"response_ms": max(0, response_ms), "status": status[:40]},
            source=source,
        )
    except Exception:
        db.rollback()

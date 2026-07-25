from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Course, LearningEvent, Lesson
from app.schemas.insight import InsightItem, InsightPreferencesPatch, InsightReport, LearningEventIn
from app.services import insight_service


def _event(
    event_id: str,
    event_type: str,
    payload: dict | None = None,
    *,
    source: str = "web",
) -> LearningEventIn:
    return LearningEventIn(
        event_id=event_id,
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        course_id="course",
        lesson_id="lesson",
        session_id="session_123",
        source=source,
        schema_version=1,
        payload=payload or {},
    )


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'insights.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    db.add(Course(id="course", user_id="user", topic="Biology", status="ready"))
    db.add(
        Lesson(
            id="lesson",
            course_id="course",
            title="Cells",
            status="ready",
            completed=False,
        )
    )
    db.commit()
    return db


def test_events_are_idempotent_private_and_drive_observability_metrics(tmp_path) -> None:
    with _session(tmp_path) as db:
        events = [
            _event("event_view", "lesson_view_started", {"entry_source": "dashboard"}),
            _event("event_active", "active_time_increment", {"active_ms": 60_000}),
            _event(
                "event_quiz",
                "quiz_submitted",
                {"score": 2, "total": 3, "attempt": 1, "duration_ms": 9_000},
            ),
            _event(
                "event_quiz",
                "quiz_submitted",
                {"score": 2, "total": 3, "attempt": 1, "duration_ms": 9_000},
            ),
        ]

        result = insight_service.record_events(db, "user", events)
        insight_service.record_server_event(
            db,
            "user",
            "lesson_completed",
            course_id="course",
            lesson_id="lesson",
            payload={"completion_source": "lesson"},
        )
        insight_service.record_tutor_question(
            db, "user", "course", "lesson", "What is a mitochondrion?"
        )
        insight_service.record_tutor_finished(
            db, "user", "course", "lesson", response_ms=2_400
        )

        assert result.accepted == 3
        assert result.duplicates == 1
        question = db.scalar(
            select(LearningEvent).where(
                LearningEvent.user_id == "user",
                LearningEvent.event_type == "tutor_question_asked",
            )
        )
        assert question is not None
        assert question.authority == "server"
        assert question.payload == {"intent": "explain"}

        summary = insight_service.get_summary(db, "user", "7d")
        assert summary.status == "ready"
        assert summary.private is True
        assert summary.metrics.active_minutes == 1
        assert summary.metrics.lessons_viewed == 1
        assert summary.metrics.lessons_completed == 1
        assert summary.metrics.quiz_attempts == 1
        assert summary.metrics.answers_correct == 2
        assert summary.metrics.answers_total == 3
        assert summary.metrics.quiz_accuracy == 0.67
        assert summary.metrics.average_answer_seconds == 3.0
        assert summary.metrics.tutor_questions == 1
        assert summary.metrics.tutor_responses == 1
        assert summary.metrics.average_tutor_response_seconds == 2.4
        assert summary.metrics.explanations_requested == 1
        assert summary.generated_by == "deterministic"


def test_interest_and_struggle_require_observable_corroborating_evidence(tmp_path) -> None:
    with _session(tmp_path) as db:
        insight_service.record_events(
            db,
            "user",
            [
                _event("focus_active", "active_time_increment", {"active_ms": 60_000}),
                _event(
                    "focus_quiz",
                    "quiz_submitted",
                    {"score": 1, "total": 4, "attempt": 1, "duration_ms": 12_000},
                ),
                _event("focus_retry", "practice_retried", {"attempt": 2}),
            ],
        )
        insight_service.record_tutor_question(
            db, "user", "course", "lesson", "Please explain cells in simpler terms"
        )

        summary = insight_service.get_summary(db, "user", "7d")

        assert summary.interests
        assert summary.interests[0].course_id == "course"
        assert summary.interests[0].title == "Biology"
        assert summary.interests[0].basis == "activity"
        assert summary.interests[0].active_minutes == 1
        assert summary.interests[0].answers_total == 4
        assert summary.interests[0].tutor_questions == 1

        assert len(summary.struggles) == 1
        struggle = summary.struggles[0]
        assert struggle.course_id == "course"
        assert struggle.lesson_id == "lesson"
        assert struggle.title == "Cells"
        assert struggle.answers_correct == 1
        assert struggle.answers_total == 4
        assert struggle.accuracy == 0.25
        assert struggle.quiz_attempts == 1
        assert struggle.help_requests == 1
        assert struggle.retries == 1
        assert "1/4 correct" in struggle.evidence
        assert "1 help request" in struggle.evidence
        assert "1 retry" in struggle.evidence
        assert summary.report is not None
        assert summary.report.insights[0].kind == "challenge"
        assert summary.report.insights[0].evidence_keys == ["struggle_0"]


def test_low_score_alone_is_not_labeled_as_a_struggle(tmp_path) -> None:
    with _session(tmp_path) as db:
        insight_service.record_events(
            db,
            "user",
            [
                _event(
                    "uncorroborated_quiz",
                    "quiz_submitted",
                    {"score": 1, "total": 4, "attempt": 1, "duration_ms": 8_000},
                )
            ],
        )

        summary = insight_service.get_summary(db, "user", "7d")

        assert summary.metrics.answers_correct == 1
        assert summary.metrics.answers_total == 4
        assert summary.struggles == []


def test_long_course_title_is_bounded_in_generated_feedback(tmp_path) -> None:
    with _session(tmp_path) as db:
        course = db.get(Course, "course")
        assert course is not None
        course.title = "A detailed guide to " + "cellular biology, " * 12
        db.commit()
        insight_service.record_events(
            db,
            "user",
            [_event("long_title_quiz", "quiz_submitted", {"score": 1, "total": 1})],
        )

        summary = insight_service.get_summary(db, "user", "7d")

        assert summary.report is not None
        assert all(len(item.title) <= 90 for item in summary.report.insights)


def test_failed_tutor_lifecycle_is_recorded_but_not_counted_as_a_reply(tmp_path) -> None:
    with _session(tmp_path) as db:
        insight_service.record_tutor_question(db, "user", "course", "lesson", "Explain cells")
        insight_service.record_tutor_finished(
            db, "user", "course", "lesson", response_ms=900, status="failed"
        )

        summary = insight_service.get_summary(db, "user", "7d")
        failed = db.scalar(
            select(LearningEvent).where(
                LearningEvent.user_id == "user",
                LearningEvent.event_type == "tutor_response_finished",
            )
        )

        assert failed is not None
        assert failed.payload == {"response_ms": 900, "status": "failed"}
        assert summary.metrics.tutor_questions == 1
        assert summary.metrics.tutor_responses == 0
        assert summary.metrics.average_tutor_response_seconds is None


def test_agent_report_must_rewrite_a_supported_observation_without_trait_inference() -> None:
    supported = InsightReport(
        headline="What the evidence shows",
        summary="3 of 4 answers were correct.",
        insights=[
            InsightItem(
                kind="habit",
                title="You’re exploring Biology",
                body="This topic has recorded activity.",
                evidence_keys=["interest_0"],
            )
        ],
    )
    safe = InsightReport(
        headline="Invented headline",
        summary="Invented summary",
        insights=[
            InsightItem(
                kind="habit",
                title="Invented title",
                body="Biology has been part of your recent recorded activity.",
                evidence_keys=["interest_0"],
            )
        ],
    )
    unsafe = safe.model_copy(
        update={
            "insights": [
                safe.insights[0].model_copy(
                    update={"body": "You are curious and engaging so actively with Biology."}
                )
            ]
        }
    )

    validated = insight_service._validated_agent_report(safe, supported, {"interest_0"})

    assert validated is not None
    assert validated.headline == supported.headline
    assert validated.summary == supported.summary
    assert validated.insights[0].title == supported.insights[0].title
    assert insight_service._validated_agent_report(unsafe, supported, {"interest_0"}) is None


@pytest.mark.parametrize(
    "event_type,payload",
    [
        ("lesson_completed", {"completion_source": "lesson"}),
        ("course_completed", {"lesson_count": 1}),
        ("tutor_question_asked", {"intent": "explain"}),
        ("tutor_response_finished", {"response_ms": 1_000}),
        ("explanation_requested", {"intent": "explain"}),
    ],
)
def test_client_event_schema_rejects_server_only_events(event_type, payload) -> None:
    with pytest.raises(ValidationError):
        _event("forged_event", event_type, payload)


@pytest.mark.parametrize("source", ["server", "tutor", "voice"])
def test_client_event_schema_rejects_server_owned_sources(source) -> None:
    with pytest.raises(ValidationError):
        _event("forged_source", "lesson_view_started", source=source)


def test_turning_off_question_content_scrubs_existing_text(tmp_path) -> None:
    with _session(tmp_path) as db:
        insight_service.update_preferences(
            db, "user", InsightPreferencesPatch(question_content_enabled=True)
        )
        insight_service.record_tutor_question(
            db, "user", "course", "lesson", "Please explain cell division"
        )
        stored = db.scalar(
            select(LearningEvent).where(
                LearningEvent.user_id == "user",
                LearningEvent.event_type == "tutor_question_asked",
            )
        )
        assert stored is not None and "question" in stored.payload

        insight_service.update_preferences(
            db, "user", InsightPreferencesPatch(question_content_enabled=False)
        )
        db.refresh(stored)
        assert stored.payload == {"intent": "explain"}


def test_deleting_insights_preserves_courses(tmp_path) -> None:
    with _session(tmp_path) as db:
        insight_service.record_events(
            db,
            "user",
            [_event("event_quiz", "quiz_submitted", {"score": 1, "total": 1})],
        )
        result = insight_service.delete_user_insights(db, "user")

        assert result.deleted_events == 1
        assert db.get(Course, "course") is not None
        assert db.scalar(select(LearningEvent)) is None


def test_cross_user_context_is_rejected_without_partial_insert(tmp_path) -> None:
    with _session(tmp_path) as db:
        foreign = Course(id="foreign", user_id="someone-else", topic="Private")
        foreign_lesson = Lesson(
            id="foreign-lesson", course_id="foreign", title="Private", status="ready"
        )
        db.add_all([foreign, foreign_lesson])
        db.commit()
        bad_event = LearningEventIn(
            event_id="event_foreign",
            event_type="lesson_view_started",
            occurred_at=datetime.now(timezone.utc),
            course_id="foreign",
            lesson_id="foreign-lesson",
            schema_version=1,
            payload={},
        )

        with pytest.raises(ValueError, match="not owned"):
            insight_service.record_events(db, "user", [bad_event])

        assert db.scalar(select(LearningEvent)) is None

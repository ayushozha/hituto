"""Strict contracts for personal-learning events, metrics, and insight reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LearningEventType = Literal[
    "lesson_view_started",
    "lesson_view_ended",
    "active_time_increment",
    "lesson_completed",
    "course_completed",
    "tutor_question_asked",
    "tutor_response_finished",
    "explanation_requested",
    "hint_requested",
    "widget_opened",
    "quiz_submitted",
    "practice_retried",
    "capsule_control_used",
    "capsule_section_viewed",
    "studio_mode_opened",
    "studio_part_selected",
    "studio_control_changed",
    "studio_playback_completed",
    "studio_reset",
    "studio_degraded",
]

_PAYLOAD_KEYS: dict[str, set[str]] = {
    "lesson_view_started": {"artifact_version", "entry_source"},
    "lesson_view_ended": {"reason"},
    "active_time_increment": {"active_ms"},
    "lesson_completed": {"completion_source"},
    "course_completed": {"lesson_count"},
    "tutor_question_asked": {"intent", "question"},
    "tutor_response_finished": {"response_ms", "status", "tool_name"},
    "explanation_requested": {"intent"},
    "hint_requested": {"concept"},
    "widget_opened": {"widget_type"},
    "quiz_submitted": {"score", "total", "attempt", "duration_ms"},
    "practice_retried": {"attempt", "duration_ms"},
    "capsule_control_used": {"control"},
    "capsule_section_viewed": {"section_id"},
    "studio_mode_opened": {"mode", "manifest_version"},
    "studio_part_selected": {"part_id"},
    "studio_control_changed": {"control_id", "value"},
    "studio_playback_completed": {"sequence_id"},
    "studio_reset": {"mode"},
    "studio_degraded": {"reason_code", "fallback_kind"},
}

_SERVER_ONLY_EVENT_TYPES = {
    "lesson_completed",
    "course_completed",
    "tutor_question_asked",
    "tutor_response_finished",
    "explanation_requested",
}
_CAPSULE_EVENT_TYPES = {
    "capsule_control_used",
    "capsule_section_viewed",
    "studio_mode_opened",
    "studio_part_selected",
    "studio_control_changed",
    "studio_playback_completed",
    "studio_reset",
    "studio_degraded",
}


class LearningEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=8, max_length=64)
    event_type: LearningEventType
    occurred_at: datetime
    course_id: str | None = Field(default=None, max_length=64)
    lesson_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    source: Literal["web", "capsule"] = "web"
    schema_version: Literal[1] = 1
    payload: dict = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        now = datetime.now(timezone.utc)
        utc_value = value.astimezone(timezone.utc)
        if (utc_value - now).total_seconds() > 300:
            raise ValueError("occurred_at cannot be more than 5 minutes in the future")
        return utc_value

    @model_validator(mode="after")
    def validate_payload(self) -> "LearningEventIn":
        if self.event_type in _SERVER_ONLY_EVENT_TYPES:
            raise ValueError(f"{self.event_type} is recorded by the server only")
        if self.event_type in _CAPSULE_EVENT_TYPES and self.source != "capsule":
            raise ValueError(f"{self.event_type} requires capsule source")
        if self.source == "capsule" and self.event_type not in _CAPSULE_EVENT_TYPES:
            raise ValueError("capsule source is limited to capsule interaction events")
        if len(str(self.payload)) > 12_000:
            raise ValueError("payload is too large")
        unknown = set(self.payload) - _PAYLOAD_KEYS[self.event_type]
        if unknown:
            raise ValueError(f"unsupported payload fields: {', '.join(sorted(unknown))}")
        if self.event_type == "active_time_increment":
            active_ms = self.payload.get("active_ms")
            if type(active_ms) is not int or not 1 <= active_ms <= 60_000:
                raise ValueError("active_time_increment requires active_ms between 1 and 60000")
        if self.event_type == "quiz_submitted":
            score = self.payload.get("score")
            total = self.payload.get("total")
            if type(score) is not int or type(total) is not int or total < 1:
                raise ValueError("quiz_submitted requires integer score and total")
            if score < 0 or score > total or total > 100:
                raise ValueError("quiz score must be between 0 and total")
        for key in ("attempt", "duration_ms", "response_ms"):
            value = self.payload.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{key} must be a non-negative integer")
        if type(self.payload.get("attempt")) is int and not 1 <= self.payload["attempt"] <= 100:
            raise ValueError("attempt must be between 1 and 100")
        if isinstance(self.payload.get("duration_ms"), int) and self.payload["duration_ms"] > 86_400_000:
            raise ValueError("duration_ms cannot exceed 24 hours")
        if isinstance(self.payload.get("response_ms"), int) and self.payload["response_ms"] > 600_000:
            raise ValueError("response_ms cannot exceed 10 minutes")
        for key in (
            "question",
            "intent",
            "control",
            "section_id",
            "widget_type",
            "mode",
            "manifest_version",
            "part_id",
            "control_id",
            "value",
            "sequence_id",
            "reason_code",
            "fallback_kind",
        ):
            value = self.payload.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 2000):
                raise ValueError(f"{key} must be bounded text")
        return self


class LearningEventBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[LearningEventIn] = Field(min_length=1, max_length=50)


class EventBatchResult(BaseModel):
    accepted: int
    duplicates: int


class InsightMetrics(BaseModel):
    active_minutes: int = 0
    active_days: int = 0
    lessons_viewed: int = 0
    lessons_completed: int = 0
    tutor_questions: int = 0
    tutor_responses: int = 0
    average_tutor_response_seconds: float | None = None
    quiz_attempts: int = 0
    answers_correct: int = 0
    answers_total: int = 0
    quiz_accuracy: float | None = None
    average_answer_seconds: float | None = None
    hints_requested: int = 0
    explanations_requested: int = 0
    practice_retries: int = 0


class InsightEvidence(BaseModel):
    label: str
    value: str


class InsightItem(BaseModel):
    kind: Literal["achievement", "momentum", "strength", "challenge", "habit"]
    title: str = Field(max_length=90)
    body: str = Field(max_length=280)
    evidence_keys: list[str] = Field(default_factory=list, max_length=4)


class InsightAction(BaseModel):
    label: str = Field(max_length=60)
    href: str = Field(max_length=300)
    course_id: str | None = None
    lesson_id: str | None = None


class LearningInterest(BaseModel):
    course_id: str
    title: str = Field(max_length=120)
    evidence: str = Field(max_length=180)
    active_minutes: int = 0
    tutor_questions: int = 0
    answers_total: int = 0
    basis: Literal["activity", "course_selection"]


class LearningStruggle(BaseModel):
    course_id: str
    lesson_id: str
    title: str = Field(max_length=120)
    evidence: str = Field(max_length=220)
    confidence: Literal["medium", "high"]
    answers_correct: int
    answers_total: int
    accuracy: float
    quiz_attempts: int
    help_requests: int
    retries: int
    href: str = Field(max_length=300)


class RecentLearningActivity(BaseModel):
    kind: Literal["lesson", "completion", "practice", "tutor"]
    title: str = Field(max_length=120)
    detail: str = Field(max_length=180)
    occurred_at: datetime
    course_id: str | None = None
    lesson_id: str | None = None
    href: str | None = Field(default=None, max_length=300)


class InsightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = Field(max_length=100)
    summary: str = Field(max_length=320)
    insights: list[InsightItem] = Field(min_length=1, max_length=3)


class InsightSummary(BaseModel):
    window: Literal["7d", "30d"]
    status: Literal["ready", "insufficient_data", "disabled"]
    private: Literal[True] = True
    generated_by: Literal["agent", "deterministic"]
    metrics: InsightMetrics
    report: InsightReport | None = None
    evidence: dict[str, InsightEvidence] = Field(default_factory=dict)
    interests: list[LearningInterest] = Field(default_factory=list, max_length=3)
    struggles: list[LearningStruggle] = Field(default_factory=list, max_length=3)
    recent_activity: list[RecentLearningActivity] = Field(default_factory=list, max_length=5)
    recommended_action: InsightAction | None = None
    updated_at: datetime


class InsightPreferencesOut(BaseModel):
    analytics_enabled: bool = True
    question_content_enabled: bool = False
    updated_at: datetime


class InsightPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analytics_enabled: bool | None = None
    question_content_enabled: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "InsightPreferencesPatch":
        if self.analytics_enabled is None and self.question_content_enabled is None:
            raise ValueError("at least one preference must be provided")
        return self


class DeleteInsightsResult(BaseModel):
    deleted_events: int
    deleted_snapshots: int

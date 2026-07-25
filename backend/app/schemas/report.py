"""Validated request and response contracts for progress-report handoff."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=2000)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceItem(_StrictModel):
    statement: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=4000)


class ReportContent(_StrictModel):
    learning_goals: list[ShortText] = Field(default_factory=list, max_length=20)
    work_completed: list[ShortText] = Field(default_factory=list, max_length=30)
    strengths: list[EvidenceItem] = Field(default_factory=list, max_length=20)
    support_areas: list[EvidenceItem] = Field(default_factory=list, max_length=20)
    teacher_observations: str = Field(default="", max_length=8000)
    next_actions: list[ShortText] = Field(default_factory=list, max_length=20)


class LearnerCreate(_StrictModel):
    display_alias: str = Field(min_length=1, max_length=120)
    grade_band: str | None = Field(default=None, max_length=80)


class ReportCreate(_StrictModel):
    author_display_name: str = Field(min_length=1, max_length=160)
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    content: ReportContent = Field(default_factory=ReportContent)
    learner_id: str | None = Field(default=None, min_length=1)
    learner: LearnerCreate | None = None

    @model_validator(mode="after")
    def _one_learner_source(self):
        if (self.learner_id is None) == (self.learner is None):
            raise ValueError("provide exactly one of learner_id or learner")
        if (
            self.reporting_period_start
            and self.reporting_period_end
            and self.reporting_period_start > self.reporting_period_end
        ):
            raise ValueError("reporting period start must be on or before the end")
        return self


class ReportPatch(_StrictModel):
    author_display_name: str | None = Field(default=None, min_length=1, max_length=160)
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    content: ReportContent | None = None

    @model_validator(mode="after")
    def _period_order(self):
        if (
            self.reporting_period_start
            and self.reporting_period_end
            and self.reporting_period_start > self.reporting_period_end
        ):
            raise ValueError("reporting period start must be on or before the end")
        return self


class LearnerOut(BaseModel):
    id: str
    display_alias: str
    grade_band: str | None


class ReportPermissions(BaseModel):
    can_edit: bool = False
    can_publish: bool = False
    can_invite: bool = False
    can_correct: bool = False
    can_acknowledge: bool = False
    can_print: bool = False
    can_manage_grants: bool = False


class ReportOut(BaseModel):
    id: str
    series_id: str
    learner: LearnerOut
    author_display_name: str
    author_account_ref: str
    reporting_period_start: date | None
    reporting_period_end: date | None
    status: Literal["draft", "published"]
    version: int
    supersedes_id: str | None
    schema_version: Literal[1]
    content: ReportContent
    evidence_mode: Literal["teacher_entered"]
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None = None
    permissions: ReportPermissions


class ReportInvitationOut(BaseModel):
    id: str
    token: str
    expires_at: datetime


class ReportPublishOut(BaseModel):
    report: ReportOut
    invitation: ReportInvitationOut | None


class InvitationClaimIn(_StrictModel):
    token: str = Field(min_length=32, max_length=512)
    target_learner_id: str | None = Field(default=None, min_length=1)


class GrantOut(BaseModel):
    id: str
    principal_user_id: str
    capability: str
    accepted_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    created_at: datetime


class AcknowledgementOut(BaseModel):
    acknowledged_at: datetime


class ReportHistoryOut(BaseModel):
    reports: list[ReportOut]
    events: list[AuditEventOut]

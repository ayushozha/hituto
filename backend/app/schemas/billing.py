"""Billing usage payloads (GET /billing/usage)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AllowanceOut(BaseModel):
    used: int
    total: int
    remaining: int


class BillingUsageOut(BaseModel):
    plan: str
    plan_slug: str
    is_free: bool = False
    # True when the backend blocks creation at zero remaining course credits.
    enforced: bool
    course_credits: AllowanceOut
    voice_minutes: AllowanceOut
    visuals: AllowanceOut
    lab_credits: AllowanceOut
    # Pricing promise: lessons included in one course credit.
    max_lessons_per_course: int = Field(default=5)
    renews_at: str

"""Credit ledger for Clerk-billed plan allowances (specs: PricingPage credit model).

One row per spent credit (or voice-minute batch). Balances are derived
(allowance − sum of units in the current calendar-month period), so there is no
mutable counter to drift.

Kinds:
  course  — one new course's generation kicked off (roadmap review is free)
  voice   — live voice-tutor minutes (units = whole minutes, min 1)
  visual  — newly generated AI lesson image
  lab     — custom AI-generated 3D mesh for a studio lesson
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now, _uuid


class CreditEvent(Base):
    __tablename__ = "credit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, default="dev", index=True)
    kind: Mapped[str] = mapped_column(String, default="course")
    # The course this credit paid for; used to keep course spends idempotent.
    course_id: Mapped[str | None] = mapped_column(String, default=None, index=True)
    # Calendar month the spend counts against, e.g. "2026-07".
    period: Mapped[str] = mapped_column(String, index=True)
    # Voice minutes / multi-unit spends; course/visual/lab usually 1.
    units: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

"""User-owned learner profile: onboarding-captured learning preferences (agent memory).

Semantic (declarative) memory — stable, user-declared preferences, as opposed to the
episodic `LearningEvent` stream. Consumed as a knobs snapshot by coursegen and live by
the tutor. See specs/learner_profile/design.md.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now


class LearnerProfile(Base):
    """One row per user; `onboarded_at is None` means onboarding never completed/skipped."""

    __tablename__ = "learner_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

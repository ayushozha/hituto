"""Course / voice / visual / lab credit metering.

Fail-open by default: metering always records, but creation is only blocked when
BILLING_ENFORCE is set, so a misconfigured allowance can never brick course
creation in dev or during rollout.

Plan allowances come from Clerk Billing JWT `pla` claims via billing_plans.py.
BILLING_COURSE_CREDITS remains a hard override for local demos when set to a
non-default and no plan slug is present.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import CreditEvent
from ..schemas.billing import AllowanceOut, BillingUsageOut
from .billing_plans import (
    MAX_LESSONS_PER_COURSE_CREDIT,
    PlanAllowances,
    allowances_for,
)


def _current_period(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _period_renews_at(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc).isoformat()


def resolve_plan(plan_slug: str | None) -> PlanAllowances:
    """Map a Clerk plan slug onto allowances; env override only for bare free demos."""
    plan = allowances_for(plan_slug)
    settings = get_settings()
    # Explicit env override wins when the JWT has no plan (legacy) — keep Early Explorer
    # as the catalog default, but let BILLING_COURSE_CREDITS force a local allowance.
    if not plan_slug and settings.billing_course_credits != 1:
        return PlanAllowances(
            slug=plan.slug,
            name=settings.billing_plan_name or plan.name,
            course_credits=max(0, settings.billing_course_credits),
            voice_minutes=plan.voice_minutes,
            visuals=plan.visuals,
            lab_credits=plan.lab_credits,
            is_free=plan.is_free,
        )
    if settings.billing_plan_name and plan.is_free:
        # Allow renaming the free tier display without changing allowances.
        if settings.billing_plan_name.strip() and settings.billing_plan_name != plan.name:
            return PlanAllowances(
                slug=plan.slug,
                name=settings.billing_plan_name.strip(),
                course_credits=plan.course_credits,
                voice_minutes=plan.voice_minutes,
                visuals=plan.visuals,
                lab_credits=plan.lab_credits,
                is_free=True,
            )
    return plan


def _units_used(db: Session, user_id: str, kind: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(CreditEvent.units), 0)).where(
                CreditEvent.user_id == user_id,
                CreditEvent.kind == kind,
                CreditEvent.period == _current_period(),
            )
        )
        or 0
    )


def _allowance(used: int, total: int) -> AllowanceOut:
    total = max(0, total)
    used = max(0, used)
    return AllowanceOut(used=used, total=total, remaining=max(0, total - used))


def course_credits_used(db: Session, user_id: str) -> int:
    return _units_used(db, user_id, "course")


def usage_out(db: Session, user_id: str, plan_slug: str | None = None) -> BillingUsageOut:
    settings = get_settings()
    plan = resolve_plan(plan_slug)
    return BillingUsageOut(
        plan=plan.name,
        plan_slug=plan.slug,
        is_free=plan.is_free,
        enforced=settings.billing_enforce,
        course_credits=_allowance(course_credits_used(db, user_id), plan.course_credits),
        voice_minutes=_allowance(_units_used(db, user_id, "voice"), plan.voice_minutes),
        visuals=_allowance(_units_used(db, user_id, "visual"), plan.visuals),
        lab_credits=_allowance(_units_used(db, user_id, "lab"), plan.lab_credits),
        max_lessons_per_course=MAX_LESSONS_PER_COURSE_CREDIT,
        renews_at=_period_renews_at(),
    )


def ensure_course_credit_available(
    db: Session, user_id: str, plan_slug: str | None = None
) -> None:
    """Raise ValueError when enforcement is on and the allowance is exhausted."""
    settings = get_settings()
    if not settings.billing_enforce:
        return
    plan = resolve_plan(plan_slug)
    if course_credits_used(db, user_id) >= max(0, plan.course_credits):
        raise ValueError(
            "no course credits left this month — upgrade your plan to keep creating"
        )


def ensure_voice_minutes_available(
    db: Session, user_id: str, plan_slug: str | None = None, need: int = 1
) -> None:
    settings = get_settings()
    if not settings.billing_enforce:
        return
    plan = resolve_plan(plan_slug)
    if _units_used(db, user_id, "voice") + max(1, need) > max(0, plan.voice_minutes):
        raise ValueError(
            "no voice minutes left this month — upgrade your plan to keep talking"
        )


def ensure_lab_credit_available(
    db: Session, user_id: str, plan_slug: str | None = None
) -> None:
    settings = get_settings()
    if not settings.billing_enforce:
        return
    plan = resolve_plan(plan_slug)
    if plan.lab_credits <= 0 or _units_used(db, user_id, "lab") >= plan.lab_credits:
        raise ValueError(
            "no 3D lab credits left this month — upgrade your plan for custom meshes"
        )


def spend_course_credit(db: Session, user_id: str, course_id: str) -> None:
    """Record one course-credit spend; idempotent per course."""
    existing = db.scalars(
        select(CreditEvent).where(
            CreditEvent.kind == "course", CreditEvent.course_id == course_id
        )
    ).first()
    if existing is not None:
        return
    db.add(
        CreditEvent(
            user_id=user_id,
            kind="course",
            course_id=course_id,
            period=_current_period(),
            units=1,
        )
    )
    db.commit()


def refund_course_credit(db: Session, course_id: str) -> None:
    """Drop the course-credit row when generation fails before any lesson ships.

    Matches the pricing promise that a failed generation does not consume the credit.
    """
    row = db.scalars(
        select(CreditEvent).where(
            CreditEvent.kind == "course", CreditEvent.course_id == course_id
        )
    ).first()
    if row is None:
        return
    db.delete(row)
    db.commit()


def spend_units(
    db: Session,
    user_id: str,
    kind: str,
    units: int = 1,
    *,
    course_id: str | None = None,
) -> None:
    """Append a metered spend (voice minutes, visuals, lab credits)."""
    units = max(1, int(units))
    db.add(
        CreditEvent(
            user_id=user_id,
            kind=kind,
            course_id=course_id,
            period=_current_period(),
            units=units,
        )
    )
    db.commit()


def spend_voice_minutes(
    db: Session, user_id: str, minutes: int, *, course_id: str | None = None
) -> None:
    if minutes <= 0:
        return
    spend_units(db, user_id, "voice", minutes, course_id=course_id)


def spend_lab_credit(
    db: Session, user_id: str, *, course_id: str | None = None
) -> None:
    """Idempotent per course — one custom 3D mesh per course generation."""
    if course_id:
        existing = db.scalars(
            select(CreditEvent).where(
                CreditEvent.kind == "lab", CreditEvent.course_id == course_id
            )
        ).first()
        if existing is not None:
            return
    spend_units(db, user_id, "lab", 1, course_id=course_id)


def spend_visual(
    db: Session, user_id: str, *, course_id: str | None = None
) -> None:
    spend_units(db, user_id, "visual", 1, course_id=course_id)

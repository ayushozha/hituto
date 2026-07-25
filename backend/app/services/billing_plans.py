"""Plan → monthly allowance catalog (mirrors PricingPage credit model).

Clerk session JWTs carry `pla` as `u:<slug>` / `o:<slug>`. We map those slugs onto
named allowances here. Unknown / missing slugs fall back to Early Explorer (free).
"""
from __future__ import annotations

from dataclasses import dataclass


# Pricing promise: one course credit covers the roadmap + up to this many lessons.
MAX_LESSONS_PER_COURSE_CREDIT = 5


@dataclass(frozen=True, slots=True)
class PlanAllowances:
    slug: str
    name: str
    course_credits: int
    voice_minutes: int
    visuals: int
    lab_credits: int
    # True for the free starter plan — used by UI upgrade CTAs.
    is_free: bool = False


# Canonical catalog. Aliases below point at the same objects.
_EARLY = PlanAllowances(
    slug="early_explorer",
    name="Early Explorer",
    course_credits=1,
    voice_minutes=20,
    visuals=10,
    lab_credits=0,
    is_free=True,
)
_LEARNER = PlanAllowances(
    slug="learner",
    name="Learner",
    course_credits=8,
    voice_minutes=90,
    visuals=40,
    lab_credits=2,
)
_PRO = PlanAllowances(
    slug="pro",
    name="Pro",
    course_credits=20,
    voice_minutes=300,
    visuals=120,
    lab_credits=8,
)
_CREW = PlanAllowances(
    slug="study_crew",
    name="Study Crew",
    course_credits=8,
    voice_minutes=200,
    visuals=60,
    lab_credits=4,
)
_DEV = PlanAllowances(
    slug="dev",
    name="Local Dev",
    course_credits=100,
    voice_minutes=999,
    visuals=999,
    lab_credits=50,
)

_PLANS: dict[str, PlanAllowances] = {
    "early_explorer": _EARLY,
    # Clerk Billing auto-creates free_user when Billing is enabled.
    "free_user": _EARLY,
    "free": _EARLY,
    "learner": _LEARNER,
    "plus": _LEARNER,
    "starter": _LEARNER,
    "pro": _PRO,
    "unlimited": _PRO,
    "study_crew": _CREW,
    "crew": _CREW,
    "dev": _DEV,
}


def normalize_plan_slug(raw: str | None) -> str:
    """Turn Clerk `pla` (`u:pro` / `o:study_crew`) or a bare slug into a catalog key."""
    if not raw:
        return _EARLY.slug
    slug = raw.strip().lower()
    if ":" in slug:
        slug = slug.split(":", 1)[1]
    slug = slug.replace("-", "_").replace(" ", "_")
    return slug or _EARLY.slug


def allowances_for(plan_slug: str | None) -> PlanAllowances:
    return _PLANS.get(normalize_plan_slug(plan_slug), _EARLY)


def known_plan_slugs() -> tuple[str, ...]:
    return tuple(sorted(_PLANS))

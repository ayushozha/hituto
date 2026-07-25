"""Aggregates every v1 endpoint router into one `api_router`.

NOTE: no extra prefix is added here — each sub-router keeps its own path prefix
(`/courses`, `/sources`, …) so public URLs are unchanged. `v1` is the Python
package location, not a URL segment (the SPA + lesson iframes call root paths).
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    agentbridge,
    billing,
    courses,
    insights,
    profile,
    reports,
    shared,
    sources,
    tools,
    tutor,
    voice,
)

api_router = APIRouter()
api_router.include_router(billing.router)
api_router.include_router(courses.router)
api_router.include_router(tools.router)
api_router.include_router(tutor.router)
api_router.include_router(sources.router)
api_router.include_router(shared.router)
api_router.include_router(voice.router)
api_router.include_router(agentbridge.router)
api_router.include_router(insights.router)
api_router.include_router(profile.router)
api_router.include_router(reports.router)

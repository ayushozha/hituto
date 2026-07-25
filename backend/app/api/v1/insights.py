"""Thin HTTP endpoints for private, user-owned learning insights."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ...core.auth import get_current_user_id
from ...core.db import get_db
from ...core.tasks import spawn
from ...schemas.insight import (
    DeleteInsightsResult,
    EventBatchResult,
    InsightPreferencesOut,
    InsightPreferencesPatch,
    InsightSummary,
    LearningEventBatchIn,
)
from ...services import insight_service

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/events/batch", response_model=EventBatchResult, status_code=202)
async def record_learning_events(
    body: LearningEventBatchIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return insight_service.record_events(db, user_id, body.events)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/summary", response_model=InsightSummary)
async def insight_summary(
    window: str = Query(default="7d", pattern="^(7d|30d)$"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    summary = insight_service.get_summary(db, user_id, window)
    if summary.status == "ready":
        spawn(
            insight_service.refresh_snapshot(user_id, window),
            name=f"insights:{user_id}:{window}",
        )
    return summary


@router.post("/refresh", status_code=202)
async def refresh_insights(
    window: str = Query(default="7d", pattern="^(7d|30d)$"),
    user_id: str = Depends(get_current_user_id),
):
    spawn(insight_service.refresh_snapshot(user_id, window), name=f"insights:{user_id}:{window}")
    return Response(status_code=202)


@router.get("/preferences", response_model=InsightPreferencesOut)
def get_insight_preferences(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return insight_service.preferences_out(
        insight_service.get_or_create_preferences(db, user_id)
    )


@router.patch("/preferences", response_model=InsightPreferencesOut)
def patch_insight_preferences(
    body: InsightPreferencesPatch,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return insight_service.update_preferences(db, user_id, body)


@router.delete("/data", response_model=DeleteInsightsResult)
def delete_insights(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return insight_service.delete_user_insights(db, user_id)

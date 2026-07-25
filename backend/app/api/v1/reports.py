"""Authenticated progress-report authoring and parent-vault handoff routes."""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ...core.auth import get_current_user_id
from ...core.db import get_db
from ...schemas.report import (
    AcknowledgementOut,
    GrantOut,
    InvitationClaimIn,
    LearnerOut,
    ReportCreate,
    ReportHistoryOut,
    ReportInvitationOut,
    ReportOut,
    ReportPatch,
    ReportPublishOut,
)
from ...services import report_service

router = APIRouter(tags=["reports"])
T = TypeVar("T")


def _service(call: Callable[..., T], *args, **kwargs) -> T:
    try:
        return call(*args, **kwargs)
    except report_service.ReportNotFound as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc
    except report_service.InvitationUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail="This invitation is unavailable. It may be expired, revoked, or already claimed.",
        ) from exc
    except report_service.ReportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc) or "report state conflict") from exc
    except report_service.ReportInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc) or "invalid report") from exc


@router.get("/reports", response_model=list[ReportOut])
def list_reports(
    scope: Literal["authored", "family"] = Query(default="authored"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.list_reports, db, user_id, scope)


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(
    body: ReportCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.create_report, db, user_id, body)


# Keep static learner paths above /reports/{report_id}, or "learners" is captured as an id.
@router.get("/reports/learners", response_model=list[LearnerOut])
def list_report_learners(
    scope: Literal["authoring", "custody"] = Query(default="authoring"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = (
        report_service.list_authoring_learners
        if scope == "authoring"
        else report_service.list_custody_learners
    )
    return _service(service, db, user_id)


@router.get("/reports/learners/{learner_id}/grants", response_model=list[GrantOut])
def list_learner_grants(
    learner_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.list_grants, db, learner_id, user_id)


@router.delete("/reports/learners/{learner_id}/grants/{grant_id}", status_code=204)
def revoke_learner_grant(
    learner_id: str,
    grant_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _service(report_service.revoke_grant, db, learner_id, grant_id, user_id)
    return Response(status_code=204)


@router.post("/report-invitations/claim", response_model=ReportOut)
def claim_report_invitation(
    body: InvitationClaimIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(
        report_service.claim_invitation,
        db,
        body.token,
        user_id,
        body.target_learner_id,
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.get_report, db, report_id, user_id)


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(
    report_id: str,
    body: ReportPatch,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.update_report, db, report_id, user_id, body)


@router.post("/reports/{report_id}/publish", response_model=ReportPublishOut)
def publish_report(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.publish_report, db, report_id, user_id)


@router.post("/reports/{report_id}/corrections", response_model=ReportOut, status_code=201)
def create_report_correction(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.create_correction, db, report_id, user_id)


@router.post("/reports/{report_id}/invitations", response_model=ReportInvitationOut)
def create_report_invitation(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.create_invitation, db, report_id, user_id)


@router.delete("/reports/{report_id}/invitations", status_code=204)
def revoke_report_invitations(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _service(report_service.revoke_invitations, db, report_id, user_id)
    return Response(status_code=204)


@router.post("/reports/{report_id}/acknowledge", response_model=AcknowledgementOut)
def acknowledge_report(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.acknowledge_report, db, report_id, user_id)


@router.post("/reports/{report_id}/print", status_code=204)
def record_report_print(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _service(report_service.record_print, db, report_id, user_id)
    return Response(status_code=204)


@router.get("/reports/{report_id}/history", response_model=ReportHistoryOut)
def get_report_history(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return _service(report_service.report_history, db, report_id, user_id)

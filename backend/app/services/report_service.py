"""Learner-scoped progress-report authorization, handoff, and history."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..models.report import (
    Learner,
    LearnerAccessGrant,
    ProgressReport,
    ReportAuditEvent,
    ReportDelivery,
)
from ..models.base import _now
from ..schemas.report import (
    AcknowledgementOut,
    AuditEventOut,
    GrantOut,
    LearnerOut,
    ReportContent,
    ReportCreate,
    ReportHistoryOut,
    ReportInvitationOut,
    ReportOut,
    ReportPatch,
    ReportPermissions,
    ReportPublishOut,
)

CUSTODY_MANAGE = "custody:manage"
REPORT_CREATE = "report:create"
REPORT_VIEW = "report:view"
INVITATION_TTL = timedelta(days=7)


class ReportNotFound(Exception):
    """The resource does not exist or the caller may not discover it."""


class ReportConflict(Exception):
    """The requested state transition is not valid."""


class ReportInvalid(Exception):
    """The draft is not complete enough for the requested transition."""


class InvitationUnavailable(Exception):
    """A claim token is unknown, expired, revoked, or already used."""


def _begin_sqlite_write(db: Session) -> None:
    """Serialize report-series transitions where SQLite cannot honor FOR UPDATE."""
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _active_grant_query(
    learner_id: str,
    user_id: str,
    capabilities: tuple[str, ...],
):
    now = _now()
    return (
        select(LearnerAccessGrant.id)
        .where(
            LearnerAccessGrant.learner_id == learner_id,
            LearnerAccessGrant.principal_user_id == user_id,
            LearnerAccessGrant.capability.in_(capabilities),
            LearnerAccessGrant.accepted_at.is_not(None),
            LearnerAccessGrant.revoked_at.is_(None),
            or_(
                LearnerAccessGrant.expires_at.is_(None),
                LearnerAccessGrant.expires_at > now,
            ),
        )
        .limit(1)
    )


def has_learner_capability(
    db: Session,
    learner_id: str,
    user_id: str,
    *capabilities: str,
) -> bool:
    return db.scalar(_active_grant_query(learner_id, user_id, tuple(capabilities))) is not None


def _active_custodian(db: Session, learner_id: str) -> LearnerAccessGrant | None:
    now = _now()
    return db.scalar(
        select(LearnerAccessGrant)
        .where(
            LearnerAccessGrant.learner_id == learner_id,
            LearnerAccessGrant.capability == CUSTODY_MANAGE,
            LearnerAccessGrant.accepted_at.is_not(None),
            LearnerAccessGrant.revoked_at.is_(None),
            or_(
                LearnerAccessGrant.expires_at.is_(None),
                LearnerAccessGrant.expires_at > now,
            ),
        )
        .limit(1)
    )


def _lock_learner(db: Session, learner_id: str) -> Learner:
    learner = db.scalar(select(Learner).where(Learner.id == learner_id).with_for_update())
    if learner is None:
        raise ReportNotFound
    return learner


def require_learner_capability(
    db: Session,
    learner_id: str,
    user_id: str,
    *capabilities: str,
    lock: bool = False,
) -> None:
    if lock:
        now = _now()
        grant = db.scalar(
            select(LearnerAccessGrant)
            .where(
                LearnerAccessGrant.learner_id == learner_id,
                LearnerAccessGrant.principal_user_id == user_id,
                LearnerAccessGrant.capability.in_(capabilities),
                LearnerAccessGrant.accepted_at.is_not(None),
                LearnerAccessGrant.revoked_at.is_(None),
                or_(
                    LearnerAccessGrant.expires_at.is_(None),
                    LearnerAccessGrant.expires_at > now,
                ),
            )
            .limit(1)
            .with_for_update()
        )
        if grant is not None:
            return
    elif has_learner_capability(db, learner_id, user_id, *capabilities):
        return
    raise ReportNotFound


def _grant(
    db: Session,
    learner_id: str,
    principal_user_id: str,
    capability: str,
    *,
    granted_by_user_id: str | None,
    principal_label: str | None = None,
    expires_at: datetime | None = None,
) -> LearnerAccessGrant:
    grant = db.scalar(
        select(LearnerAccessGrant).where(
            LearnerAccessGrant.learner_id == learner_id,
            LearnerAccessGrant.principal_user_id == principal_user_id,
            LearnerAccessGrant.capability == capability,
        )
    )
    now = _now()
    if grant is None:
        grant = LearnerAccessGrant(
            learner_id=learner_id,
            principal_user_id=principal_user_id,
            principal_label=principal_label,
            capability=capability,
            granted_by_user_id=granted_by_user_id,
            accepted_at=now,
            expires_at=expires_at,
        )
        db.add(grant)
    else:
        grant.principal_label = principal_label or grant.principal_label
        grant.granted_by_user_id = granted_by_user_id
        grant.accepted_at = now
        grant.expires_at = expires_at
        grant.revoked_at = None
        grant.updated_at = now
    db.flush()
    return grant


def _audit(
    db: Session,
    learner_id: str,
    actor_user_id: str,
    event_type: str,
    *,
    report_id: str | None = None,
    delivery_id: str | None = None,
    details: dict | None = None,
    event_id: str | None = None,
) -> ReportAuditEvent:
    event = ReportAuditEvent(
        **({"id": event_id} if event_id is not None else {}),
        learner_id=learner_id,
        report_id=report_id,
        delivery_id=delivery_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        details=details or {},
    )
    db.add(event)
    db.flush()
    return event


def _learner_out(learner: Learner) -> LearnerOut:
    return LearnerOut(
        id=learner.id,
        display_alias=learner.display_alias,
        grade_band=learner.grade_band,
    )


def _acknowledged_at(
    db: Session,
    report_id: str,
    user_id: str | None = None,
) -> datetime | None:
    conditions = [
        ReportAuditEvent.report_id == report_id,
        ReportAuditEvent.event_type == "acknowledged",
    ]
    if user_id is not None:
        conditions.append(ReportAuditEvent.actor_user_id == user_id)
    value = db.scalar(select(func.max(ReportAuditEvent.created_at)).where(*conditions))
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def _author_access(db: Session, report: ProgressReport, user_id: str) -> bool:
    return report.author_user_id == user_id and has_learner_capability(
        db,
        report.learner_id,
        user_id,
        REPORT_VIEW,
    )


def _family_access(db: Session, report: ProgressReport, user_id: str) -> bool:
    return report.status == "published" and has_learner_capability(
        db,
        report.learner_id,
        user_id,
        REPORT_VIEW,
    )


def _can_access(db: Session, report: ProgressReport, user_id: str) -> bool:
    return _author_access(db, report, user_id) or _family_access(db, report, user_id)


def _get_report(db: Session, report_id: str, user_id: str) -> ProgressReport:
    report = db.get(ProgressReport, report_id)
    if report is None or not _can_access(db, report, user_id):
        raise ReportNotFound
    return report


def _lock_report(db: Session, report_id: str) -> ProgressReport:
    report = db.scalar(
        select(ProgressReport)
        .where(ProgressReport.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        raise ReportNotFound
    return report


def _is_latest_version(db: Session, report: ProgressReport) -> bool:
    latest_version = db.scalar(
        select(func.max(ProgressReport.version)).where(
            ProgressReport.series_id == report.series_id
        )
    )
    return latest_version == report.version


def _is_latest_published_version(db: Session, report: ProgressReport) -> bool:
    if report.status != "published":
        return False
    latest_version = db.scalar(
        select(func.max(ProgressReport.version)).where(
            ProgressReport.series_id == report.series_id,
            ProgressReport.status == "published",
        )
    )
    return latest_version == report.version


def _permissions(db: Session, report: ProgressReport, user_id: str) -> ReportPermissions:
    author = report.author_user_id == user_id
    can_create = author and has_learner_capability(
        db, report.learner_id, user_id, REPORT_CREATE
    )
    can_read_family = has_learner_capability(db, report.learner_id, user_id, REPORT_VIEW)
    can_manage = has_learner_capability(
        db, report.learner_id, user_id, CUSTODY_MANAGE
    )
    published = report.status == "published"
    latest = _is_latest_version(db, report)
    latest_published = _is_latest_published_version(db, report)
    return ReportPermissions(
        can_edit=can_create and not published,
        can_publish=can_create and not published,
        can_invite=(
            can_create
            and published
            and latest_published
            and _active_custodian(db, report.learner_id) is None
        ),
        can_correct=can_create and published and latest,
        can_acknowledge=published and not author and can_read_family,
        can_print=published and (author or can_read_family),
        can_manage_grants=can_manage,
    )


def report_out(db: Session, report: ProgressReport, user_id: str) -> ReportOut:
    learner = db.get(Learner, report.learner_id)
    if learner is None:
        raise ReportNotFound
    return ReportOut(
        id=report.id,
        series_id=report.series_id,
        learner=_learner_out(learner),
        author_display_name=report.author_display_name,
        author_account_ref=hashlib.sha256(report.author_user_id.encode()).hexdigest()[:12],
        version=report.version,
        supersedes_id=report.supersedes_id,
        status=report.status,
        reporting_period_start=report.reporting_period_start,
        reporting_period_end=report.reporting_period_end,
        schema_version=report.schema_version,
        evidence_mode=report.evidence_mode,
        content=ReportContent.model_validate(report.content or {}),
        published_at=report.published_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
        acknowledged_at=_acknowledged_at(db, report.id),
        permissions=_permissions(db, report, user_id),
    )


def list_reports(
    db: Session,
    user_id: str,
    scope: str,
) -> list[ReportOut]:
    if scope == "authored":
        reports = db.scalars(
            select(ProgressReport)
            .where(ProgressReport.author_user_id == user_id)
            .order_by(ProgressReport.updated_at.desc())
        ).all()
        reports = [report for report in reports if _author_access(db, report, user_id)]
    else:
        reports = db.scalars(
            select(ProgressReport)
            .where(ProgressReport.status == "published")
            .order_by(ProgressReport.updated_at.desc())
        ).all()
        reports = [report for report in reports if _family_access(db, report, user_id)]
    latest_versions: dict[str, int] = {}
    for report in reports:
        latest_versions[report.series_id] = max(
            report.version,
            latest_versions.get(report.series_id, 0),
        )
    reports = [
        report
        for report in reports
        if report.version == latest_versions[report.series_id]
    ]
    return [report_out(db, report, user_id) for report in reports]


def _list_learners_for_capability(
    db: Session,
    user_id: str,
    capability: str,
) -> list[LearnerOut]:
    now = _now()
    active_grant = (
        select(LearnerAccessGrant.id)
        .where(
            LearnerAccessGrant.learner_id == Learner.id,
            LearnerAccessGrant.principal_user_id == user_id,
            LearnerAccessGrant.capability == capability,
            LearnerAccessGrant.accepted_at.is_not(None),
            LearnerAccessGrant.revoked_at.is_(None),
            or_(
                LearnerAccessGrant.expires_at.is_(None),
                LearnerAccessGrant.expires_at > now,
            ),
        )
        .exists()
    )
    learners = db.scalars(
        select(Learner).where(active_grant).order_by(Learner.display_alias)
    ).all()
    return [_learner_out(learner) for learner in learners]


def list_authoring_learners(db: Session, user_id: str) -> list[LearnerOut]:
    return _list_learners_for_capability(db, user_id, REPORT_CREATE)


def list_custody_learners(db: Session, user_id: str) -> list[LearnerOut]:
    return _list_learners_for_capability(db, user_id, CUSTODY_MANAGE)


def create_report(db: Session, user_id: str, body: ReportCreate) -> ReportOut:
    if body.learner is not None:
        learner = Learner(
            display_alias=body.learner.display_alias,
            grade_band=body.learner.grade_band,
            created_by_user_id=user_id,
        )
        db.add(learner)
        db.flush()
        _grant(
            db,
            learner.id,
            user_id,
            REPORT_CREATE,
            granted_by_user_id=user_id,
        )
        _grant(
            db,
            learner.id,
            user_id,
            REPORT_VIEW,
            granted_by_user_id=user_id,
        )
        _audit(
            db,
            learner.id,
            user_id,
            "grant_created",
            details={"capabilities": [REPORT_CREATE, REPORT_VIEW]},
        )
    else:
        learner = db.get(Learner, body.learner_id)
        if learner is None:
            raise ReportNotFound
        require_learner_capability(db, learner.id, user_id, REPORT_CREATE)

    report = ProgressReport(
        learner_id=learner.id,
        author_user_id=user_id,
        author_display_name=body.author_display_name,
        reporting_period_start=body.reporting_period_start,
        reporting_period_end=body.reporting_period_end,
        content=body.content.model_dump(mode="json"),
    )
    db.add(report)
    db.flush()
    _audit(db, learner.id, user_id, "draft_created", report_id=report.id)
    db.commit()
    db.refresh(report)
    return report_out(db, report, user_id)


def get_report(db: Session, report_id: str, user_id: str) -> ReportOut:
    report = _get_report(db, report_id, user_id)
    if report.status == "published":
        _audit(db, report.learner_id, user_id, "viewed", report_id=report.id)
        db.commit()
        db.refresh(report)
    return report_out(db, report, user_id)


def update_report(
    db: Session,
    report_id: str,
    user_id: str,
    body: ReportPatch,
) -> ReportOut:
    report = _lock_report(db, report_id)
    if report.author_user_id != user_id:
        raise ReportNotFound
    require_learner_capability(
        db,
        report.learner_id,
        user_id,
        REPORT_CREATE,
        lock=True,
    )
    if report.status != "draft":
        raise ReportConflict("published reports are immutable")

    start = (
        body.reporting_period_start
        if "reporting_period_start" in body.model_fields_set
        else report.reporting_period_start
    )
    end = (
        body.reporting_period_end
        if "reporting_period_end" in body.model_fields_set
        else report.reporting_period_end
    )
    if start and end and start > end:
        raise ReportInvalid("reporting period start must be on or before the end")

    values: dict = {"updated_at": _now()}
    if body.author_display_name is not None:
        values["author_display_name"] = body.author_display_name
    if "reporting_period_start" in body.model_fields_set:
        values["reporting_period_start"] = body.reporting_period_start
    if "reporting_period_end" in body.model_fields_set:
        values["reporting_period_end"] = body.reporting_period_end
    if body.content is not None:
        values["content"] = body.content.model_dump(mode="json")

    changed = db.execute(
        update(ProgressReport)
        .where(
            ProgressReport.id == report.id,
            ProgressReport.status == "draft",
            ProgressReport.author_user_id == user_id,
        )
        .values(**values)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ReportConflict("report is no longer editable")
    _audit(db, report.learner_id, user_id, "draft_updated", report_id=report.id)
    db.commit()
    updated_report = db.get(ProgressReport, report.id)
    if updated_report is None:
        raise ReportNotFound
    return report_out(db, updated_report, user_id)


def _validate_publishable(report: ProgressReport) -> None:
    content = ReportContent.model_validate(report.content or {})
    if (
        report.reporting_period_start is None
        or report.reporting_period_end is None
        or report.reporting_period_start > report.reporting_period_end
    ):
        raise ReportInvalid("a valid reporting period is required before publishing")
    required = (
        content.learning_goals,
        content.work_completed,
        content.strengths,
        content.support_areas,
        content.next_actions,
    )
    if any(not section for section in required) or not content.teacher_observations.strip():
        raise ReportInvalid("complete every report section before publishing")


def _mint_invitation(
    db: Session,
    report: ProgressReport,
    user_id: str,
) -> tuple[ReportDelivery, str]:
    now = _now()
    db.execute(
        update(ReportDelivery)
        .where(
            ReportDelivery.report_id.in_(
                select(ProgressReport.id).where(
                    ProgressReport.series_id == report.series_id
                )
            ),
            ReportDelivery.claimed_at.is_(None),
            ReportDelivery.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = secrets.token_urlsafe(32)
    delivery = ReportDelivery(
        report_id=report.id,
        created_by_user_id=user_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + INVITATION_TTL,
    )
    db.add(delivery)
    db.flush()
    _audit(
        db,
        report.learner_id,
        user_id,
        "invitation_created",
        report_id=report.id,
        delivery_id=delivery.id,
    )
    return delivery, token


def publish_report(
    db: Session,
    report_id: str,
    user_id: str,
) -> ReportPublishOut:
    report = _lock_report(db, report_id)
    if report.author_user_id != user_id:
        raise ReportNotFound
    require_learner_capability(
        db,
        report.learner_id,
        user_id,
        REPORT_CREATE,
        lock=True,
    )
    if report.status != "draft":
        raise ReportConflict("report is already published")
    _validate_publishable(report)

    now = _now()
    changed = db.execute(
        update(ProgressReport)
        .where(
            ProgressReport.id == report.id,
            ProgressReport.status == "draft",
            ProgressReport.author_user_id == user_id,
        )
        .values(status="published", published_at=now, updated_at=now)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ReportConflict("report is no longer publishable")
    report.status = "published"
    report.published_at = now
    report.updated_at = now
    _audit(
        db,
        report.learner_id,
        user_id,
        "published",
        report_id=report.id,
        details={"version": report.version, "supersedes_id": report.supersedes_id},
    )
    delivery = None
    token = None
    try:
        _lock_learner(db, report.learner_id)
        if _active_custodian(db, report.learner_id) is None:
            delivery, token = _mint_invitation(db, report, user_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ReportConflict("could not publish report") from exc
    db.refresh(report)
    return ReportPublishOut(
        report=report_out(db, report, user_id),
        invitation=(
            ReportInvitationOut(
                id=delivery.id,
                token=token,
                expires_at=delivery.expires_at,
            )
            if delivery is not None and token is not None
            else None
        ),
    )


def create_invitation(
    db: Session,
    report_id: str,
    user_id: str,
) -> ReportInvitationOut:
    report = _lock_report(db, report_id)
    if report.author_user_id != user_id:
        raise ReportNotFound
    require_learner_capability(
        db,
        report.learner_id,
        user_id,
        REPORT_CREATE,
        lock=True,
    )
    if report.status != "published":
        raise ReportConflict("only published reports can be invited")
    if not _is_latest_published_version(db, report):
        raise ReportConflict("only the latest published report version can be invited")
    _lock_learner(db, report.learner_id)
    if _active_custodian(db, report.learner_id) is not None:
        db.rollback()
        raise ReportConflict("this learner already has a custodian")
    delivery, token = _mint_invitation(db, report, user_id)
    db.commit()
    return ReportInvitationOut(id=delivery.id, token=token, expires_at=delivery.expires_at)


def revoke_invitations(db: Session, report_id: str, user_id: str) -> None:
    report = _get_report(db, report_id, user_id)
    if report.author_user_id != user_id:
        raise ReportNotFound
    require_learner_capability(db, report.learner_id, user_id, REPORT_CREATE)
    if report.status != "published":
        raise ReportConflict("only published report invitations can be revoked")
    now = _now()
    revoked = db.execute(
        update(ReportDelivery)
        .where(
            ReportDelivery.report_id == report.id,
            ReportDelivery.claimed_at.is_(None),
            ReportDelivery.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if revoked.rowcount:
        _audit(
            db,
            report.learner_id,
            user_id,
            "invitation_revoked",
            report_id=report.id,
            details={"count": revoked.rowcount},
        )
        db.commit()


def _lock_report_series(
    db: Session,
    report: ProgressReport,
) -> list[ProgressReport]:
    source_learner_id = report.learner_id
    series_reports = db.scalars(
        select(ProgressReport)
        .where(ProgressReport.series_id == report.series_id)
        .order_by(ProgressReport.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if not series_reports or any(
        item.learner_id != source_learner_id for item in series_reports
    ):
        raise InvitationUnavailable
    return list(series_reports)


def _attach_report_series(
    db: Session,
    series_reports: list[ProgressReport],
    target_learner_id: str,
    custodian_user_id: str,
) -> list[str]:
    report_ids = [item.id for item in series_reports]
    author_user_ids = sorted({item.author_user_id for item in series_reports})
    db.execute(
        update(ProgressReport)
        .where(ProgressReport.id.in_(report_ids))
        .values(learner_id=target_learner_id)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(ReportAuditEvent)
        .where(ReportAuditEvent.report_id.in_(report_ids))
        .values(learner_id=target_learner_id)
        .execution_options(synchronize_session=False)
    )
    for author_user_id in author_user_ids:
        _grant(
            db,
            target_learner_id,
            author_user_id,
            REPORT_CREATE,
            granted_by_user_id=custodian_user_id,
        )
        _grant(
            db,
            target_learner_id,
            author_user_id,
            REPORT_VIEW,
            granted_by_user_id=custodian_user_id,
        )
    _audit(
        db,
        target_learner_id,
        custodian_user_id,
        "grant_created",
        details={
            "capabilities": [REPORT_CREATE, REPORT_VIEW],
            "principal_user_ids": author_user_ids,
            "reason": "report_series_attached",
        },
    )
    return author_user_ids


def claim_invitation(
    db: Session,
    token: str,
    user_id: str,
    target_learner_id: str | None = None,
) -> ReportOut:
    try:
        _begin_sqlite_write(db)
    except OperationalError as exc:
        db.rollback()
        raise InvitationUnavailable from exc
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    delivery = db.scalar(
        select(ReportDelivery).where(ReportDelivery.token_hash == token_hash)
    )
    if delivery is None:
        db.rollback()
        raise InvitationUnavailable
    try:
        report = _lock_report(db, delivery.report_id)
    except ReportNotFound as exc:
        db.rollback()
        raise InvitationUnavailable from exc
    if not _is_latest_published_version(db, report):
        db.rollback()
        raise InvitationUnavailable

    series_reports: list[ProgressReport] = []
    if target_learner_id is not None:
        require_learner_capability(
            db,
            target_learner_id,
            user_id,
            CUSTODY_MANAGE,
            lock=True,
        )
        try:
            series_reports = _lock_report_series(db, report)
        except InvitationUnavailable:
            db.rollback()
            raise
    try:
        source_learner = _lock_learner(db, report.learner_id)
        if target_learner_id is not None:
            _lock_learner(db, target_learner_id)
    except ReportNotFound as exc:
        db.rollback()
        raise InvitationUnavailable from exc
    if _active_custodian(db, report.learner_id) is not None:
        db.rollback()
        raise InvitationUnavailable

    try:
        now = _now()
        claimed = db.execute(
            update(ReportDelivery)
            .where(
                ReportDelivery.token_hash == token_hash,
                ReportDelivery.claimed_at.is_(None),
                ReportDelivery.revoked_at.is_(None),
                ReportDelivery.expires_at > now,
            )
            .values(claimed_by_user_id=user_id, claimed_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise InvitationUnavailable

        claim_learner_id = report.learner_id
        claim_details: dict = {"mode": "bootstrap"}
        if target_learner_id is None:
            _grant(
                db,
                claim_learner_id,
                user_id,
                CUSTODY_MANAGE,
                granted_by_user_id=delivery.created_by_user_id,
            )
            _grant(
                db,
                claim_learner_id,
                user_id,
                REPORT_VIEW,
                granted_by_user_id=delivery.created_by_user_id,
            )
        else:
            source_learner_id = claim_learner_id
            if not series_reports:
                raise InvitationUnavailable
            author_user_ids = _attach_report_series(
                db,
                series_reports,
                target_learner_id,
                user_id,
            )
            source_report_count = db.scalar(
                select(func.count(ProgressReport.id)).where(
                    ProgressReport.learner_id == source_learner_id
                )
            )
            if source_report_count == 0:
                db.delete(source_learner)
            claim_learner_id = target_learner_id
            claim_details = {
                "mode": "existing_learner",
                "source_learner_id": source_learner_id,
                "target_learner_id": target_learner_id,
                "author_user_ids": author_user_ids,
            }
        _audit(
            db,
            claim_learner_id,
            user_id,
            "claimed",
            report_id=report.id,
            delivery_id=delivery.id,
            details=claim_details,
        )
        db.commit()
    except InvitationUnavailable:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise InvitationUnavailable from exc
    db.refresh(report)
    return report_out(db, report, user_id)


def create_correction(db: Session, report_id: str, user_id: str) -> ReportOut:
    try:
        _begin_sqlite_write(db)
    except OperationalError as exc:
        db.rollback()
        raise ReportConflict("report update is busy; retry") from exc
    source = _lock_report(db, report_id)
    if source.author_user_id != user_id:
        raise ReportNotFound
    require_learner_capability(
        db,
        source.learner_id,
        user_id,
        REPORT_CREATE,
        lock=True,
    )
    if source.status != "published":
        raise ReportConflict("only published reports can be corrected")
    latest_version = db.scalar(
        select(func.max(ProgressReport.version)).where(
            ProgressReport.series_id == source.series_id
        )
    )
    if latest_version != source.version:
        raise ReportConflict("a newer report version already exists")

    correction = ProgressReport(
        series_id=source.series_id,
        learner_id=source.learner_id,
        author_user_id=user_id,
        author_display_name=source.author_display_name,
        reporting_period_start=source.reporting_period_start,
        reporting_period_end=source.reporting_period_end,
        schema_version=source.schema_version,
        content=dict(source.content or {}),
        evidence_mode=source.evidence_mode,
        version=source.version + 1,
        supersedes_id=source.id,
    )
    db.add(correction)
    try:
        db.flush()
        _audit(
            db,
            source.learner_id,
            user_id,
            "correction_created",
            report_id=correction.id,
            details={"supersedes_id": source.id, "version": correction.version},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ReportConflict("a correction already exists") from exc
    db.refresh(correction)
    return report_out(db, correction, user_id)


def acknowledge_report(
    db: Session,
    report_id: str,
    user_id: str,
) -> AcknowledgementOut:
    report = _lock_report(db, report_id)
    if report.status != "published" or report.author_user_id == user_id:
        raise ReportNotFound
    require_learner_capability(
        db,
        report.learner_id,
        user_id,
        CUSTODY_MANAGE,
        REPORT_VIEW,
    )
    acknowledged_at = _acknowledged_at(db, report.id, user_id)
    if acknowledged_at is None:
        event_id = hashlib.sha256(
            f"acknowledged\0{report.id}\0{user_id}".encode()
        ).hexdigest()
        try:
            event = _audit(
                db,
                report.learner_id,
                user_id,
                "acknowledged",
                report_id=report.id,
                event_id=event_id,
            )
            db.commit()
            acknowledged_at = event.created_at
        except IntegrityError:
            db.rollback()
            acknowledged_at = _acknowledged_at(db, report.id, user_id)
            if acknowledged_at is None:
                raise
    return AcknowledgementOut(acknowledged_at=acknowledged_at)


def record_print(db: Session, report_id: str, user_id: str) -> None:
    report = _get_report(db, report_id, user_id)
    if report.status != "published":
        raise ReportConflict("only published reports can be printed")
    _audit(db, report.learner_id, user_id, "print_requested", report_id=report.id)
    db.commit()


def report_history(
    db: Session,
    report_id: str,
    user_id: str,
) -> ReportHistoryOut:
    anchor = _get_report(db, report_id, user_id)
    reports = db.scalars(
        select(ProgressReport)
        .where(ProgressReport.series_id == anchor.series_id)
        .order_by(ProgressReport.version.desc())
    ).all()
    visible = [report for report in reports if _can_access(db, report, user_id)]
    report_ids = [report.id for report in visible]
    events = (
        db.scalars(
            select(ReportAuditEvent)
            .where(ReportAuditEvent.report_id.in_(report_ids))
            .order_by(ReportAuditEvent.created_at.desc())
        ).all()
        if report_ids
        else []
    )
    return ReportHistoryOut(
        reports=[report_out(db, report, user_id) for report in visible],
        events=[
            AuditEventOut(
                id=event.id,
                event_type=event.event_type,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def list_grants(db: Session, learner_id: str, user_id: str) -> list[GrantOut]:
    require_learner_capability(db, learner_id, user_id, CUSTODY_MANAGE)
    grants = db.scalars(
        select(LearnerAccessGrant)
        .where(LearnerAccessGrant.learner_id == learner_id)
        .order_by(LearnerAccessGrant.created_at)
    ).all()
    return [
        GrantOut(
            id=grant.id,
            principal_user_id=grant.principal_user_id,
            capability=grant.capability,
            accepted_at=grant.accepted_at,
            expires_at=grant.expires_at,
            revoked_at=grant.revoked_at,
        )
        for grant in grants
    ]


def revoke_grant(
    db: Session,
    learner_id: str,
    grant_id: str,
    user_id: str,
) -> None:
    require_learner_capability(db, learner_id, user_id, CUSTODY_MANAGE)
    grant = db.scalar(
        select(LearnerAccessGrant)
        .where(LearnerAccessGrant.id == grant_id)
        .with_for_update()
    )
    if grant is None or grant.learner_id != learner_id:
        raise ReportNotFound
    if grant.capability == CUSTODY_MANAGE:
        raise ReportConflict("custody grants cannot be revoked from this flow")
    if grant.revoked_at is None:
        grant.revoked_at = _now()
        _audit(
            db,
            learner_id,
            user_id,
            "grant_revoked",
            details={
                "grant_id": grant.id,
                "capability": grant.capability,
                "principal_user_id": grant.principal_user_id,
            },
        )
        db.commit()

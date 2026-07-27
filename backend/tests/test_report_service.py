from __future__ import annotations

import hashlib
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from threading import Event

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base, create_database_engine
from app.models.base import _now
from app.models.report import (
    Learner,
    LearnerAccessGrant,
    ProgressReport,
    ReportAuditEvent,
    ReportDelivery,
)
from app.schemas.report import LearnerCreate, ReportContent, ReportCreate, ReportPatch
from app.services import report_service


@pytest.fixture
def db(tmp_path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'reports.db'}")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    assert session.scalar(text("PRAGMA foreign_keys")) == 1
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _content(label: str = "Cells") -> ReportContent:
    return ReportContent(
        learning_goals=[f"Explain {label} clearly"],
        work_completed=[f"Completed the {label} learning sequence"],
        strengths=[
            {
                "statement": f"Explains {label} accurately",
                "evidence": "Used the concept correctly in a worked example",
            }
        ],
        support_areas=[
            {
                "statement": "Needs more independent retrieval",
                "evidence": "Needed one prompt during the final practice check",
            }
        ],
        teacher_observations="Participated thoughtfully and responded well to feedback.",
        next_actions=[f"Practice recalling the key parts of {label}"],
    )


def _draft(
    db: Session,
    *,
    teacher: str = "teacher-a",
    learner_alias: str = "Learner A",
    label: str = "Cells",
):
    return report_service.create_report(
        db,
        teacher,
        ReportCreate(
            author_display_name="Ms. Rivera",
            learner=LearnerCreate(display_alias=learner_alias, grade_band="6"),
            reporting_period_start=date(2026, 7, 1),
            reporting_period_end=date(2026, 7, 24),
            content=_content(label),
        ),
    )


def _published(
    db: Session,
    *,
    teacher: str = "teacher-a",
    learner_alias: str = "Learner A",
    label: str = "Cells",
):
    draft = _draft(
        db,
        teacher=teacher,
        learner_alias=learner_alias,
        label=label,
    )
    published = report_service.publish_report(db, draft.id, teacher)
    assert published.invitation is not None
    assert published.report.author_account_ref == hashlib.sha256(teacher.encode()).hexdigest()[:12]
    return published


def _grant(
    db: Session,
    learner_id: str,
    principal_user_id: str,
    capability: str,
) -> LearnerAccessGrant:
    grant = db.scalar(
        select(LearnerAccessGrant).where(
            LearnerAccessGrant.learner_id == learner_id,
            LearnerAccessGrant.principal_user_id == principal_user_id,
            LearnerAccessGrant.capability == capability,
        )
    )
    assert grant is not None
    return grant


def test_teacher_access_is_scoped_to_explicitly_granted_learners(db: Session) -> None:
    draft = _draft(db)

    assert [learner.id for learner in report_service.list_authoring_learners(db, "teacher-a")] == [
        draft.learner.id
    ]
    assert report_service.list_authoring_learners(db, "teacher-b") == []
    assert report_service.list_reports(db, "teacher-b", "authored") == []
    with pytest.raises(report_service.ReportNotFound):
        report_service.get_report(db, draft.id, "teacher-b")
    with pytest.raises(report_service.ReportNotFound):
        report_service.update_report(
            db,
            draft.id,
            "teacher-b",
            ReportPatch(author_display_name="Unauthorized teacher"),
        )
    with pytest.raises(report_service.ReportNotFound):
        report_service.publish_report(db, draft.id, "teacher-b")
    with pytest.raises(report_service.ReportNotFound):
        report_service.create_report(
            db,
            "teacher-b",
            ReportCreate(
                author_display_name="Unauthorized teacher",
                learner_id=draft.learner.id,
                content=_content(),
            ),
        )

    persisted = db.get(ProgressReport, draft.id)
    assert persisted is not None
    assert persisted.status == "draft"
    assert persisted.author_display_name == "Ms. Rivera"


def test_published_report_is_immutable_and_raw_invitation_token_is_not_stored(
    db: Session,
) -> None:
    published = _published(db)
    token = published.invitation.token
    row = db.get(ProgressReport, published.report.id)
    assert row is not None
    original = {
        "content": deepcopy(row.content),
        "author_display_name": row.author_display_name,
        "reporting_period_start": row.reporting_period_start,
        "reporting_period_end": row.reporting_period_end,
        "published_at": row.published_at,
        "updated_at": row.updated_at,
    }

    with pytest.raises(report_service.ReportConflict, match="immutable"):
        report_service.update_report(
            db,
            row.id,
            "teacher-a",
            ReportPatch(
                author_display_name="Changed after publication",
                content=_content("Altered content"),
            ),
        )

    db.expire_all()
    unchanged = db.get(ProgressReport, row.id)
    assert unchanged is not None
    assert {
        "content": unchanged.content,
        "author_display_name": unchanged.author_display_name,
        "reporting_period_start": unchanged.reporting_period_start,
        "reporting_period_end": unchanged.reporting_period_end,
        "published_at": unchanged.published_at,
        "updated_at": unchanged.updated_at,
    } == original

    delivery = db.get(ReportDelivery, published.invitation.id)
    assert delivery is not None
    assert delivery.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert delivery.token_hash != token
    columns = {
        column[1] for column in db.execute(text("PRAGMA table_info(report_deliveries)"))
    }
    assert "token_hash" in columns
    assert "token" not in columns
    audit_details = db.scalars(select(ReportAuditEvent.details)).all()
    assert all(token not in json.dumps(details) for details in audit_details)


def test_claim_succeeds_once_and_expired_or_revoked_invitations_fail(
    db: Session,
) -> None:
    published = _published(db)
    claimed = report_service.claim_invitation(
        db,
        published.invitation.token,
        "parent-a",
    )
    assert claimed.id == published.report.id
    assert claimed.permissions.can_manage_grants is True
    assert report_service.has_learner_capability(
        db,
        claimed.learner.id,
        "parent-a",
        report_service.CUSTODY_MANAGE,
    )

    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(
            db,
            published.invitation.token,
            "parent-a",
        )

    expired = _published(db, learner_alias="Learner Expired", label="Plants")
    expired_row = db.get(ReportDelivery, expired.invitation.id)
    assert expired_row is not None
    expired_row.expires_at = _now() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(
            db,
            expired.invitation.token,
            "parent-expired",
        )

    revoked = _published(db, learner_alias="Learner Revoked", label="Energy")
    revoked_row = db.get(ReportDelivery, revoked.invitation.id)
    assert revoked_row is not None
    revoked_row.revoked_at = _now()
    db.commit()
    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(
            db,
            revoked.invitation.token,
            "parent-revoked",
        )

    assert not report_service.has_learner_capability(
        db,
        claimed.learner.id,
        "parent-expired",
        report_service.REPORT_VIEW,
    )
    assert not report_service.has_learner_capability(
        db,
        claimed.learner.id,
        "parent-revoked",
        report_service.REPORT_VIEW,
    )
    failed_claim_audits = db.scalar(
        select(func.count(ReportAuditEvent.id)).where(
            ReportAuditEvent.event_type == "claimed",
            ReportAuditEvent.actor_user_id.in_(["parent-expired", "parent-revoked"]),
        )
    )
    assert failed_claim_audits == 0


def test_claim_into_existing_learner_requires_target_custody(db: Session) -> None:
    existing = _published(
        db,
        teacher="teacher-existing",
        learner_alias="Existing learner",
        label="Geometry",
    )
    report_service.claim_invitation(
        db,
        existing.invitation.token,
        "parent-a",
    )
    incoming = _published(
        db,
        teacher="teacher-incoming",
        learner_alias="Incoming learner",
        label="Fractions",
    )

    with pytest.raises(report_service.ReportNotFound):
        report_service.claim_invitation(
            db,
            incoming.invitation.token,
            "parent-b",
            existing.report.learner.id,
        )

    delivery = db.get(ReportDelivery, incoming.invitation.id)
    assert delivery is not None
    assert delivery.claimed_at is None
    persisted = db.get(ProgressReport, incoming.report.id)
    assert persisted is not None
    assert persisted.learner_id == incoming.report.learner.id


def test_claim_into_existing_learner_attaches_the_whole_report_series(
    db: Session,
) -> None:
    existing = _published(
        db,
        teacher="teacher-existing",
        learner_alias="Existing learner",
        label="Geometry",
    )
    report_service.claim_invitation(
        db,
        existing.invitation.token,
        "parent-a",
    )
    target_learner_id = existing.report.learner.id

    incoming_first = _published(
        db,
        teacher="teacher-incoming",
        learner_alias="Incoming learner",
        label="Fractions",
    )
    source_learner_id = incoming_first.report.learner.id
    correction = report_service.create_correction(
        db,
        incoming_first.report.id,
        "teacher-incoming",
    )
    incoming_latest = report_service.publish_report(
        db,
        correction.id,
        "teacher-incoming",
    )
    assert incoming_latest.invitation is not None

    claimed = report_service.claim_invitation(
        db,
        incoming_latest.invitation.token,
        "parent-a",
        target_learner_id,
    )

    assert claimed.learner.id == target_learner_id
    series_rows = db.scalars(
        select(ProgressReport)
        .where(ProgressReport.series_id == incoming_first.report.series_id)
        .order_by(ProgressReport.version)
    ).all()
    assert [report.version for report in series_rows] == [1, 2]
    assert {report.learner_id for report in series_rows} == {target_learner_id}
    report_ids = [report.id for report in series_rows]
    report_audit_learner_ids = set(
        db.scalars(
            select(ReportAuditEvent.learner_id).where(
                ReportAuditEvent.report_id.in_(report_ids)
            )
        ).all()
    )
    assert report_audit_learner_ids == {target_learner_id}
    assert report_service.has_learner_capability(
        db,
        target_learner_id,
        "teacher-incoming",
        report_service.REPORT_CREATE,
    )
    assert report_service.has_learner_capability(
        db,
        target_learner_id,
        "teacher-incoming",
        report_service.REPORT_VIEW,
    )
    assert [learner.id for learner in report_service.list_custody_learners(db, "parent-a")] == [
        target_learner_id
    ]
    assert not report_service.has_learner_capability(
        db,
        source_learner_id,
        "parent-a",
        report_service.CUSTODY_MANAGE,
    )
    assert db.scalar(
        select(func.count(LearnerAccessGrant.id)).where(
            LearnerAccessGrant.learner_id == source_learner_id
        )
    ) == 0
    assert db.scalar(
        select(func.count(ReportAuditEvent.id)).where(
            ReportAuditEvent.learner_id == source_learner_id
        )
    ) == 0
    assert db.get(Learner, source_learner_id) is None
    assert [
        learner.id
        for learner in report_service.list_authoring_learners(db, "teacher-incoming")
    ] == [target_learner_id]


def test_sqlite_serializes_existing_learner_attach_and_correction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _published(db, teacher="teacher-existing", learner_alias="Existing", label="Geometry")
    report_service.claim_invitation(db, existing.invitation.token, "parent-a")
    incoming = _published(db, teacher="teacher-incoming", learner_alias="Incoming", label="Fractions")
    target_learner_id = existing.report.learner.id
    session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    attach_started = Event()
    release_attach = Event()
    correction_started = Event()
    original_attach = report_service._attach_report_series

    def block_attach(*args, **kwargs):
        attach_started.set()
        assert release_attach.wait(timeout=5)
        return original_attach(*args, **kwargs)

    monkeypatch.setattr(report_service, "_attach_report_series", block_attach)

    def claim():
        with session_factory() as session:
            return report_service.claim_invitation(
                session,
                incoming.invitation.token,
                "parent-a",
                target_learner_id,
            )

    def correct():
        correction_started.set()
        with session_factory() as session:
            return report_service.create_correction(session, incoming.report.id, "teacher-incoming")

    with ThreadPoolExecutor(max_workers=2) as executor:
        claim_future = executor.submit(claim)
        assert attach_started.wait(timeout=5)
        correction_future = executor.submit(correct)
        assert correction_started.wait(timeout=5)
        time.sleep(0.1)
        assert not correction_future.done()
        release_attach.set()
        claim_future.result(timeout=5)
        correction = correction_future.result(timeout=5)

    db.expire_all()
    series_rows = db.scalars(
        select(ProgressReport)
        .where(ProgressReport.series_id == incoming.report.series_id)
        .order_by(ProgressReport.version)
    ).all()
    assert [report.version for report in series_rows] == [1, 2]
    assert {report.learner_id for report in series_rows} == {target_learner_id}
    assert correction.learner.id == target_learner_id


def test_existing_learner_attach_keeps_a_source_with_an_unrelated_series(
    db: Session,
) -> None:
    existing = _published(
        db,
        teacher="teacher-existing",
        learner_alias="Existing learner",
        label="Geometry",
    )
    report_service.claim_invitation(
        db,
        existing.invitation.token,
        "parent-a",
    )
    incoming = _published(
        db,
        teacher="teacher-incoming",
        learner_alias="Incoming learner",
        label="Fractions",
    )
    source_learner_id = incoming.report.learner.id
    unrelated = report_service.create_report(
        db,
        "teacher-incoming",
        ReportCreate(
            author_display_name="Ms. Rivera",
            learner_id=source_learner_id,
            reporting_period_start=date(2026, 7, 1),
            reporting_period_end=date(2026, 7, 24),
            content=_content("Energy"),
        ),
    )

    claimed = report_service.claim_invitation(
        db,
        incoming.invitation.token,
        "parent-a",
        existing.report.learner.id,
    )

    assert claimed.learner.id == existing.report.learner.id
    assert db.get(Learner, source_learner_id) is not None
    unrelated_row = db.get(ProgressReport, unrelated.id)
    assert unrelated_row is not None
    assert unrelated_row.learner_id == source_learner_id


def test_teacher_cannot_create_a_second_custodian(db: Session) -> None:
    published = _published(db)
    second_token = secrets.token_urlsafe(32)
    db.add(
        ReportDelivery(
            report_id=published.report.id,
            created_by_user_id="teacher-a",
            token_hash=hashlib.sha256(second_token.encode()).hexdigest(),
            expires_at=_now() + timedelta(days=1),
        )
    )
    db.commit()

    report_service.claim_invitation(db, published.invitation.token, "parent-a")

    teacher_view = report_service.get_report(db, published.report.id, "teacher-a")
    assert teacher_view.permissions.can_invite is False
    with pytest.raises(
        report_service.ReportConflict,
        match="already has a custodian",
    ):
        report_service.create_invitation(db, published.report.id, "teacher-a")
    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(db, second_token, "parent-b")
    assert not report_service.has_learner_capability(
        db,
        published.report.learner.id,
        "parent-b",
        report_service.CUSTODY_MANAGE,
    )

    correction = report_service.create_correction(
        db,
        published.report.id,
        "teacher-a",
    )
    corrected = report_service.publish_report(db, correction.id, "teacher-a")
    assert corrected.invitation is None
    assert corrected.report.id in {
        report.id for report in report_service.list_reports(db, "parent-a", "family")
    }


def test_database_enforces_one_active_custodian_per_learner(db: Session) -> None:
    published = _published(db)
    report_service.claim_invitation(
        db,
        published.invitation.token,
        "parent-a",
    )
    db.add(
        LearnerAccessGrant(
            learner_id=published.report.learner.id,
            principal_user_id="parent-b",
            capability=report_service.CUSTODY_MANAGE,
            granted_by_user_id="teacher-a",
            accepted_at=_now(),
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert db.scalar(
        select(func.count(LearnerAccessGrant.id)).where(
            LearnerAccessGrant.learner_id == published.report.learner.id,
            LearnerAccessGrant.capability == report_service.CUSTODY_MANAGE,
            LearnerAccessGrant.accepted_at.is_not(None),
            LearnerAccessGrant.revoked_at.is_(None),
        )
    ) == 1


def test_claim_rolls_back_when_the_custodian_constraint_wins(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = _published(db)
    db.add(
        LearnerAccessGrant(
            learner_id=published.report.learner.id,
            principal_user_id="parent-a",
            capability=report_service.CUSTODY_MANAGE,
            granted_by_user_id="teacher-a",
            accepted_at=_now(),
        )
    )
    db.commit()
    monkeypatch.setattr(
        report_service,
        "_active_custodian",
        lambda _db, _learner_id: None,
    )

    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(
            db,
            published.invitation.token,
            "parent-b",
        )

    delivery = db.get(ReportDelivery, published.invitation.id)
    assert delivery is not None
    assert delivery.claimed_at is None
    assert not report_service.has_learner_capability(
        db,
        published.report.learner.id,
        "parent-b",
        report_service.CUSTODY_MANAGE,
    )
    assert not report_service.has_learner_capability(
        db,
        published.report.learner.id,
        "parent-b",
        report_service.REPORT_VIEW,
    )


def test_teacher_can_explicitly_revoke_an_unclaimed_invitation(db: Session) -> None:
    published = _published(db)
    active = report_service.create_invitation(db, published.report.id, "teacher-a")

    report_service.revoke_invitations(db, published.report.id, "teacher-a")

    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(db, active.token, "parent-a")
    revoked = db.get(ReportDelivery, active.id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    assert db.scalar(
        select(func.count(ReportAuditEvent.id)).where(
            ReportAuditEvent.report_id == published.report.id,
            ReportAuditEvent.event_type == "invitation_revoked",
        )
    ) == 1


def test_parent_cannot_see_another_learners_reports(db: Session) -> None:
    first = _published(
        db,
        teacher="teacher-a",
        learner_alias="Learner A",
        label="Cells",
    )
    second = _published(
        db,
        teacher="teacher-b",
        learner_alias="Learner B",
        label="Fractions",
    )
    report_service.claim_invitation(db, first.invitation.token, "parent-a")
    report_service.claim_invitation(db, second.invitation.token, "parent-b")

    family_ids = {
        report.id for report in report_service.list_reports(db, "parent-a", "family")
    }
    assert family_ids == {first.report.id}
    with pytest.raises(report_service.ReportNotFound):
        report_service.get_report(db, second.report.id, "parent-a")


def test_correction_chain_preserves_the_published_original(db: Session) -> None:
    first = _published(db)
    original = db.get(ProgressReport, first.report.id)
    assert original is not None
    original_snapshot = {
        "content": deepcopy(original.content),
        "published_at": original.published_at,
        "updated_at": original.updated_at,
        "author_user_id": original.author_user_id,
    }

    correction = report_service.create_correction(db, original.id, "teacher-a")
    assert correction.series_id == original.series_id
    assert correction.version == 2
    assert correction.supersedes_id == original.id
    assert correction.status == "draft"
    assert correction.content == ReportContent.model_validate(original.content)

    report_service.update_report(
        db,
        correction.id,
        "teacher-a",
        ReportPatch(content=_content("Revised cells")),
    )
    second = report_service.publish_report(db, correction.id, "teacher-a")
    assert second.report.version == 2
    assert second.report.content != first.report.content

    db.expire_all()
    preserved = db.get(ProgressReport, original.id)
    assert preserved is not None
    assert preserved.status == "published"
    assert {
        "content": preserved.content,
        "published_at": preserved.published_at,
        "updated_at": preserved.updated_at,
        "author_user_id": preserved.author_user_id,
    } == original_snapshot
    history = report_service.report_history(db, second.report.id, "teacher-a")
    assert [report.version for report in history.reports] == [2, 1]


def test_published_correction_obsoletes_prior_invitations_and_actions(db: Session) -> None:
    first = _published(db)
    correction = report_service.create_correction(
        db,
        first.report.id,
        "teacher-a",
    )

    while_correction_is_draft = report_service.get_report(
        db,
        first.report.id,
        "teacher-a",
    )
    assert while_correction_is_draft.permissions.can_invite is True
    assert while_correction_is_draft.permissions.can_correct is False
    latest = report_service.publish_report(db, correction.id, "teacher-a")

    prior_view = report_service.get_report(db, first.report.id, "teacher-a")
    assert prior_view.permissions.can_invite is False
    assert prior_view.permissions.can_correct is False
    with pytest.raises(report_service.ReportConflict, match="latest published"):
        report_service.create_invitation(db, first.report.id, "teacher-a")
    with pytest.raises(report_service.InvitationUnavailable):
        report_service.claim_invitation(
            db,
            first.invitation.token,
            "parent-a",
        )
    delivery = db.get(ReportDelivery, first.invitation.id)
    assert delivery is not None
    assert delivery.claimed_at is None

    authored = report_service.list_reports(db, "teacher-a", "authored")
    assert [report.id for report in authored] == [latest.report.id]


def test_correction_draft_does_not_interrupt_parent_handoff(db: Session) -> None:
    first = _published(db)
    correction = report_service.create_correction(
        db,
        first.report.id,
        "teacher-a",
    )

    claimed = report_service.claim_invitation(
        db,
        first.invitation.token,
        "parent-a",
    )
    assert claimed.id == first.report.id

    latest = report_service.publish_report(db, correction.id, "teacher-a")
    assert latest.invitation is None
    assert [report.id for report in report_service.list_reports(db, "parent-a", "family")] == [
        latest.report.id
    ]


def test_lists_show_only_the_latest_accessible_version_per_series(db: Session) -> None:
    first = _published(db)
    report_service.claim_invitation(
        db,
        first.invitation.token,
        "parent-a",
    )
    correction = report_service.create_correction(
        db,
        first.report.id,
        "teacher-a",
    )
    latest = report_service.publish_report(db, correction.id, "teacher-a")

    assert [report.id for report in report_service.list_reports(db, "teacher-a", "authored")] == [
        latest.report.id
    ]
    assert [report.id for report in report_service.list_reports(db, "parent-a", "family")] == [
        latest.report.id
    ]
    history = report_service.report_history(db, latest.report.id, "parent-a")
    assert [report.id for report in history.reports] == [
        latest.report.id,
        first.report.id,
    ]


def test_publish_refreshes_a_stale_report_before_validation(db: Session) -> None:
    draft = _draft(db)
    stale_report = db.get(ProgressReport, draft.id)
    assert stale_report is not None
    assert stale_report.content

    other_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    try:
        current = other_session.get(ProgressReport, draft.id)
        assert current is not None
        current.content = {}
        other_session.commit()
    finally:
        other_session.close()
    assert stale_report.content

    with pytest.raises(report_service.ReportInvalid, match="complete every report section"):
        report_service.publish_report(db, draft.id, "teacher-a")

    db.expire_all()
    persisted = db.get(ProgressReport, draft.id)
    assert persisted is not None
    assert persisted.status == "draft"
    assert persisted.content == {}


def test_revoking_report_create_blocks_publishing_an_existing_correction(
    db: Session,
) -> None:
    first = _published(db)
    parent_report = report_service.claim_invitation(
        db,
        first.invitation.token,
        "parent-a",
    )
    correction = report_service.create_correction(db, first.report.id, "teacher-a")
    authoring_grant = _grant(
        db,
        parent_report.learner.id,
        "teacher-a",
        report_service.REPORT_CREATE,
    )

    report_service.revoke_grant(
        db,
        parent_report.learner.id,
        authoring_grant.id,
        "parent-a",
    )

    with pytest.raises(report_service.ReportNotFound):
        report_service.publish_report(db, correction.id, "teacher-a")
    persisted = db.get(ProgressReport, correction.id)
    assert persisted is not None
    assert persisted.status == "draft"
    assert report_service.get_report(
        db,
        correction.id,
        "teacher-a",
    ).permissions.can_publish is False
    viewing_grant = _grant(
        db,
        parent_report.learner.id,
        "teacher-a",
        report_service.REPORT_VIEW,
    )
    report_service.revoke_grant(
        db,
        parent_report.learner.id,
        viewing_grant.id,
        "parent-a",
    )
    with pytest.raises(report_service.ReportNotFound):
        report_service.get_report(db, correction.id, "teacher-a")


def test_revoking_report_view_blocks_reads_but_not_report_authoring(db: Session) -> None:
    published = _published(db)
    parent_report = report_service.claim_invitation(db, published.invitation.token, "parent-a")
    viewing_grant = _grant(
        db,
        parent_report.learner.id,
        "teacher-a",
        report_service.REPORT_VIEW,
    )

    report_service.revoke_grant(db, parent_report.learner.id, viewing_grant.id, "parent-a")

    with pytest.raises(report_service.ReportNotFound):
        report_service.get_report(db, published.report.id, "teacher-a")
    with pytest.raises(report_service.ReportNotFound):
        report_service.report_history(db, published.report.id, "teacher-a")
    assert report_service.list_reports(db, "teacher-a", "authored") == []
    assert report_service.create_correction(db, published.report.id, "teacher-a").version == 2


def test_acknowledgement_is_idempotent(db: Session) -> None:
    published = _published(db)
    report_service.claim_invitation(db, published.invitation.token, "parent-a")

    first = report_service.acknowledge_report(
        db,
        published.report.id,
        "parent-a",
    )
    second = report_service.acknowledge_report(
        db,
        published.report.id,
        "parent-a",
    )

    assert second.acknowledged_at.replace(tzinfo=None) == first.acknowledged_at.replace(
        tzinfo=None
    )
    author_view = report_service.get_report(db, published.report.id, "teacher-a")
    assert author_view.acknowledged_at is not None
    assert author_view.acknowledged_at.replace(tzinfo=None) == first.acknowledged_at.replace(
        tzinfo=None
    )
    acknowledgements = db.scalar(
        select(func.count(ReportAuditEvent.id)).where(
            ReportAuditEvent.report_id == published.report.id,
            ReportAuditEvent.actor_user_id == "parent-a",
            ReportAuditEvent.event_type == "acknowledged",
        )
    )
    assert acknowledgements == 1


def test_custody_grant_cannot_be_revoked_through_generic_grant_flow(
    db: Session,
) -> None:
    published = _published(db)
    parent_report = report_service.claim_invitation(
        db,
        published.invitation.token,
        "parent-a",
    )
    custody = _grant(
        db,
        parent_report.learner.id,
        "parent-a",
        report_service.CUSTODY_MANAGE,
    )

    with pytest.raises(report_service.ReportConflict, match="custody grants"):
        report_service.revoke_grant(
            db,
            parent_report.learner.id,
            custody.id,
            "parent-a",
        )

    db.refresh(custody)
    assert custody.revoked_at is None
    revoke_audits = db.scalar(
        select(func.count(ReportAuditEvent.id)).where(
            ReportAuditEvent.learner_id == parent_report.learner.id,
            ReportAuditEvent.event_type == "grant_revoked",
        )
    )
    assert revoke_audits == 0

from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.v1.reports import router
from app.core.auth import get_current_user_id
from app.core.db import Base, create_database_engine, get_db
from app.core.middleware import register_middleware


def test_report_handoff_api_contract(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'report-api.db'}")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    principal = {"id": "teacher-a"}

    def _db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def _user_id() -> str:
        return principal["id"]

    app = FastAPI()
    register_middleware(app)
    app.include_router(router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_id] = _user_id

    with TestClient(app) as client:
        created = client.post(
            "/reports",
            json={
                "author_display_name": "Ms. Rivera",
                "learner": {"display_alias": "Learner A", "grade_band": "6"},
                "reporting_period_start": date(2026, 7, 1).isoformat(),
                "reporting_period_end": date(2026, 7, 24).isoformat(),
                "content": {
                    "learning_goals": ["Explain cell structure"],
                    "work_completed": ["Completed the cell learning sequence"],
                    "strengths": [
                        {
                            "statement": "Explains the nucleus accurately",
                            "evidence": "Labeled it correctly in a worked example",
                        }
                    ],
                    "support_areas": [
                        {
                            "statement": "Needs more independent retrieval",
                            "evidence": "Needed one prompt in the final check",
                        }
                    ],
                    "teacher_observations": "Participated thoughtfully.",
                    "next_actions": ["Practice recalling organelle functions"],
                },
            },
        )
        assert created.status_code == 201
        assert created.headers["cache-control"] == "no-store, private"
        report = created.json()
        report_id = report["id"]
        learner_id = report["learner"]["id"]
        assert report["permissions"]["can_publish"] is True
        assert client.get("/reports/learners").json() == [
            {"id": learner_id, "display_alias": "Learner A", "grade_band": "6"}
        ]

        published = client.post(f"/reports/{report_id}/publish")
        assert published.status_code == 200
        invitation = published.json()["invitation"]
        assert invitation["token"]
        assert client.patch(
            f"/reports/{report_id}",
            json={"author_display_name": "Rewritten"},
        ).status_code == 409

        principal["id"] = "parent-a"
        claimed = client.post(
            "/report-invitations/claim",
            json={"token": invitation["token"]},
        )
        assert claimed.status_code == 200
        assert claimed.json()["permissions"]["can_manage_grants"] is True
        assert client.get("/reports/learners").json() == []
        assert client.get("/reports/learners?scope=custody").json() == [
            {"id": learner_id, "display_alias": "Learner A", "grade_band": "6"}
        ]
        assert [item["id"] for item in client.get("/reports?scope=family").json()] == [
            report_id
        ]
        first_ack = client.post(f"/reports/{report_id}/acknowledge")
        second_ack = client.post(f"/reports/{report_id}/acknowledge")
        assert first_ack.status_code == second_ack.status_code == 200
        assert first_ack.json()["acknowledged_at"] == second_ack.json()["acknowledged_at"]

        principal["id"] = "parent-b"
        assert client.get(f"/reports/{report_id}").status_code == 404
        replay = client.post(
            "/report-invitations/claim",
            json={"token": invitation["token"]},
        )
        assert replay.status_code == 409
        assert replay.headers["cache-control"] == "no-store, private"
        assert "unavailable" in replay.json()["detail"].lower()
        opaque_preview = client.get(f"/report-invitations/{invitation['token']}")
        assert opaque_preview.status_code == 404
        assert opaque_preview.headers["cache-control"] == "no-store, private"

    engine.dispose()

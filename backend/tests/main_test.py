from pathlib import Path

from fastapi.testclient import TestClient

import main
from session_store import SQLiteSessionStore
from tutor_service import TutorService


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    service = TutorService(SQLiteSessionStore(tmp_path / "api.db"))
    monkeypatch.setattr(main, "service", service)
    return TestClient(main.app)


def test_health_endpoint(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_cookie_is_http_only_and_reused(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        first = client.get("/api/session")
        second = client.get("/api/session")

    assert first.status_code == 200
    assert "sat_session=" in first.headers["set-cookie"]
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "set-cookie" not in second.headers
    assert second.json()["snapshot"]["status"] == ""


def test_reset_and_forget_return_camel_case_json(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        reset = client.post("/api/session/reset")
        forgotten = client.delete("/api/session")

    assert reset.status_code == 200
    assert "questionText" in reset.json()["snapshot"]
    assert forgotten.json() == {"messagesErased": 0}

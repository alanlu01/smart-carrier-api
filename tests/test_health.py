from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_health_does_not_require_database():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database_backend"] == "oracle"


def test_readiness_reports_database_success(monkeypatch):
    monkeypatch.setattr(main, "ping_database", lambda: None)
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_hides_database_error(monkeypatch):
    def fail():
        raise RuntimeError("secret connection detail")

    monkeypatch.setattr(main, "ping_database", fail)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Oracle Database is unavailable"}

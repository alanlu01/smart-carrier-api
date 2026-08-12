from fastapi.testclient import TestClient

from app.main import app


def test_health_does_not_require_database():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import repository
from app.main import app
from app.security import require_robot_token

client = TestClient(app)


def task_record(**overrides):
    now = datetime.now(UTC)
    record = {
        "id": uuid4(),
        "location_code": "A1",
        "task_type": "borrow",
        "status": "pending",
        "note": None,
        "result_note": None,
        "required_charge": 80,
        "quantity": 1,
        "robot_id": None,
        "created_at": now,
        "updated_at": now,
        "assigned_at": None,
        "completed_at": None,
    }
    return {**record, **overrides}


def test_create_order_uses_oracle_repository(monkeypatch):
    expected = task_record()
    monkeypatch.setattr(repository, "create_order", lambda _payload: expected)

    response = client.post(
        "/api/v1/orders",
        json={"location_code": "A1", "task_type": "borrow", "required_charge": 80},
    )

    assert response.status_code == 201
    assert response.json()["location_code"] == "A1"
    assert response.json()["task_type"] == "borrow"


def test_create_order_rejects_unknown_location(monkeypatch):
    monkeypatch.setattr(repository, "create_order", lambda _payload: None)

    response = client.post("/api/v1/orders", json={"location_code": "UNKNOWN"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Location not found"


def test_robot_endpoint_requires_token():
    response = client.post("/api/v1/robots/R1/heartbeat", json={"mode": "idle"})
    assert response.status_code == 401


def test_non_ascii_robot_token_is_rejected_instead_of_crashing():
    with pytest.raises(HTTPException) as exc_info:
        require_robot_token("Bearer 錯誤-token")

    assert exc_info.value.status_code == 401

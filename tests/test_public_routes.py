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


def test_cancel_order_returns_conflict_after_task_starts(monkeypatch):
    monkeypatch.setattr(repository, "cancel_order", lambda _task_id: False)

    response = client.post(f"/api/v1/orders/{uuid4()}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == "Task cannot be cancelled"


def test_robot_endpoint_requires_token():
    response = client.post("/api/v1/robots/R1/heartbeat", json={"mode": "idle"})
    assert response.status_code == 401


def test_non_ascii_robot_token_is_rejected_instead_of_crashing():
    with pytest.raises(HTTPException) as exc_info:
        require_robot_token("Bearer 錯誤-token")

    assert exc_info.value.status_code == 401


def test_robot_claim_passes_validated_three_slot_snapshot(monkeypatch):
    captured = {}

    def fake_claim(robot_id, payload):
        captured["robot_id"] = robot_id
        captured["payload"] = payload
        return None

    monkeypatch.setitem(app.dependency_overrides, require_robot_token, lambda: None)
    monkeypatch.setattr(repository, "claim_task", fake_claim)

    response = client.post(
        "/api/v1/robots/R1/tasks/claim",
        json={
            "slots": [
                {"slot": 1, "status": "ready", "charge": 96},
                {"slot": 2, "status": "low", "charge": 45},
                {"slot": 3, "status": "empty", "charge": 0},
            ]
        },
    )

    assert response.status_code == 204
    assert captured["robot_id"] == "R1"
    assert [slot.slot for slot in captured["payload"].slots] == [1, 2, 3]


def test_robot_claim_rejects_incomplete_slot_snapshot(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, require_robot_token, lambda: None)

    response = client.post(
        "/api/v1/robots/R1/tasks/claim",
        json={
            "slots": [
                {"slot": 1, "status": "ready", "charge": 96},
                {"slot": 2, "status": "low", "charge": 45},
            ]
        },
    )

    assert response.status_code == 422


def test_robot_release_returns_conflict_if_task_is_not_owned(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, require_robot_token, lambda: None)
    monkeypatch.setattr(repository, "release_task", lambda *_args: False)

    response = client.post(
        "/api/v1/robots/R1/tasks/task-1/release",
        json={"note": "inventory changed"},
    )

    assert response.status_code == 409

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
        "power_bank_id": None,
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
    expected = task_record(power_bank_id="PB-02")
    captured = {}

    def fake_create_order(payload):
        captured["payload"] = payload
        return expected

    monkeypatch.setattr(repository, "create_order", fake_create_order)

    response = client.post(
        "/api/v1/orders",
        json={
            "location_code": "A1",
            "task_type": "borrow",
            "power_bank_id": "pb-02",
            "required_charge": 80,
        },
    )

    assert response.status_code == 201
    assert response.json()["location_code"] == "A1"
    assert response.json()["task_type"] == "borrow"
    assert response.json()["power_bank_id"] == "PB-02"
    assert captured["payload"].power_bank_id == "PB-02"


def test_task_response_marks_naive_oracle_timestamps_as_utc(monkeypatch):
    oracle_timestamp = datetime(2026, 8, 22, 9, 6, 15)
    expected = task_record(
        created_at=oracle_timestamp,
        updated_at=oracle_timestamp,
        assigned_at=oracle_timestamp,
        completed_at=oracle_timestamp,
    )
    monkeypatch.setattr(repository, "get_order", lambda _task_id: expected)

    response = client.get(f"/api/v1/orders/{expected['id']}")

    assert response.status_code == 200
    assert response.json()["created_at"] == "2026-08-22T09:06:15Z"
    assert response.json()["updated_at"] == "2026-08-22T09:06:15Z"
    assert response.json()["assigned_at"] == "2026-08-22T09:06:15Z"
    assert response.json()["completed_at"] == "2026-08-22T09:06:15Z"


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


def test_public_robot_status_returns_live_slots_without_robot_token(monkeypatch):
    now = datetime(2026, 8, 22, 9, 6, 15)
    monkeypatch.setattr(
        repository,
        "get_robot_status",
        lambda _robot_id: {
            "id": "R1",
            "online": True,
            "mode": "idle",
            "battery": None,
            "location_code": "A1",
            "x": -0.45,
            "y": -0.35,
            "yaw": 0.0,
            "last_seen_at": now,
            "current_task_id": None,
            "slots": [
                {
                    "slot": 1,
                    "bank_id": "PB-01",
                    "status": "ready",
                    "voltage": 5.0,
                    "current": 0.1,
                    "charge": 96,
                    "sensor_ok": True,
                    "updated_at": now,
                },
                {
                    "slot": 2,
                    "bank_id": "PB-02",
                    "status": "low",
                    "voltage": 5.0,
                    "current": 0.5,
                    "charge": 40,
                    "sensor_ok": True,
                    "updated_at": now,
                },
                {
                    "slot": 3,
                    "bank_id": None,
                    "status": "empty",
                    "voltage": 0.0,
                    "current": 0.0,
                    "charge": 0,
                    "sensor_ok": True,
                    "updated_at": now,
                },
            ],
        },
    )

    response = client.get("/api/v1/robots/R1/status")

    assert response.status_code == 200
    assert response.json()["battery"] is None
    assert [slot["status"] for slot in response.json()["slots"]] == [
        "ready",
        "low",
        "empty",
    ]
    assert response.json()["last_seen_at"] == "2026-08-22T09:06:15Z"
    assert response.json()["slots"][0]["updated_at"] == "2026-08-22T09:06:15Z"


def test_public_robot_status_returns_not_found(monkeypatch):
    monkeypatch.setattr(repository, "get_robot_status", lambda _robot_id: None)

    response = client.get("/api/v1/robots/UNKNOWN/status")

    assert response.status_code == 404


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

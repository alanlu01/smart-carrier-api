from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import repository
from app.main import app
from app.schemas import LocationCreate, LocationInput
from app.security import require_admin_session

client = TestClient(app)
PAYLOAD = {"name": "測試地點", "floor": "3F", "x": 1.4, "y": -5.3, "yaw": 0}


@pytest.fixture
def admin_session(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, require_admin_session, lambda: None)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/v1/admin/locations", {"code": "T1", **PAYLOAD}),
        ("PATCH", "/api/v1/admin/locations/T1", PAYLOAD),
        ("DELETE", "/api/v1/admin/locations/T1", None),
    ],
)
def test_location_writes_require_admin(method, path, body):
    assert client.request(method, path, json=body).status_code == 401


def test_create_normalizes_code_and_returns_saved_location(admin_session, monkeypatch):
    captured = []

    def create(payload):
        captured.append(payload)
        return payload.model_dump()

    monkeypatch.setattr(repository, "create_location", create)
    response = client.post("/api/v1/admin/locations", json={"code": " t1 ", **PAYLOAD})
    assert response.status_code == 201
    assert response.json()["code"] == "T1"
    assert response.json()["x"] == 1.4
    assert captured[0].code == "T1"


@pytest.mark.parametrize(
    "invalid",
    [
        {"code": "A-1"},
        {"code": "中文"},
        {"name": "   "},
        {"floor": " "},
        {"x": "NaN"},
        {"y": "Infinity"},
        {"yaw": "-Infinity"},
        {"x": None},
        {"name": "地" * 100},
        {"description": "字" * 400},
        {"floor": "層" * 20},
    ],
)
def test_invalid_location_is_rejected(admin_session, invalid):
    response = client.post("/api/v1/admin/locations", json={"code": "T1", **PAYLOAD, **invalid})
    assert response.status_code == 422


def test_duplicate_code_returns_conflict(admin_session, monkeypatch):
    def conflict(_payload):
        raise repository.LocationConflict("duplicate code")

    monkeypatch.setattr(repository, "create_location", conflict)
    response = client.post("/api/v1/admin/locations", json={"code": "T1", **PAYLOAD})
    assert response.status_code == 409


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_active_location_conflict_is_explained(admin_session, monkeypatch, method):
    def conflict(*_args):
        raise repository.LocationHasActiveTasks("location has active tasks")

    monkeypatch.setattr(
        repository, "edit_location" if method == "PATCH" else "delete_location", conflict
    )
    response = client.request(
        method, "/api/v1/admin/locations/T1", json=PAYLOAD if method == "PATCH" else None
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "location has active tasks"


def test_edit_cannot_change_code(admin_session):
    response = client.patch("/api/v1/admin/locations/T1", json={**PAYLOAD, "code": "T2"})
    assert response.status_code == 422


def test_edit_and_delete_use_normalized_code(admin_session, monkeypatch):
    calls = []

    def edit(code, payload):
        calls.append(code)
        return {"code": code, **payload.model_dump()}

    def delete(code):
        calls.append(code)
        return True

    monkeypatch.setattr(repository, "edit_location", edit)
    monkeypatch.setattr(repository, "delete_location", delete)
    edited = client.patch("/api/v1/admin/locations/t1", json=PAYLOAD)
    assert edited.status_code == 200
    assert edited.json()["code"] == "T1"
    assert client.delete("/api/v1/admin/locations/t1").json() == {"ok": True}
    assert calls == ["T1", "T1"]


def test_edit_and_delete_return_not_found(admin_session, monkeypatch):
    monkeypatch.setattr(repository, "edit_location", lambda *_args: None)
    monkeypatch.setattr(repository, "delete_location", lambda *_args: False)
    assert client.patch("/api/v1/admin/locations/T1", json=PAYLOAD).status_code == 404
    assert client.delete("/api/v1/admin/locations/T1").status_code == 404


def fake_database(monkeypatch, *, active_tasks=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = (active_tasks,)
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def get_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", get_connection)
    return connection, cursor


@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_active_tasks_prevent_mutations_and_roll_back(monkeypatch, operation):
    connection, cursor = fake_database(monkeypatch, active_tasks=1)
    with pytest.raises(repository.LocationHasActiveTasks):
        if operation == "edit":
            repository.edit_location("T1", LocationInput(**PAYLOAD))
        else:
            repository.delete_location("T1")
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    assert not any("UPDATE locations" in call.args[0] for call in cursor.execute.call_args_list)


def test_delete_preserves_history_and_seed_identity(monkeypatch):
    connection, cursor = fake_database(monkeypatch)
    assert repository.delete_location("T1")
    connection.commit.assert_called_once()
    assert "SET enabled = 0" in cursor.execute.call_args.args[0]
    assert "DELETE FROM" not in cursor.execute.call_args.args[0]


def test_archived_code_cannot_be_reused(monkeypatch):
    connection, _cursor = fake_database(monkeypatch)
    with pytest.raises(repository.LocationConflict):
        repository.create_location(LocationCreate(code="T1", **PAYLOAD))
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_delete_cors_preflight_is_allowed():
    response = client.options(
        "/api/v1/admin/locations/T1",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]

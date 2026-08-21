from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app import repository
from app.schemas import Heartbeat


def test_heartbeat_avoids_reserved_mode_bind_name(monkeypatch):
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    repository.record_heartbeat("R1", Heartbeat(mode="idle"))

    sql = cursor.execute.call_args.args[0]
    bind_values = cursor.execute.call_args.kwargs
    assert ":robot_mode" in sql
    assert ":mode" not in sql
    assert bind_values["robot_mode"] == "idle"
    connection.commit.assert_called_once_with()


def test_heartbeat_persists_voltage_and_sensor_health(monkeypatch):
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    repository.record_heartbeat(
        "R1",
        Heartbeat(
            mode="idle",
            slots=[
                {
                    "slot": 1,
                    "bank_id": "PB-01",
                    "status": "ready",
                    "voltage": 5.04,
                    "current": 0.1,
                    "charge": 96,
                    "sensor_ok": True,
                }
            ],
        ),
    )

    slot_call = cursor.execute.call_args_list[1]
    assert "voltage_volts = :voltage_volts" in slot_call.args[0]
    assert "sensor_ok = :sensor_ok" in slot_call.args[0]
    assert slot_call.kwargs["voltage_volts"] == 5.04
    assert slot_call.kwargs["sensor_ok"] == 1


def test_robot_online_requires_recent_heartbeat():
    now = datetime.now(UTC)

    assert repository.robot_is_online(now - timedelta(seconds=10), now)
    assert not repository.robot_is_online(now - timedelta(seconds=20), now)


def test_robot_status_always_returns_three_slots(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("task-1",)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    robot = {
        "id": "R1",
        "robot_mode": "dispatching",
        "battery": None,
        "location_code": "A1",
        "x": 0.0,
        "y": 0.0,
        "yaw": 0.0,
        "last_seen_at": datetime.now(UTC),
    }
    saved_slots = [
        {
            "slot": 1,
            "bank_id": "PB-01",
            "status": "ready",
            "voltage": 5.0,
            "current_amps": 0.1,
            "charge": 96,
            "sensor_ok": 1,
            "updated_at": datetime.now(UTC),
        }
    ]
    monkeypatch.setattr(repository, "get_connection", fake_connection)
    monkeypatch.setattr(repository, "_fetch_one", lambda _cursor: robot)
    monkeypatch.setattr(repository, "_fetch_all", lambda _cursor: saved_slots)

    status = repository.get_robot_status("R1")

    assert status["mode"] == "dispatching"
    assert status["current_task_id"] == "task-1"
    assert len(status["slots"]) == 3
    assert status["slots"][0]["current"] == 0.1
    assert status["slots"][1]["status"] == "unknown"
    assert status["slots"][1]["sensor_ok"] is False


def test_cancel_order_only_updates_pending_tasks(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.cancel_order("task-1") is True

    sql = cursor.execute.call_args.args[0]
    assert "status = 'pending'" in sql
    assert "in_progress" not in sql
    connection.commit.assert_called_once_with()


def test_release_task_only_requeues_task_owned_by_robot(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.release_task("R1", "task-1", "inventory changed") is True

    sql = cursor.execute.call_args.args[0]
    bind_values = cursor.execute.call_args.kwargs
    assert "status = 'pending'" in sql
    assert "robot_id = NULL" in sql
    assert "status = 'in_progress'" in sql
    assert bind_values == {
        "release_note": "inventory changed",
        "id": "task-1",
        "robot_id": "R1",
    }
    connection.commit.assert_called_once_with()

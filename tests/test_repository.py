from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app import repository
from app.schemas import Heartbeat, TaskCreate, TaskProgress, TaskRelease, TaskResult


def test_public_locations_and_new_orders_only_use_enabled_locations(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.list_locations() == []
    list_sql = cursor.execute.call_args.args[0]
    assert "WHERE enabled = 1" in list_sql

    assert repository.create_order(TaskCreate(location_code="S1")) is None
    create_sql = cursor.execute.call_args.args[0]
    assert "WHERE code = :code AND enabled = 1" in create_sql


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


def test_heartbeat_treats_legacy_disabled_slot_as_not_enabled(monkeypatch):
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    repository.record_heartbeat(
        "R1",
        Heartbeat(slots=[{"slot": 3, "status": "disabled", "sensor_ok": True}]),
    )

    assert cursor.execute.call_args_list[1].kwargs["enabled"] == 0


def test_robot_online_requires_recent_heartbeat():
    now = datetime.now(UTC)

    assert repository.robot_is_online(now - timedelta(seconds=10), now)
    assert not repository.robot_is_online(now - timedelta(seconds=20), now)


def test_robot_status_always_returns_three_slots(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [("task-1", "navigating"), ("task-2", "queued_on_robot")]
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
            "enabled": 1,
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
    assert status["claimed_task_ids"] == ["task-1", "task-2"]
    assert len(status["slots"]) == 3
    assert status["slots"][0]["current"] == 0.1
    assert status["slots"][1]["status"] == "unknown"
    assert status["slots"][1]["sensor_ok"] is False
    task_query = cursor.execute.call_args_list[1].args[0]
    assert "progress_state IN" in task_query
    assert "assigned_at ASC" in task_query


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


def test_force_cancel_immediately_cancels_pending_task(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("pending", None)
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.force_cancel_order("task-1", "admin") == "cancelled"
    update_sql = cursor.execute.call_args_list[1].args[0]
    assert "status = 'cancelled'" in update_sql
    assert "completed_at = SYSTIMESTAMP" in update_sql


def test_force_cancel_requests_stop_for_online_robot(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("in_progress", "R1"),
        (datetime.now(UTC),),
    ]
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.force_cancel_order("task-1", "admin") == "cancellation_requested"
    update_sql = cursor.execute.call_args_list[1].args[0]
    assert "cancel_requested_at" in update_sql
    assert "status = 'cancelled'" not in update_sql


def test_force_cancel_offline_robot_still_waits_for_safe_stop(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        ("in_progress", "R1"),
        (datetime.now(UTC) - timedelta(minutes=1),),
    ]
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.force_cancel_order("task-1", "admin") == "cancellation_requested"
    update_sql = cursor.execute.call_args_list[1].args[0]
    assert "status = 'cancelled'" not in update_sql
    assert "cancel_requested_at" in update_sql


def test_force_finalize_clears_action_state(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    assert repository.force_finalize_order("task-1", "operator stopped") is True
    sql = cursor.execute.call_args.args[0]
    assert "status = 'cancelled'" in sql
    assert "progress_state = 'cancelled'" in sql
    assert "warning = 0" in sql


def test_complete_task_clears_stale_action_fields(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    payload = TaskResult(
        event_id="85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        status="done",
        note="confirmed",
    )

    assert repository.complete_task("R1", "task-1", payload) is True
    sql = cursor.execute.call_args_list[1].args[0]
    assert "progress_state = 'result_acked'" in sql
    assert "changed_slots = NULL" in sql
    assert "warning = 0" in sql


def test_release_task_only_requeues_task_owned_by_robot(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    cursor.fetchone.return_value = None
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)

    payload = TaskRelease(
        event_id="85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        note="inventory changed",
    )
    assert repository.release_task("R1", "task-1", payload) is True

    sql = cursor.execute.call_args_list[1].args[0]
    bind_values = cursor.execute.call_args_list[1].kwargs
    assert "status = 'pending'" in sql
    assert "robot_id = NULL" in sql
    assert "status = 'in_progress'" in sql
    assert bind_values == {
        "result_note": "inventory changed",
        "id": "task-1",
        "robot_id": "R1",
    }
    connection.commit.assert_called_once_with()


def test_task_row_decodes_changed_slots_and_exposes_progress_event_id():
    cursor = MagicMock()
    cursor.description = [
        ("CHANGED_SLOTS",),
        ("PROGRESS_EVENT_ID",),
    ]

    row = repository._row_as_dict(
        cursor,
        ("2,3", "85af9ce7-6b7d-4a3d-8afb-155334a0aa4f"),
    )

    assert row["changed_slots"] == [2, 3]
    assert row["progress_event_id"] == "85af9ce7-6b7d-4a3d-8afb-155334a0aa4f"


def test_record_task_progress_persists_all_changed_slots(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    payload = TaskProgress(
        event_id="85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        task_id="95af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        progress_state="wrong_slot",
        expected_slot=1,
        changed_slot=2,
        changed_slots=[3, 2, 2],
    )

    assert repository.record_task_progress("R1", str(payload.task_id), payload) is True

    sql = cursor.execute.call_args.args[0]
    binds = cursor.execute.call_args.kwargs
    assert "changed_slots = :changed_slots" in sql
    assert binds["changed_slots"] == "2,3"
    assert binds["progress_event_id"] == str(payload.event_id)


def test_claim_capacity_counts_existing_tasks_under_robot_lock(monkeypatch):
    from app.schemas import TaskClaim

    cursor = MagicMock()
    cursor.fetchone.side_effect = [("R1",), (3,)]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    payload = TaskClaim(slots=[{"slot": n, "status": "unknown"} for n in range(1, 4)])
    assert repository.claim_task("R1", payload) is None
    assert "FOR UPDATE" in cursor.execute.call_args_list[0].args[0]
    assert len(cursor.execute.call_args_list) == 2
    connection.commit.assert_not_called()


def test_claim_request_id_returns_the_previously_assigned_task(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("R1",)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    existing = {
        "id": "task-1",
        "location_code": "A1",
        "claim_request_id": "85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
    }
    location = {"code": "A1", "name": "右樓梯口"}
    fetched = iter([existing, location])

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    monkeypatch.setattr(repository, "_fetch_one", lambda _cursor: next(fetched))
    payload = repository.TaskClaim(
        claim_request_id="85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        slots=[{"slot": n, "status": "unknown"} for n in range(1, 4)],
    )

    task = repository.claim_task("R1", payload)

    assert task["id"] == "task-1"
    assert task["location"] == location
    assert all("COUNT(*)" not in call.args[0] for call in cursor.execute.call_args_list)


def test_progress_rejects_second_executing_task(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("R1",)
    cursor.fetchall.return_value = [("other-task", "navigating")]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "get_connection", fake_connection)
    payload = TaskProgress(
        event_id="85af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        task_id="95af9ce7-6b7d-4a3d-8afb-155334a0aa4f",
        progress_state="navigating",
    )
    assert repository.record_task_progress("R1", str(payload.task_id), payload) is False
    assert all("UPDATE tasks" not in call.args[0] for call in cursor.execute.call_args_list)


def test_slot_charge_obeys_sensor_status():
    for status, expected in [
        ("empty", 0),
        ("full", 100),
        ("low", None),
        ("unknown", None),
        ("disabled", None),
    ]:
        slot = repository.normalize_slot({"status": status, "sensor_ok": True, "charge": 42})
        assert slot["charge"] == expected
    assert repository.normalize_slot({"status": "full", "sensor_ok": False})["charge"] is None
    assert repository.normalize_slot({"status": "full", "enabled": False})["status"] == "disabled"

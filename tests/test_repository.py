from contextlib import contextmanager
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

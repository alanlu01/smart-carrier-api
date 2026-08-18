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

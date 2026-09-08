"""Opt-in Oracle integration check using disposable, uniquely named QA tables.

Run against a migrated database: python scripts/verify_oracle_queue.py
Requires httpx for FastAPI TestClient. No production orders or robots are modified.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app import repository
from app.database import get_connection
from app.main import app
from app.security import require_admin_session, require_robot_token


def main():
    prefix = "qa_" + uuid4().hex[:8] + "_"
    tables = ["locations", "robots", "tasks", "power_slots", "robot_events"]
    created = []
    original_connection = repository.get_connection
    previous_overrides = dict(app.dependency_overrides)

    def rewrite(sql):
        return re.sub(r"\b(" + "|".join(tables) + r")\b", lambda m: prefix + m[0], sql)

    class Cursor:
        def __init__(self, cursor):
            self.inner = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.inner.close()

        def execute(self, sql, **binds):
            return self.inner.execute(rewrite(sql), **binds)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    class Connection:
        def __init__(self, connection):
            self.inner = connection

        def cursor(self):
            return Cursor(self.inner.cursor())

        def __getattr__(self, name):
            return getattr(self.inner, name)

    @contextmanager
    def qa_connection():
        with get_connection() as connection:
            yield Connection(connection)

    try:
        with get_connection() as connection, connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"CREATE TABLE {prefix}{table} AS SELECT * FROM {table} WHERE 1=0")
                created.append(table)
            # Also permits pre-deployment checks of the new warning column.
            cursor.execute(f"SELECT * FROM {prefix}tasks WHERE 1=0")
            if "WARNING" not in [column[0] for column in cursor.description]:
                cursor.execute(f"ALTER TABLE {prefix}tasks ADD warning NUMBER(1) DEFAULT 0")
            cursor.execute(f"ALTER TABLE {prefix}tasks MODIFY warning DEFAULT 0")
            cursor.execute(
                f"ALTER TABLE {prefix}robot_events MODIFY created_at DEFAULT SYSTIMESTAMP"
            )
            cursor.execute(f"INSERT INTO {prefix}locations SELECT * FROM locations")
            connection.commit()
        repository.get_connection = qa_connection
        app.dependency_overrides[require_robot_token] = lambda: None
        app.dependency_overrides[require_admin_session] = lambda: None
        client = TestClient(app)
        unknown = [
            {"slot": n, "status": "unknown", "enabled": True, "sensor_ok": False}
            for n in range(1, 4)
        ]
        base = "/api/v1/robots/QA"
        assert client.post(base + "/heartbeat", json={"slots": unknown}).status_code == 200
        locations = client.get("/api/v1/locations").json()
        assert {item["code"] for item in locations} == {"A1", "E1", "F1"}
        assert client.post("/api/v1/orders", json={"location_code": "S1"}).status_code == 404
        ids = []
        for _ in range(4):
            response = client.post(
                "/api/v1/orders", json={"location_code": "A1", "task_type": "navigation"}
            )
            assert response.status_code == 201, response.text
            ids.append(response.json()["id"])

        def claim(_):
            return client.post(base + "/tasks/claim", json={"slots": unknown})

        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(claim, range(4)))
        assert sorted(response.status_code for response in responses) == [200, 200, 200, 204]
        claimed = {response.json()["id"] for response in responses if response.status_code == 200}
        assert claimed == set(ids[:3]), (claimed, ids)

        def progress(task_id, state, **extra):
            return client.post(
                base + f"/tasks/{task_id}/progress",
                json={
                    "task_id": task_id,
                    "event_id": str(uuid4()),
                    "progress_state": state,
                    **extra,
                },
            )

        assert progress(ids[0], "navigating").status_code == 200
        assert progress(ids[1], "navigating").status_code >= 400
        status = client.get(base + "/status").json()
        assert status["current_task_id"] == ids[0]
        assert set(status["claimed_task_ids"]) == claimed
        assert client.get(f"/api/v1/orders/{ids[3]}").json()["status"] == "pending"
        assert client.get(f"/api/v1/orders/{ids[1]}").json()["progress_state"] == "queued_on_robot"
        # Recreate the HTTP client; all queue state must still be in Oracle.
        client = TestClient(app)
        assert set(client.get(base + "/status").json()["claimed_task_ids"]) == claimed
        result = {"event_id": str(uuid4()), "status": "done", "note": "QA navigation complete"}
        for _ in range(2):
            assert client.post(base + f"/tasks/{ids[0]}/result", json=result).status_code == 200
        assert claim(0).json()["id"] == ids[3]
        assert claim(0).status_code == 204
        assert len(client.get("/api/v1/admin/orders").json()) == 4
        assert progress(ids[1], "arrived").status_code == 200
        assert client.get(f"/api/v1/orders/{ids[1]}").json()["status"] == "in_progress"
        assert (
            progress(
                ids[1],
                "wrong_slot",
                warning=True,
                expected_slot=1,
                changed_slot=2,
                changed_slots=[2, 3],
                action_deadline=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            ).status_code
            == 200
        )
        task = client.get(f"/api/v1/orders/{ids[1]}").json()
        assert task["warning"] and task["changed_slots"] == [2, 3]
        assert progress(ids[1], "result_pending").status_code == 200
        assert client.get(f"/api/v1/orders/{ids[1]}").json()["status"] == "in_progress"
        with qa_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE robots SET last_seen_at = :seen WHERE id = :id",
                seen=datetime.now(UTC) - timedelta(minutes=1),
                id="QA",
            )
            connection.commit()
        cancellation = client.post(f"/api/v1/admin/orders/{ids[1]}/force-cancel", json={})
        assert cancellation.json()["outcome"] == "cancellation_requested"
        assert client.get(f"/api/v1/orders/{ids[1]}").json()["status"] == "in_progress"
        assert (
            client.post(
                base + f"/tasks/{ids[1]}/result",
                json={
                    "event_id": str(uuid4()),
                    "status": "cancelled",
                    "note": "QA safe stop confirmed",
                },
            ).status_code
            == 200
        )
        print("PASS: Oracle claims capped at 3; FIFO refill; queue persists across clients;")
        print("single active navigation; 4 separate orders; idempotent result; wrong-slot warning;")
        print("arrival/result_pending nonterminal; offline cancellation waits for safe stop.")
    finally:
        repository.get_connection = original_connection
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        with get_connection() as connection, connection.cursor() as cursor:
            for table in reversed(created):
                cursor.execute(f"DROP TABLE {prefix}{table} PURGE")
        print(f"Removed {len(created)} QA tables ({prefix}); production records unchanged.")


if __name__ == "__main__":
    main()

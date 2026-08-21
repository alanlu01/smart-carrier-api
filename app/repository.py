from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.database import get_connection
from app.schemas import Heartbeat, TaskCreate, TaskResult

LOCATION_COLUMNS = "code, name, description, floor, x, y, yaw"
TASK_COLUMNS = """
    id, location_code, task_type, status, note, result_note,
    required_charge, quantity, robot_id, created_at, updated_at,
    assigned_at, completed_at
"""


class LocationHasActiveTasks(RuntimeError):
    pass


def _row_as_dict(cursor, row) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [column[0].lower() for column in cursor.description]
    return dict(zip(columns, row, strict=True))


def _fetch_one(cursor) -> dict[str, Any] | None:
    return _row_as_dict(cursor, cursor.fetchone())


def _fetch_all(cursor) -> list[dict[str, Any]]:
    return [_row_as_dict(cursor, row) for row in cursor.fetchall()]


def list_locations() -> list[dict[str, Any]]:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {LOCATION_COLUMNS} FROM locations ORDER BY code")
        return _fetch_all(cursor)


def get_location(location_code: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {LOCATION_COLUMNS} FROM locations WHERE code = :code",
            code=location_code.upper(),
        )
        return _fetch_one(cursor)


def update_location_coordinates(
    location_code: str,
    x: float,
    y: float,
    yaw: float,
    *,
    name: str | None = None,
) -> dict[str, Any] | None:
    code = location_code.upper()
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM tasks
            WHERE location_code = :code AND status IN ('pending', 'in_progress')
            """,
            code=code,
        )
        if cursor.fetchone()[0]:
            raise LocationHasActiveTasks(
                f"Location {code} has pending or in-progress tasks; coordinates unchanged"
            )
        cursor.execute(
            """
            UPDATE locations
            SET name = COALESCE(:location_name, name),
                x = :x, y = :y, yaw = :yaw
            WHERE code = :code
            """,
            code=code,
            location_name=name,
            x=x,
            y=y,
            yaw=yaw,
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return None
        connection.commit()
        cursor.execute(f"SELECT {LOCATION_COLUMNS} FROM locations WHERE code = :code", code=code)
        return _fetch_one(cursor)


def create_order(payload: TaskCreate) -> dict[str, Any] | None:
    task_id = str(uuid4())
    location_code = payload.location_code.upper()
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM locations WHERE code = :code", code=location_code)
        if cursor.fetchone() is None:
            return None
        cursor.execute(
            """
            INSERT INTO tasks (
                id, location_code, task_type, status, note,
                required_charge, quantity, created_at, updated_at
            ) VALUES (
                :id, :location_code, :task_type, 'pending', :note,
                :required_charge, :quantity, SYSTIMESTAMP, SYSTIMESTAMP
            )
            """,
            id=task_id,
            location_code=location_code,
            task_type=payload.task_type,
            note=payload.note,
            required_charge=payload.required_charge,
            quantity=payload.quantity,
        )
        connection.commit()
        cursor.execute(f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = :id", id=task_id)
        return _fetch_one(cursor)


def list_orders(limit: int) -> list[dict[str, Any]]:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {TASK_COLUMNS}
            FROM (
                SELECT {TASK_COLUMNS}
                FROM tasks
                ORDER BY created_at DESC
            )
            WHERE ROWNUM <= :limit
            """,
            limit=limit,
        )
        return _fetch_all(cursor)


def get_order(task_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = :id", id=task_id)
        return _fetch_one(cursor)


def cancel_order(task_id: str) -> bool:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'cancelled', updated_at = SYSTIMESTAMP
            WHERE id = :id AND status IN ('pending', 'in_progress')
            """,
            id=task_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed


def record_heartbeat(robot_id: str, payload: Heartbeat) -> None:
    now = datetime.now(UTC)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            MERGE INTO robots target
            USING (SELECT :id AS id FROM dual) source
            ON (target.id = source.id)
            WHEN MATCHED THEN UPDATE SET
                robot_mode = :robot_mode,
                battery = :battery,
                location_code = :location_code,
                x = :x,
                y = :y,
                yaw = :yaw,
                last_seen_at = :last_seen_at
            WHEN NOT MATCHED THEN INSERT (
                id, robot_mode, battery, location_code, x, y, yaw,
                last_seen_at, created_at
            ) VALUES (
                :id, :robot_mode, :battery, :location_code, :x, :y, :yaw,
                :last_seen_at, :last_seen_at
            )
            """,
            id=robot_id,
            robot_mode=payload.mode,
            battery=payload.battery,
            location_code=payload.location_code,
            x=payload.x,
            y=payload.y,
            yaw=payload.yaw,
            last_seen_at=now,
        )
        for slot_number, slot in enumerate(payload.slots[:3], start=1):
            bank_id = slot.get("bank_id") or slot.get("id")
            cursor.execute(
                """
                MERGE INTO power_slots target
                USING (
                    SELECT :robot_id AS robot_id, :slot_number AS slot_number FROM dual
                ) source
                ON (
                    target.robot_id = source.robot_id
                    AND target.slot_number = source.slot_number
                )
                WHEN MATCHED THEN UPDATE SET
                    bank_id = :bank_id,
                    status = :status,
                    current_amps = :current_amps,
                    charge = :charge,
                    updated_at = :updated_at
                WHEN NOT MATCHED THEN INSERT (
                    robot_id, slot_number, bank_id, status,
                    current_amps, charge, updated_at
                ) VALUES (
                    :robot_id, :slot_number, :bank_id, :status,
                    :current_amps, :charge, :updated_at
                )
                """,
                robot_id=robot_id,
                slot_number=slot_number,
                bank_id=str(bank_id) if bank_id is not None else None,
                status=str(slot.get("status", "empty")),
                current_amps=slot.get("current"),
                charge=slot.get("charge"),
                updated_at=now,
            )
        connection.commit()


def claim_task(robot_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        for _ in range(3):
            cursor.execute(
                """
                SELECT id
                FROM (
                    SELECT id FROM tasks
                    WHERE status = 'pending'
                    ORDER BY created_at
                )
                WHERE ROWNUM = 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return None
            task_id = row[0]
            cursor.execute(
                """
                UPDATE tasks
                SET status = 'in_progress', robot_id = :robot_id,
                    assigned_at = SYSTIMESTAMP, updated_at = SYSTIMESTAMP
                WHERE id = :id AND status = 'pending'
                """,
                robot_id=robot_id,
                id=task_id,
            )
            if cursor.rowcount == 1:
                connection.commit()
                cursor.execute(f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = :id", id=task_id)
                task = _fetch_one(cursor)
                cursor.execute(
                    f"SELECT {LOCATION_COLUMNS} FROM locations WHERE code = :code",
                    code=task["location_code"],
                )
                task["location"] = _fetch_one(cursor)
                return task
            connection.rollback()
        return None


def complete_task(robot_id: str, task_id: str, payload: TaskResult) -> bool:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tasks
            SET status = :status, result_note = :result_note,
                completed_at = SYSTIMESTAMP, updated_at = SYSTIMESTAMP
            WHERE id = :id AND robot_id = :robot_id AND status = 'in_progress'
            """,
            status=payload.status,
            result_note=payload.note,
            id=task_id,
            robot_id=robot_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed

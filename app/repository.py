from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.database import get_connection
from app.schemas import Heartbeat, TaskClaim, TaskClaimSlot, TaskCreate, TaskResult

LOCATION_COLUMNS = "code, name, description, floor, x, y, yaw"
TASK_COLUMNS = """
    id, location_code, task_type, status, note, result_note,
    power_bank_id, required_charge, quantity, robot_id, created_at, updated_at,
    assigned_at, completed_at
"""


class LocationHasActiveTasks(RuntimeError):
    pass


NAVIGATION_ONLY_TASK_TYPES = {"delivery", "navigation", "callbot"}
ROBOT_ONLINE_TIMEOUT_SECONDS = 15


def task_is_compatible(
    task_type: str,
    required_charge: int | None,
    quantity: int,
    slots: list[TaskClaimSlot],
    power_bank_id: str | None = None,
) -> bool:
    """Return whether this robot can execute a pending task from its current slots."""
    if quantity != 1:
        return False
    if task_type in NAVIGATION_ONLY_TASK_TYPES:
        return True
    healthy_slots = [slot for slot in slots if slot.sensor_ok and slot.status != "unknown"]
    if task_type == "return":
        return any(slot.status == "empty" for slot in healthy_slots)
    if task_type == "borrow":
        minimum_charge = required_charge or 0
        return any(
            slot.status in {"ready", "full"}
            and (power_bank_id is None or slot.bank_id == power_bank_id)
            and (slot.charge is None or slot.charge >= minimum_charge)
            for slot in healthy_slots
        )
    return False


def first_compatible_task_id(
    candidates: list[tuple[str, str, str | None, int | None, int]],
    slots: list[TaskClaimSlot],
) -> str | None:
    for task_id, task_type, power_bank_id, required_charge, quantity in candidates:
        if task_is_compatible(
            task_type,
            required_charge,
            quantity,
            slots,
            power_bank_id,
        ):
            return task_id
    return None


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
                power_bank_id, required_charge, quantity, created_at, updated_at
            ) VALUES (
                :id, :location_code, :task_type, 'pending', :note,
                :power_bank_id, :required_charge, :quantity,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            """,
            id=task_id,
            location_code=location_code,
            task_type=payload.task_type,
            note=payload.note,
            power_bank_id=payload.power_bank_id,
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
            WHERE id = :id AND status = 'pending'
            """,
            id=task_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed


def robot_is_online(last_seen_at: datetime, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if last_seen_at.tzinfo is None:
        current = current.replace(tzinfo=None)
    return current - last_seen_at <= timedelta(seconds=ROBOT_ONLINE_TIMEOUT_SECONDS)


def get_robot_status(robot_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, robot_mode, battery, location_code, x, y, yaw, last_seen_at
            FROM robots
            WHERE id = :id
            """,
            id=robot_id,
        )
        robot = _fetch_one(cursor)
        if robot is None:
            return None

        robot["mode"] = robot.pop("robot_mode")
        robot["online"] = robot_is_online(robot["last_seen_at"])

        cursor.execute(
            """
            SELECT id
            FROM (
                SELECT id
                FROM tasks
                WHERE robot_id = :robot_id AND status = 'in_progress'
                ORDER BY assigned_at DESC
            )
            WHERE ROWNUM = 1
            """,
            robot_id=robot_id,
        )
        task_row = cursor.fetchone()
        robot["current_task_id"] = task_row[0] if task_row else None

        cursor.execute(
            """
            SELECT slot_number AS slot, bank_id, status,
                   voltage_volts AS voltage, current_amps AS current_amps,
                   charge, sensor_ok, updated_at
            FROM power_slots
            WHERE robot_id = :robot_id
            ORDER BY slot_number
            """,
            robot_id=robot_id,
        )
        saved_slots = _fetch_all(cursor)
        slots_by_number = {int(slot["slot"]): slot for slot in saved_slots}
        robot["slots"] = [
            slots_by_number.get(
                slot_number,
                {
                    "slot": slot_number,
                    "bank_id": None,
                    "status": "unknown",
                    "voltage": None,
                    "current_amps": None,
                    "charge": None,
                    "sensor_ok": False,
                    "updated_at": None,
                },
            )
            for slot_number in range(1, 4)
        ]
        for slot in robot["slots"]:
            slot["current"] = slot.pop("current_amps")
        return robot


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
                    voltage_volts = :voltage_volts,
                    current_amps = :current_amps,
                    charge = :charge,
                    sensor_ok = :sensor_ok,
                    updated_at = :updated_at
                WHEN NOT MATCHED THEN INSERT (
                    robot_id, slot_number, bank_id, status,
                    voltage_volts, current_amps, charge, sensor_ok, updated_at
                ) VALUES (
                    :robot_id, :slot_number, :bank_id, :status,
                    :voltage_volts, :current_amps, :charge, :sensor_ok, :updated_at
                )
                """,
                robot_id=robot_id,
                slot_number=slot_number,
                bank_id=str(bank_id) if bank_id is not None else None,
                status=str(slot.get("status", "unknown")),
                voltage_volts=slot.get("voltage"),
                current_amps=slot.get("current"),
                charge=slot.get("charge"),
                sensor_ok=1 if slot.get("sensor_ok", True) else 0,
                updated_at=now,
            )
        connection.commit()


def claim_task(robot_id: str, payload: TaskClaim) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        for _ in range(3):
            cursor.execute(
                """
                SELECT id, task_type, power_bank_id, required_charge, quantity
                FROM tasks
                WHERE status = 'pending'
                ORDER BY created_at
                """
            )
            candidates = cursor.fetchall()
            task_id = first_compatible_task_id(candidates, payload.slots)
            if task_id is None:
                return None
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


def release_task(robot_id: str, task_id: str, note: str | None = None) -> bool:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'pending', robot_id = NULL, assigned_at = NULL,
                completed_at = NULL, result_note = :release_note,
                updated_at = SYSTIMESTAMP
            WHERE id = :id AND robot_id = :robot_id AND status = 'in_progress'
            """,
            release_note=note,
            id=task_id,
            robot_id=robot_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed


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

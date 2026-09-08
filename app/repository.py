import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.database import get_connection
from app.schemas import (
    Heartbeat,
    TaskClaim,
    TaskClaimSlot,
    TaskCreate,
    TaskProgress,
    TaskRelease,
    TaskResult,
)

LOCATION_COLUMNS = "code, name, description, floor, x, y, yaw"
TASK_COLUMNS = """
    id, location_code, task_type, status, note, result_note,
    power_bank_id, required_charge, quantity, robot_id, created_at, updated_at,
    assigned_at, completed_at, cancel_requested_at, cancel_reason,
    progress_state, progress_message, warning,
    expected_slot, changed_slot, changed_slots, action_deadline,
    progress_event_id, progress_updated_at
"""


class LocationHasActiveTasks(RuntimeError):
    pass


NAVIGATION_ONLY_TASK_TYPES = {"delivery", "navigation", "callbot"}
ROBOT_ONLINE_TIMEOUT_SECONDS = 15
MAX_CLAIMED_TASKS = 3
EXECUTING_PROGRESS_STATES = {
    "precheck",
    "navigating",
    "arrived",
    "waiting_action",
    "wrong_slot",
    "verifying_action",
    "result_pending",
    "recovery_required",
}


def normalize_slot(slot: dict[str, Any]) -> dict[str, Any]:
    slot = dict(slot)
    slot["enabled"] = bool(slot.get("enabled", slot.get("status") != "disabled"))
    slot["sensor_ok"] = bool(slot.get("sensor_ok", False))
    if not slot["enabled"] or slot.get("status") == "disabled":
        slot.update(status="disabled", enabled=False, charge=None)
    elif not slot["sensor_ok"] or slot.get("status") not in {
        "empty",
        "low",
        "ready",
        "full",
        "unknown",
    }:
        slot.update(status="unknown", charge=None)
    elif slot["status"] in {"low", "unknown"}:
        slot["charge"] = None
    elif slot["status"] == "empty":
        slot["charge"] = 0
    elif slot["status"] == "full":
        slot["charge"] = 100
    return slot


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
    healthy_slots = [
        slot
        for slot in slots
        if slot.enabled and slot.sensor_ok and slot.status not in {"unknown", "disabled"}
    ]
    if task_type == "return":
        return any(slot.status == "empty" for slot in healthy_slots)
    if task_type == "borrow":
        minimum_charge = required_charge or 0
        return any(
            slot.status in {"ready", "full"}
            and (power_bank_id is None or slot.bank_id == power_bank_id)
            and (
                (slot.charge is None and (minimum_charge == 0 or slot.status == "full"))
                or (slot.charge is not None and slot.charge >= minimum_charge)
            )
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
    result = dict(zip(columns, row, strict=True))
    if "changed_slots" in result:
        raw_slots = result["changed_slots"]
        result["changed_slots"] = (
            [int(slot) for slot in str(raw_slots).split(",") if slot] if raw_slots else []
        )
    return result


def _fetch_one(cursor) -> dict[str, Any] | None:
    return _row_as_dict(cursor, cursor.fetchone())


def _fetch_all(cursor) -> list[dict[str, Any]]:
    return [_row_as_dict(cursor, row) for row in cursor.fetchall()]


def list_locations() -> list[dict[str, Any]]:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {LOCATION_COLUMNS} FROM locations WHERE enabled = 1 ORDER BY code")
        return _fetch_all(cursor)


def get_location(location_code: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {LOCATION_COLUMNS} FROM locations WHERE code = :code AND enabled = 1",
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
        cursor.execute(
            "SELECT 1 FROM locations WHERE code = :code AND enabled = 1",
            code=location_code,
        )
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


def get_robot_order(robot_id: str, task_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = :id AND robot_id = :robot_id",
            id=task_id,
            robot_id=robot_id,
        )
        return _fetch_one(cursor)


def cancel_order(task_id: str) -> bool:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'cancelled', completed_at = SYSTIMESTAMP,
                updated_at = SYSTIMESTAMP
            WHERE id = :id AND status = 'pending'
            """,
            id=task_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed


def force_cancel_order(task_id: str, reason: str | None = None) -> str | None:
    """Cancel immediately when safe, otherwise request an active robot to stop first."""
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, robot_id
            FROM tasks
            WHERE id = :id
            FOR UPDATE
            """,
            id=task_id,
        )
        task = cursor.fetchone()
        if task is None:
            return None
        task_status, robot_id = task
        if task_status == "pending":
            cursor.execute(
                """
                UPDATE tasks
                SET status = 'cancelled', result_note = :reason,
                    cancel_requested_at = SYSTIMESTAMP, cancel_reason = :reason,
                    completed_at = SYSTIMESTAMP, updated_at = SYSTIMESTAMP
                WHERE id = :id AND status = 'pending'
                """,
                id=task_id,
                reason=reason,
            )
            connection.commit()
            return "cancelled" if cursor.rowcount == 1 else None
        if task_status != "in_progress":
            connection.rollback()
            return None

        cursor.execute(
            """
            UPDATE tasks
            SET cancel_requested_at = COALESCE(cancel_requested_at, SYSTIMESTAMP),
                cancel_reason = :reason, updated_at = SYSTIMESTAMP
            WHERE id = :id AND status = 'in_progress'
            """,
            id=task_id,
            reason=reason,
        )
        connection.commit()
        return "cancellation_requested" if cursor.rowcount == 1 else None


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
            SELECT id, progress_state
            FROM tasks
            WHERE robot_id = :robot_id AND status = 'in_progress'
            ORDER BY
                CASE
                    WHEN progress_state IN (
                        'precheck', 'navigating', 'arrived', 'waiting_action',
                        'wrong_slot', 'verifying_action', 'result_pending',
                        'recovery_required'
                    ) THEN 0
                    ELSE 1
                END,
                assigned_at ASC
            """,
            robot_id=robot_id,
        )
        claimed_task_rows = cursor.fetchall()
        robot["claimed_task_ids"] = [row[0] for row in claimed_task_rows]
        robot["current_task_id"] = next(
            (row[0] for row in claimed_task_rows if row[1] in EXECUTING_PROGRESS_STATES),
            None,
        )

        cursor.execute(
            """
            SELECT slot_number AS slot, bank_id, status, enabled,
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
                    "enabled": True,
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
            slot["enabled"] = bool(slot.get("enabled", True))
            slot["sensor_ok"] = bool(slot["sensor_ok"])
        robot["slots"] = [normalize_slot(slot) for slot in robot["slots"]]
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
        for index, raw_slot in enumerate(payload.slots[:3], start=1):
            slot = normalize_slot(raw_slot)
            slot_number = int(slot.get("slot", index))
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
                    enabled = :enabled,
                    sensor_ok = :sensor_ok,
                    current_amps = :current_amps,
                    voltage_volts = :voltage_volts,
                    charge = :charge,
                    updated_at = :updated_at
                WHEN NOT MATCHED THEN INSERT (
                    robot_id, slot_number, bank_id, status,
                    enabled, sensor_ok, current_amps, voltage_volts, charge, updated_at
                ) VALUES (
                    :robot_id, :slot_number, :bank_id, :status,
                    :enabled, :sensor_ok, :current_amps, :voltage_volts, :charge, :updated_at
                )
                """,
                robot_id=robot_id,
                slot_number=slot_number,
                bank_id=str(bank_id) if bank_id is not None else None,
                status=str(slot.get("status", "unknown")),
                enabled=(1 if slot.get("enabled", slot.get("status") != "disabled") else 0),
                current_amps=slot.get("current"),
                voltage_volts=slot.get("voltage"),
                charge=slot.get("charge"),
                sensor_ok=1 if slot.get("sensor_ok", True) else 0,
                updated_at=now,
            )
        connection.commit()


def claim_task(robot_id: str, payload: TaskClaim) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        for _ in range(3):
            # Serialize claims for one robot across API workers. A heartbeat creates the row.
            cursor.execute("SELECT id FROM robots WHERE id = :id FOR UPDATE", id=robot_id)
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                "SELECT COUNT(*) FROM tasks WHERE robot_id = :robot_id AND status = 'in_progress'",
                robot_id=robot_id,
            )
            if cursor.fetchone()[0] >= MAX_CLAIMED_TASKS:
                return None
            cursor.execute(
                """
                SELECT t.id, t.task_type, t.power_bank_id, t.required_charge, t.quantity
                FROM tasks t
                JOIN locations l ON l.code = t.location_code
                WHERE t.status = 'pending' AND l.enabled = 1
                ORDER BY t.created_at
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
                    assigned_at = SYSTIMESTAMP, updated_at = SYSTIMESTAMP,
                    cancel_requested_at = NULL, cancel_reason = NULL,
                    progress_state = 'queued_on_robot', warning = 0
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
        cursor.execute("SELECT 1 FROM robot_events WHERE id = :id", id=str(payload.event_id))
        if cursor.fetchone() is not None:
            return True
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
        if not changed and payload.status == "cancelled":
            cursor.execute(
                """
                SELECT 1 FROM tasks
                WHERE id = :id AND robot_id = :robot_id AND status = 'cancelled'
                """,
                id=task_id,
                robot_id=robot_id,
            )
            changed = cursor.fetchone() is not None
        if changed:
            cursor.execute(
                """
                INSERT INTO robot_events(id, robot_id, task_id, event_type, payload)
                VALUES (:id, :robot_id, :task_id, 'task_result', :payload)
                """,
                id=str(payload.event_id),
                robot_id=robot_id,
                task_id=task_id,
                payload=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
            )
        connection.commit()
        return changed


def release_task(robot_id: str, task_id: str, payload: TaskRelease) -> bool:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM robot_events WHERE id = :id", id=str(payload.event_id))
        if cursor.fetchone() is not None:
            return True
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'pending', robot_id = NULL, assigned_at = NULL,
                completed_at = NULL, result_note = :result_note,
                cancel_requested_at = NULL, cancel_reason = NULL,
                updated_at = SYSTIMESTAMP,
                progress_state = NULL, progress_message = NULL, warning = 0,
                expected_slot = NULL, changed_slot = NULL, changed_slots = NULL,
                action_deadline = NULL, progress_event_id = NULL,
                progress_updated_at = NULL
            WHERE id = :id AND robot_id = :robot_id AND status = 'in_progress'
              AND cancel_requested_at IS NULL
            """,
            result_note=payload.note,
            id=task_id,
            robot_id=robot_id,
        )
        changed = cursor.rowcount == 1
        if changed:
            cursor.execute(
                """
                INSERT INTO robot_events(id, robot_id, task_id, event_type, payload)
                VALUES (:id, :robot_id, :task_id, 'task_released', :payload)
                """,
                id=str(payload.event_id),
                robot_id=robot_id,
                task_id=task_id,
                payload=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
            )
        connection.commit()
        return changed


def record_task_progress(robot_id: str, task_id: str, payload: TaskProgress) -> bool:
    if str(payload.task_id) != task_id:
        return False
    with get_connection() as connection, connection.cursor() as cursor:
        if payload.progress_state in EXECUTING_PROGRESS_STATES:
            cursor.execute("SELECT id FROM robots WHERE id = :id FOR UPDATE", id=robot_id)
            if cursor.fetchone() is None:
                return False
            cursor.execute(
                "SELECT id, progress_state FROM tasks WHERE robot_id = :robot_id "
                "AND status = 'in_progress' AND id != :id",
                robot_id=robot_id,
                id=task_id,
            )
            if any(row[1] in EXECUTING_PROGRESS_STATES for row in cursor.fetchall()):
                return False
        cursor.execute(
            """
            UPDATE tasks
            SET progress_state = :progress_state,
                warning = :warning,
                progress_message = :progress_message,
                expected_slot = :expected_slot,
                changed_slot = :changed_slot,
                changed_slots = :changed_slots,
                action_deadline = :action_deadline,
                progress_event_id = :progress_event_id,
                progress_updated_at = SYSTIMESTAMP,
                updated_at = SYSTIMESTAMP
            WHERE id = :id AND robot_id = :robot_id AND status = 'in_progress'
            """,
            progress_state=payload.progress_state,
            warning=1 if payload.warning else 0,
            progress_message=payload.progress_message,
            expected_slot=payload.expected_slot,
            changed_slot=payload.changed_slot,
            changed_slots=",".join(str(slot) for slot in payload.changed_slots) or None,
            action_deadline=payload.action_deadline,
            progress_event_id=str(payload.event_id),
            id=task_id,
            robot_id=robot_id,
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed

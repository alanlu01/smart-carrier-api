from datetime import UTC, datetime
from typing import Any, Literal, overload
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TaskStatus = Literal["pending", "in_progress", "done", "cancelled", "failed"]
TaskType = Literal["borrow", "return", "delivery", "navigation", "callbot"]


@overload
def ensure_utc(value: datetime) -> datetime: ...


@overload
def ensure_utc(value: None) -> None: ...


def ensure_utc(value: datetime | None) -> datetime | None:
    """Treat timezone-less Oracle timestamps as UTC and normalize aware values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    environment: str
    database_backend: Literal["oracle"] = "oracle"
    database_configured: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


class Location(BaseModel):
    code: str
    name: str
    description: str | None = None
    floor: str | None = None
    x: float | None = None
    y: float | None = None
    yaw: float | None = None


class TaskCreate(BaseModel):
    location_code: str = Field(min_length=1, max_length=32)
    task_type: TaskType = "borrow"
    note: str | None = Field(default=None, max_length=500)
    power_bank_id: str | None = Field(default=None, min_length=1, max_length=64)
    required_charge: int | None = Field(default=None, ge=0, le=100)
    quantity: int = Field(default=1, ge=1, le=1)

    @field_validator("power_bank_id")
    @classmethod
    def normalize_power_bank_id(cls, power_bank_id: str | None) -> str | None:
        if power_bank_id is None:
            return None
        normalized = power_bank_id.strip().upper()
        if not normalized:
            raise ValueError("power_bank_id must not be blank")
        return normalized


class Task(BaseModel):
    id: UUID
    location_code: str
    task_type: TaskType
    status: TaskStatus
    note: str | None = None
    result_note: str | None = None
    power_bank_id: str | None = None
    required_charge: int | None = None
    quantity: int = 1
    robot_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    assigned_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    cancel_reason: str | None = None
    warning: bool = False
    progress_state: str | None = None
    progress_message: str | None = None
    expected_slot: int | None = None
    changed_slot: int | None = None
    changed_slots: list[int] = Field(default_factory=list)
    action_deadline: datetime | None = None
    progress_event_id: UUID | None = None
    progress_updated_at: datetime | None = None
    claim_request_id: UUID | None = None

    @field_validator(
        "created_at",
        "updated_at",
        "assigned_at",
        "completed_at",
        "cancel_requested_at",
        "action_deadline",
        "progress_updated_at",
    )
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class ClaimedTask(Task):
    location: Location | None = None


class TaskClaimSlot(BaseModel):
    slot: int = Field(ge=1, le=3)
    bank_id: str | None = Field(default=None, max_length=64)
    status: Literal["empty", "low", "ready", "full", "unknown", "disabled"]
    charge: int | None = Field(default=None, ge=0, le=100)
    sensor_ok: bool = True
    enabled: bool = True

    @field_validator("bank_id")
    @classmethod
    def normalize_bank_id(cls, bank_id: str | None) -> str | None:
        if bank_id is None:
            return None
        normalized = bank_id.strip().upper()
        if not normalized:
            raise ValueError("bank_id must not be blank")
        return normalized


class TaskClaim(BaseModel):
    slots: list[TaskClaimSlot] = Field(min_length=3, max_length=3)
    claim_request_id: UUID | None = None

    @field_validator("slots")
    @classmethod
    def require_all_three_slots(cls, slots: list[TaskClaimSlot]) -> list[TaskClaimSlot]:
        if {slot.slot for slot in slots} != {1, 2, 3}:
            raise ValueError("slots must contain slot numbers 1, 2, and 3 exactly once")
        return slots


class TaskRelease(BaseModel):
    event_id: UUID
    note: str | None = Field(default=None, max_length=500)


class TaskResult(BaseModel):
    event_id: UUID
    status: Literal["done", "failed", "cancelled"]
    note: str | None = Field(default=None, max_length=500)


class ForceCancelRequest(BaseModel):
    reason: str | None = Field(default="Cancelled by administrator", max_length=500)


class ForceCancelResponse(BaseModel):
    ok: bool = True
    outcome: Literal["cancelled", "cancellation_requested"]


class ForceFinalizeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    operator_confirmed_stopped: Literal[True]


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TaskProgress(BaseModel):
    event_id: UUID
    task_id: UUID
    progress_state: str = Field(min_length=1, max_length=32)
    progress_message: str | None = Field(default=None, max_length=500)
    expected_slot: int | None = Field(default=None, ge=1, le=3)
    changed_slot: int | None = Field(default=None, ge=1, le=3)
    changed_slots: list[int] = Field(default_factory=list, max_length=3)
    action_deadline: datetime | None = None
    warning: bool = False

    @field_validator("changed_slots")
    @classmethod
    def validate_changed_slots(cls, slots: list[int]) -> list[int]:
        normalized = sorted(set(slots))
        if any(slot < 1 or slot > 3 for slot in normalized):
            raise ValueError("changed_slots values must be between 1 and 3")
        return normalized


class Heartbeat(BaseModel):
    mode: str = Field(default="idle", max_length=32)
    battery: float | None = Field(default=None, ge=0, le=100)
    location_code: str | None = Field(default=None, max_length=32)
    x: float | None = None
    y: float | None = None
    yaw: float | None = None
    slots: list[dict[str, Any]] = Field(default_factory=list)


class RobotSlotStatus(BaseModel):
    slot: int = Field(ge=1, le=3)
    bank_id: str | None = None
    status: Literal["empty", "low", "ready", "full", "unknown", "disabled"]
    enabled: bool = True
    voltage: float | None = None
    current: float | None = None
    charge: int | None = Field(default=None, ge=0, le=100)
    sensor_ok: bool
    updated_at: datetime | None = None

    @field_validator("updated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class RobotStatus(BaseModel):
    id: str
    online: bool
    mode: str
    battery: float | None = Field(default=None, ge=0, le=100)
    location_code: str | None = None
    x: float | None = None
    y: float | None = None
    yaw: float | None = None
    last_seen_at: datetime
    current_task_id: UUID | None = None
    claimed_task_ids: list[UUID] = Field(default_factory=list)
    slots: list[RobotSlotStatus]

    @field_validator("last_seen_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class MessageResponse(BaseModel):
    ok: bool = True

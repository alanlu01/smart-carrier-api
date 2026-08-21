from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TaskStatus = Literal["pending", "in_progress", "done", "cancelled", "failed"]
TaskType = Literal["borrow", "return", "delivery", "navigation", "callbot"]


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
    required_charge: int | None = Field(default=None, ge=0, le=100)
    quantity: int = Field(default=1, ge=1, le=3)


class Task(BaseModel):
    id: UUID
    location_code: str
    task_type: TaskType
    status: TaskStatus
    note: str | None = None
    result_note: str | None = None
    required_charge: int | None = None
    quantity: int = 1
    robot_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    assigned_at: datetime | None = None
    completed_at: datetime | None = None


class ClaimedTask(Task):
    location: Location | None = None


class TaskClaimSlot(BaseModel):
    slot: int = Field(ge=1, le=3)
    status: Literal["empty", "low", "ready", "full", "unknown"]
    charge: int | None = Field(default=None, ge=0, le=100)
    sensor_ok: bool = True


class TaskClaim(BaseModel):
    slots: list[TaskClaimSlot] = Field(min_length=3, max_length=3)

    @field_validator("slots")
    @classmethod
    def require_all_three_slots(cls, slots: list[TaskClaimSlot]) -> list[TaskClaimSlot]:
        if {slot.slot for slot in slots} != {1, 2, 3}:
            raise ValueError("slots must contain slot numbers 1, 2, and 3 exactly once")
        return slots


class TaskRelease(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class TaskResult(BaseModel):
    status: Literal["done", "failed"]
    note: str | None = Field(default=None, max_length=500)


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
    status: Literal["empty", "low", "ready", "full", "unknown"]
    voltage: float | None = None
    current: float | None = None
    charge: int | None = Field(default=None, ge=0, le=100)
    sensor_ok: bool
    updated_at: datetime | None = None


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
    slots: list[RobotSlotStatus]


class MessageResponse(BaseModel):
    ok: bool = True

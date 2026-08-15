from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

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


class MessageResponse(BaseModel):
    ok: bool = True

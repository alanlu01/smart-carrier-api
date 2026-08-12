from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.database import get_supabase
from app.schemas import ClaimedTask, Heartbeat, MessageResponse, TaskResult
from app.security import require_robot_token

router = APIRouter(
    prefix="/api/v1/robots",
    tags=["robot"],
    dependencies=[Depends(require_robot_token)],
)


@router.post("/{robot_id}/heartbeat", response_model=MessageResponse)
def heartbeat(robot_id: str, payload: Heartbeat):
    now = datetime.now(UTC).isoformat()
    robot = {
        "id": robot_id,
        "mode": payload.mode,
        "battery": payload.battery,
        "location_code": payload.location_code,
        "x": payload.x,
        "y": payload.y,
        "yaw": payload.yaw,
        "last_seen_at": now,
    }
    client = get_supabase()
    client.table("robots").upsert(robot).execute()
    for index, slot in enumerate(payload.slots, start=1):
        client.table("power_slots").upsert(
            {"robot_id": robot_id, "slot_number": index, **slot, "updated_at": now},
            on_conflict="robot_id,slot_number",
        ).execute()
    return MessageResponse()


@router.post("/{robot_id}/tasks/claim", response_model=ClaimedTask | None)
def claim_task(robot_id: str, response: Response):
    client = get_supabase()
    result = client.rpc("claim_next_task", {"_robot_id": robot_id}).execute()
    if not result.data:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    task = result.data[0] if isinstance(result.data, list) else result.data
    location_result = (
        client.table("locations")
        .select("*")
        .eq("code", task["location_code"])
        .maybe_single()
        .execute()
    )
    task["location"] = location_result.data if location_result else None
    return task


@router.post("/{robot_id}/tasks/{task_id}/result", response_model=MessageResponse)
def complete_task(robot_id: str, task_id: str, payload: TaskResult):
    result = (
        get_supabase()
        .table("tasks")
        .update(
            {
                "status": payload.status,
                "note": payload.note,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", task_id)
        .eq("robot_id", robot_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Assigned task not found")
    return MessageResponse()

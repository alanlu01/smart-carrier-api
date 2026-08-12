from fastapi import APIRouter, HTTPException, Query, status

from app.database import get_supabase
from app.schemas import Location, MessageResponse, Task, TaskCreate

router = APIRouter(prefix="/api/v1", tags=["public"])


@router.get("/locations", response_model=list[Location])
def list_locations():
    response = get_supabase().table("locations").select("*").order("code").execute()
    return response.data


@router.post("/orders", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_order(payload: TaskCreate):
    note_parts = [f"[{payload.task_type}]", payload.note or ""]
    if payload.required_charge is not None:
        note_parts.append(f"required_charge={payload.required_charge}")
    if payload.quantity != 1:
        note_parts.append(f"quantity={payload.quantity}")
    response = (
        get_supabase()
        .table("tasks")
        .insert(
            {
                "location_code": payload.location_code.upper(),
                "note": " ".join(note_parts).strip(),
            }
        )
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=500, detail="Task was not created")
    return response.data[0]


@router.get("/orders", response_model=list[Task])
def list_orders(limit: int = Query(default=100, ge=1, le=500)):
    response = (
        get_supabase()
        .table("tasks")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


@router.get("/orders/{task_id}", response_model=Task)
def get_order(task_id: str):
    response = get_supabase().table("tasks").select("*").eq("id", task_id).maybe_single().execute()
    if not response:
        raise HTTPException(status_code=404, detail="Task not found")
    return response.data


@router.post("/orders/{task_id}/cancel", response_model=MessageResponse)
def cancel_order(task_id: str):
    response = (
        get_supabase()
        .table("tasks")
        .update({"status": "cancelled"})
        .eq("id", task_id)
        .in_("status", ["pending", "in_progress"])
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=409, detail="Task cannot be cancelled")
    return MessageResponse()

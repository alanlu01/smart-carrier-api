from fastapi import APIRouter, HTTPException, Query, status

from app import repository
from app.schemas import Location, MessageResponse, Task, TaskCreate

router = APIRouter(prefix="/api/v1", tags=["public"])


@router.get("/locations", response_model=list[Location])
def list_locations():
    return repository.list_locations()


@router.post("/orders", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_order(payload: TaskCreate):
    task = repository.create_order(payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return task


@router.get("/orders", response_model=list[Task])
def list_orders(limit: int = Query(default=100, ge=1, le=500)):
    return repository.list_orders(limit)


@router.get("/orders/{task_id}", response_model=Task)
def get_order(task_id: str):
    task = repository.get_order(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/orders/{task_id}/cancel", response_model=MessageResponse)
def cancel_order(task_id: str):
    if not repository.cancel_order(task_id):
        raise HTTPException(status_code=409, detail="Task cannot be cancelled")
    return MessageResponse()

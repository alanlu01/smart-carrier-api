from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import repository
from app.schemas import (
    ClaimedTask,
    Heartbeat,
    MessageResponse,
    Task,
    TaskClaim,
    TaskProgress,
    TaskRelease,
    TaskResult,
)
from app.security import require_robot_token

router = APIRouter(
    prefix="/api/v1/robots",
    tags=["robot"],
    dependencies=[Depends(require_robot_token)],
)


@router.post("/{robot_id}/heartbeat", response_model=MessageResponse)
def heartbeat(robot_id: str, payload: Heartbeat):
    repository.record_heartbeat(robot_id, payload)
    return MessageResponse()


@router.post("/{robot_id}/tasks/claim", response_model=ClaimedTask | None)
def claim_task(robot_id: str, payload: TaskClaim, response: Response):
    task = repository.claim_task(robot_id, payload)
    if task is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return task


@router.get("/{robot_id}/tasks/{task_id}", response_model=Task)
def get_assigned_task(robot_id: str, task_id: str):
    task = repository.get_robot_order(robot_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Assigned task not found")
    return task


@router.post("/{robot_id}/tasks/{task_id}/release", response_model=MessageResponse)
def release_task(robot_id: str, task_id: str, payload: TaskRelease):
    if not repository.release_task(robot_id, task_id, payload):
        raise HTTPException(status_code=409, detail="Assigned task cannot be released")
    return MessageResponse()


@router.post("/{robot_id}/tasks/{task_id}/result", response_model=MessageResponse)
def complete_task(robot_id: str, task_id: str, payload: TaskResult):
    if not repository.complete_task(robot_id, task_id, payload):
        raise HTTPException(status_code=404, detail="Assigned task not found")
    return MessageResponse()


@router.post("/{robot_id}/tasks/{task_id}/progress", response_model=MessageResponse)
def task_progress(robot_id: str, task_id: str, payload: TaskProgress):
    if not repository.record_task_progress(robot_id, task_id, payload):
        raise HTTPException(status_code=404, detail="Assigned task not found")
    return MessageResponse()

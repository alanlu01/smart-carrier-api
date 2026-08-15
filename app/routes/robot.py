from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import repository
from app.schemas import ClaimedTask, Heartbeat, MessageResponse, TaskResult
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
def claim_task(robot_id: str, response: Response):
    task = repository.claim_task(robot_id)
    if task is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return task


@router.post("/{robot_id}/tasks/{task_id}/result", response_model=MessageResponse)
def complete_task(robot_id: str, task_id: str, payload: TaskResult):
    if not repository.complete_task(robot_id, task_id, payload):
        raise HTTPException(status_code=404, detail="Assigned task not found")
    return MessageResponse()

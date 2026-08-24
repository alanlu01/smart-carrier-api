from fastapi import APIRouter, Depends, HTTPException, status

from app import repository
from app.schemas import ForceCancelRequest, ForceCancelResponse
from app.security import require_admin_token

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)


@router.post("/orders/{task_id}/force-cancel", response_model=ForceCancelResponse)
def force_cancel_order(task_id: str, payload: ForceCancelRequest):
    outcome = repository.force_cancel_order(task_id, payload.reason)
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or in-progress tasks can be cancelled",
        )
    return ForceCancelResponse(outcome=outcome)

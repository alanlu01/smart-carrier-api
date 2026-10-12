from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app import repository
from app.config import get_settings
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    ForceCancelRequest,
    ForceCancelResponse,
    ForceFinalizeRequest,
    Location,
    LocationCreate,
    LocationInput,
    MessageResponse,
    Task,
)
from app.security import (
    admin_login_key,
    admin_login_retry_after,
    clear_admin_login_failures,
    create_admin_session,
    record_admin_login_failure,
    require_admin_session,
    verify_admin_password,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post(
    "/locations",
    response_model=Location,
    status_code=201,
    dependencies=[Depends(require_admin_session)],
)
def create_location(payload: LocationCreate):
    try:
        return repository.create_location(payload)
    except repository.LocationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/locations/{code}", response_model=Location, dependencies=[Depends(require_admin_session)]
)
def edit_location(code: str, payload: LocationInput):
    try:
        location = repository.edit_location(code.upper(), payload)
    except (repository.LocationConflict, repository.LocationHasActiveTasks) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if location is None:
        raise HTTPException(status_code=404, detail="找不到地點。")
    return location


@router.delete(
    "/locations/{code}",
    response_model=MessageResponse,
    dependencies=[Depends(require_admin_session)],
)
def delete_location(code: str):
    try:
        deleted = repository.delete_location(code.upper())
    except (repository.LocationConflict, repository.LocationHasActiveTasks) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到地點。")
    return MessageResponse()


def _raise_rate_limited(retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/login", response_model=AdminLoginResponse)
def login(payload: AdminLoginRequest, request: Request, response: Response):
    settings = get_settings()
    password_hash = settings.admin_password_hash.get_secret_value()
    session_secret = settings.admin_session_secret.get_secret_value()
    if not password_hash or not session_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin login is not configured",
        )

    key = admin_login_key(request)
    retry_after = admin_login_retry_after(key)
    if retry_after:
        _raise_rate_limited(retry_after)
    if not verify_admin_password(payload.password, password_hash):
        retry_after = record_admin_login_failure(key)
        if retry_after:
            _raise_rate_limited(retry_after)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator password",
        )

    clear_admin_login_failures(key)
    response.headers["Cache-Control"] = "no-store"
    return AdminLoginResponse(
        access_token=create_admin_session(
            session_secret,
            settings.admin_session_ttl_seconds,
        ),
        expires_in=settings.admin_session_ttl_seconds,
    )


@router.get(
    "/orders",
    response_model=list[Task],
    dependencies=[Depends(require_admin_session)],
)
def list_orders(limit: int = Query(default=100, ge=1, le=500)):
    return repository.list_orders(limit)


@router.post(
    "/orders/{task_id}/force-cancel",
    response_model=ForceCancelResponse,
    dependencies=[Depends(require_admin_session)],
)
def force_cancel_order(task_id: str, payload: ForceCancelRequest):
    outcome = repository.force_cancel_order(task_id, payload.reason)
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or in-progress tasks can be cancelled",
        )
    return ForceCancelResponse(outcome=outcome)


@router.post(
    "/orders/{task_id}/force-finalize",
    response_model=ForceCancelResponse,
    dependencies=[Depends(require_admin_session)],
)
def force_finalize_order(task_id: str, payload: ForceFinalizeRequest):
    if not repository.force_finalize_order(task_id, payload.reason):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or in-progress tasks can be force-finalized",
        )
    return ForceCancelResponse(outcome="cancelled")

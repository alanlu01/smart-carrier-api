import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_robot_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().robot_api_token
    prefix = "Bearer "
    provided = (
        authorization[len(prefix) :] if authorization and authorization.startswith(prefix) else ""
    )
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid robot token")

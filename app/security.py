import base64
import binascii
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request, status

from app.config import get_settings


def require_robot_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().robot_api_token
    prefix = "Bearer "
    provided = (
        authorization[len(prefix) :] if authorization and authorization.startswith(prefix) else ""
    )
    if not provided or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid robot token")


ADMIN_LOGIN_FAILURE_THRESHOLD = 5
ADMIN_LOGIN_BASE_COOLDOWN_SECONDS = 30
ADMIN_LOGIN_MAX_COOLDOWN_SECONDS = 300
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1


@dataclass
class _LoginFailures:
    failures: int = 0
    blocked_until: float = 0.0


_login_failures: dict[str, _LoginFailures] = {}
_login_failures_lock = threading.Lock()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_admin_password(password: str, *, salt: bytes | None = None) -> str:
    password_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        (
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _base64url_encode(password_salt),
            _base64url_encode(digest),
        )
    )


def verify_admin_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = password_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_base64url_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_base64url_decode(expected)),
        )
        return hmac.compare_digest(actual, _base64url_decode(expected))
    except (ValueError, TypeError, binascii.Error):
        return False


def create_admin_session(secret: str, ttl_seconds: int, *, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = {
        "exp": issued_at + ttl_seconds,
        "iat": issued_at,
        "jti": secrets.token_urlsafe(12),
        "role": "admin",
    }
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256)
    return f"{encoded_payload}.{_base64url_encode(signature.digest())}"


def verify_admin_session(
    token: str, secret: str, *, now: int | None = None
) -> dict[str, Any] | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _base64url_decode(encoded_signature)):
            return None
        payload = json.loads(_base64url_decode(encoded_payload))
        current_time = int(time.time()) if now is None else now
        if payload.get("role") != "admin" or int(payload.get("exp", 0)) <= current_time:
            return None
        return payload
    except (
        AttributeError,
        ValueError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        return None


def admin_login_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def admin_login_retry_after(key: str, *, now: float | None = None) -> int:
    current_time = time.monotonic() if now is None else now
    with _login_failures_lock:
        record = _login_failures.get(key)
        if record is None or record.blocked_until <= current_time:
            return 0
        return max(1, math.ceil(record.blocked_until - current_time))


def record_admin_login_failure(key: str, *, now: float | None = None) -> int:
    current_time = time.monotonic() if now is None else now
    with _login_failures_lock:
        record = _login_failures.setdefault(key, _LoginFailures())
        record.failures += 1
        if record.failures < ADMIN_LOGIN_FAILURE_THRESHOLD:
            return 0
        cooldown = min(
            ADMIN_LOGIN_BASE_COOLDOWN_SECONDS
            * (2 ** (record.failures - ADMIN_LOGIN_FAILURE_THRESHOLD)),
            ADMIN_LOGIN_MAX_COOLDOWN_SECONDS,
        )
        record.blocked_until = current_time + cooldown
        return cooldown


def clear_admin_login_failures(key: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(key, None)


def clear_all_admin_login_failures() -> None:
    with _login_failures_lock:
        _login_failures.clear()


def require_admin_session(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    secret = settings.admin_session_secret.get_secret_value()
    prefix = "Bearer "
    token = (
        authorization[len(prefix) :] if authorization and authorization.startswith(prefix) else ""
    )
    if not secret or not token or verify_admin_session(token, secret) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin session",
        )

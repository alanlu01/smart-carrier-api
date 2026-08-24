from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import repository, security
from app.main import app
from app.routes import admin
from app.security import (
    clear_all_admin_login_failures,
    create_admin_session,
    hash_admin_password,
    verify_admin_password,
    verify_admin_session,
)

client = TestClient(app)


def admin_settings(password: str = "test-admin-password"):
    return SimpleNamespace(
        admin_password_hash=SecretStr(
            hash_admin_password(password, salt=b"0123456789abcdef")
        ),
        admin_session_secret=SecretStr("test-admin-session-secret-with-enough-entropy"),
        admin_session_ttl_seconds=1800,
    )


def test_admin_password_is_scrypt_hashed_and_verified():
    password_hash = hash_admin_password("test-admin-password", salt=b"0123456789abcdef")

    assert password_hash.startswith("scrypt$")
    assert "test-admin-password" not in password_hash
    assert verify_admin_password("test-admin-password", password_hash)
    assert not verify_admin_password("wrong", password_hash)


def test_admin_session_rejects_forgery_and_expiry():
    token = create_admin_session("secret", 60, now=1000)

    assert verify_admin_session(token, "secret", now=1059)["role"] == "admin"
    assert verify_admin_session(token, "wrong-secret", now=1059) is None
    assert verify_admin_session(token, "secret", now=1060) is None


def test_admin_login_succeeds_and_token_authorizes_order_list(monkeypatch):
    clear_all_admin_login_failures()
    monkeypatch.setattr(admin, "get_settings", admin_settings)
    monkeypatch.setattr(security, "get_settings", admin_settings)
    monkeypatch.setattr(repository, "list_orders", lambda _limit: [])

    login = client.post(
        "/api/v1/admin/login",
        json={"password": "test-admin-password"},
        headers={"X-Forwarded-For": "192.0.2.10"},
    )

    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    token = login.json()["access_token"]
    response = client.get(
        "/api/v1/admin/orders?limit=25",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_admin_login_starts_rate_limit_after_five_failures(monkeypatch):
    clear_all_admin_login_failures()
    monkeypatch.setattr(admin, "get_settings", admin_settings)
    headers = {"X-Forwarded-For": "192.0.2.20"}

    for _ in range(4):
        response = client.post(
            "/api/v1/admin/login",
            json={"password": "wrong"},
            headers=headers,
        )
        assert response.status_code == 401

    fifth = client.post(
        "/api/v1/admin/login",
        json={"password": "wrong"},
        headers=headers,
    )
    assert fifth.status_code == 429
    assert fifth.headers["retry-after"] == "30"

    blocked = client.post(
        "/api/v1/admin/login",
        json={"password": "test-admin-password"},
        headers=headers,
    )
    assert blocked.status_code == 429


def test_successful_login_clears_four_previous_failures(monkeypatch):
    clear_all_admin_login_failures()
    monkeypatch.setattr(admin, "get_settings", admin_settings)
    headers = {"X-Forwarded-For": "192.0.2.30"}
    for _ in range(4):
        assert (
            client.post(
                "/api/v1/admin/login",
                json={"password": "wrong"},
                headers=headers,
            ).status_code
            == 401
        )

    success = client.post(
        "/api/v1/admin/login",
        json={"password": "test-admin-password"},
        headers=headers,
    )
    assert success.status_code == 200

    next_failure = client.post(
        "/api/v1/admin/login",
        json={"password": "wrong"},
        headers=headers,
    )
    assert next_failure.status_code == 401


def test_public_order_list_is_not_available():
    response = client.get("/api/v1/orders?limit=25")
    assert response.status_code in {404, 405}


def test_admin_order_list_requires_session():
    response = client.get("/api/v1/admin/orders?limit=25")
    assert response.status_code == 401

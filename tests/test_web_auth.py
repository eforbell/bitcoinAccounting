"""Tests for private auth/session routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import create_app
from web.auth import session_cookie_secure, verify_auth_passphrase
from web.config import WebConfig


def test_login_sets_session_cookie_and_me_reads_it() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    login_response = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})

    assert login_response.status_code == 200
    assert login_response.json() == {"authenticated": True, "username": "operator"}
    assert "ba_session" in login_response.cookies

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json() == {"authenticated": True, "username": "operator"}


def test_login_rejects_wrong_passphrase() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.post("/api/auth/login", json={"passphrase": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_me_requires_auth_when_enabled() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_auth_disabled_allows_me_for_local_dev() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "operator"}


def test_logout_clears_cookie() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)
    client.post("/api/auth/login", json={"passphrase": "orange-hodl"})

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"authenticated": False, "username": "operator"}


def test_auth_uses_timing_safe_passphrase_compare() -> None:
    config = WebConfig(auth_enabled=True, auth_passphrase="orange-hodl")

    assert verify_auth_passphrase("orange-hodl", config) is True
    assert verify_auth_passphrase("wrong", config) is False


def test_session_cookie_defaults_to_secure_in_production() -> None:
    config = WebConfig(app_env="production")

    assert session_cookie_secure(config) is True


def test_login_marks_cookie_secure_in_production() -> None:
    app = create_app(
        WebConfig(
            app_env="production",
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            db_backend="postgres",
        )
    )
    client = TestClient(app)

    response = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]

"""Tests for FastAPI web app boot and health route."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_backend


class FakeBackend:
    """Minimal backend stub for health route testing."""

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [{"ok": 1}]

    def execute_one(self, query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return {"ok": 1}

    def execute_scalar(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return 1

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class BrokenBackend(FakeBackend):
    """Backend stub that fails readiness probes."""

    def execute_scalar(self, query: str, params: dict[str, Any] | None = None) -> Any:
        raise RuntimeError("database unavailable")


def test_create_app_serves_web_ui_shell() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text
    assert "Private Sovereignty Treasury" in response.text
    assert 'href="static/app.css"' in response.text
    assert 'src="static/app.js"' in response.text


def test_health_route_returns_ok_payload() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "bitcoin-accounting-api"
    assert body["environment"] == "development"
    assert "timestamp" in body


def test_ready_route_returns_backend_readiness_payload() -> None:
    app = create_app(config=WebConfig(db_backend="sqlite"))
    app.dependency_overrides[get_request_backend] = lambda: FakeBackend()
    client = TestClient(app)

    response = client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "bitcoin-accounting-api"
    assert body["environment"] == "development"
    assert body["database_backend"] == "sqlite"
    assert body["database_reachable"] is True
    assert body["production_policy"] == "postgres-primary"
    assert "timestamp" in body


def test_ready_route_returns_503_when_database_probe_fails() -> None:
    app = create_app(config=WebConfig(db_backend="postgres"))
    app.dependency_overrides[get_request_backend] = lambda: BrokenBackend()
    client = TestClient(app)

    response = client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database_reachable"] is False
    assert body["database_backend"] == "postgres"

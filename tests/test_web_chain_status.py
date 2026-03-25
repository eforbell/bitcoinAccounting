"""Tests for authenticated Bitcoin chain-status routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from web.app import create_app
from web.config import WebConfig, WebConfigurationError
from web.routes.chain import get_chain_status_service


class _StaticChainService:
    """Minimal fake chain-status service for route tests."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def get_status(self) -> dict[str, object]:
        return self._payload


def _authenticated_client(config: WebConfig | None = None) -> TestClient:
    app = create_app(
        config
        or WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200
    return client


def test_chain_status_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/chain/status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_chain_status_returns_disabled_payload_when_feature_is_off() -> None:
    client = _authenticated_client()

    response = client.get("/api/chain/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["available"] is False
    assert body["source"] == "bitcoind"
    assert body["warnings"] == ["Bitcoin node presence is disabled for this deployment."]


def test_chain_status_returns_live_payload_when_service_reports_healthy() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            chain_status_enabled=True,
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_cookie_file="/tmp/fake.cookie",
        )
    )
    app.dependency_overrides[get_chain_status_service] = lambda: _StaticChainService(
        {
            "enabled": True,
            "available": True,
            "source": "bitcoind",
            "network": "main",
            "block_height": 942151,
            "header_height": 942151,
            "verification_progress": 1.0,
            "is_synced": True,
            "last_block_at": datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
            "seconds_since_last_block": 302,
            "peer_count": 11,
            "mempool_tx_count": 10815,
            "mempool_usage_bytes": 64487424,
            "pruned": False,
            "warnings": [],
            "refreshed_at": datetime(2026, 3, 25, 12, 5, tzinfo=timezone.utc),
        }
    )
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200

    response = client.get("/api/chain/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["available"] is True
    assert body["block_height"] == 942151
    assert body["peer_count"] == 11
    assert body["mempool_tx_count"] == 10815
    assert body["is_synced"] is True
    assert body["warnings"] == []


def test_chain_status_returns_syncing_payload() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            chain_status_enabled=True,
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_cookie_file="/tmp/fake.cookie",
        )
    )
    app.dependency_overrides[get_chain_status_service] = lambda: _StaticChainService(
        {
            "enabled": True,
            "available": True,
            "source": "bitcoind",
            "network": "main",
            "block_height": 942100,
            "header_height": 942151,
            "verification_progress": 0.9982,
            "is_synced": False,
            "last_block_at": datetime(2026, 3, 25, 11, 50, tzinfo=timezone.utc),
            "seconds_since_last_block": 900,
            "peer_count": 8,
            "mempool_tx_count": 9500,
            "mempool_usage_bytes": 50331648,
            "pruned": False,
            "warnings": ["Node is still syncing and may not reflect the current tip yet."],
            "refreshed_at": datetime(2026, 3, 25, 12, 5, tzinfo=timezone.utc),
        }
    )
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200

    response = client.get("/api/chain/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["is_synced"] is False
    assert body["verification_progress"] == pytest.approx(0.9982)
    assert body["warnings"] == ["Node is still syncing and may not reflect the current tip yet."]


def test_chain_status_returns_unavailable_payload() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            chain_status_enabled=True,
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_cookie_file="/tmp/fake.cookie",
        )
    )
    app.dependency_overrides[get_chain_status_service] = lambda: _StaticChainService(
        {
            "enabled": True,
            "available": False,
            "source": "bitcoind",
            "network": None,
            "block_height": None,
            "header_height": None,
            "verification_progress": None,
            "is_synced": None,
            "last_block_at": None,
            "seconds_since_last_block": None,
            "peer_count": None,
            "mempool_tx_count": None,
            "mempool_usage_bytes": None,
            "pruned": None,
            "warnings": ["Bitcoin RPC unavailable: connection refused"],
            "refreshed_at": datetime(2026, 3, 25, 12, 5, tzinfo=timezone.utc),
        }
    )
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200

    response = client.get("/api/chain/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["available"] is False
    assert body["warnings"] == ["Bitcoin RPC unavailable: connection refused"]


def test_create_app_rejects_enabled_chain_status_without_rpc_url() -> None:
    with pytest.raises(WebConfigurationError):
        create_app(
            WebConfig(
                chain_status_enabled=True,
                bitcoin_rpc_cookie_file="/tmp/fake.cookie",
            )
        )

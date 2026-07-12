"""Tests for the Reports/visualization API routes and service.

Covers the network-free charts (balance, custody), auth protection, error
handling for an empty ledger, and report-cache invalidation on ledger writes.
The orange plot and PDF are intentionally not exercised here because they fetch
BTC-USD prices over the network.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend
from web.services import reports as reports_service

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
def _isolate_cache() -> None:
    reports_service.clear_cache()
    yield
    reports_service.clear_cache()


@pytest.fixture
def seeded_accounts() -> BitcoinAccounts:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    acc = BitcoinAccounts(backend=backend)
    acc.wallet_query.add_wallet(
        wallet_id="Coldcard", wallet_type="hardware",
        custody="self-custodied", description="vault",
    )
    acc.execute_trade(trade_date=datetime(2023, 1, 10), buy=0.2,
                      sell=6000, exchange="Coldcard")
    acc.execute_trade(trade_date=datetime(2024, 3, 5), buy=0.1,
                      sell=6500, exchange="Coldcard")
    yield acc
    acc.close()


@pytest.fixture
def client(seeded_accounts: BitcoinAccounts) -> TestClient:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    app.dependency_overrides[get_request_accounts] = lambda: seeded_accounts
    app.dependency_overrides[get_request_backend] = lambda: seeded_accounts.backend
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"passphrase": "orange-hodl"}).status_code == 200
    return client


@pytest.mark.parametrize("chart", ["balance", "custody"])
def test_chart_png_renders(client: TestClient, chart: str) -> None:
    resp = client.get(f"/api/reports/chart/{chart}.png?range=all")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers.get("cache-control") == "private, max-age=120"
    assert resp.content[:8] == _PNG_MAGIC


def test_unknown_chart_is_404(client: TestClient) -> None:
    assert client.get("/api/reports/chart/bogus.png?range=all").status_code == 404


def test_bad_range_is_400(client: TestClient) -> None:
    assert client.get("/api/reports/chart/balance.png?range=decade").status_code == 400


def test_reports_require_authentication(seeded_accounts: BitcoinAccounts) -> None:
    app = create_app(
        WebConfig(auth_enabled=True, auth_passphrase="pw", session_secret="s")
    )
    app.dependency_overrides[get_request_backend] = lambda: seeded_accounts.backend
    anon = TestClient(app)
    assert anon.get("/api/reports/chart/balance.png?range=all").status_code in (401, 403)


def test_service_renders_png_bytes(seeded_accounts: BitcoinAccounts) -> None:
    png = reports_service.render_chart_png(
        seeded_accounts.backend, "balance", date_range="all"
    )
    assert png[:8] == _PNG_MAGIC


def test_service_empty_ledger_raises_report_error() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    try:
        with pytest.raises(reports_service.ReportError):
            reports_service.render_chart_png(backend, "balance", date_range="all")
    finally:
        backend.close()


def test_ledger_write_invalidates_report_cache(client: TestClient) -> None:
    # Seed a fake cached entry, then confirm a successful write clears it.
    reports_service._cache["png:balance:all"] = (time.monotonic() + 999, b"stale")
    resp = client.post(
        "/api/ledger/buy",
        json={
            "trade_date": "2024-06-15T10:30:00",
            "buy": 0.05,
            "sell": 3000.0,
            "exchange": "Coldcard",
            "comment": "cache-bust",
        },
    )
    assert resp.status_code == 200
    assert "png:balance:all" not in reports_service._cache

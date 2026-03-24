"""Tests for authenticated tax reporting API routes."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend


@pytest.fixture
def seeded_accounts() -> BitcoinAccounts:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    accounts = BitcoinAccounts(backend=backend)

    # Historical gains case
    accounts.execute_trade(
        trade_date=datetime(2024, 1, 1),
        buy=1.0,
        buy_curr="BTC",
        sell=50000.0,
        sell_curr="USD",
        exchange="Strike",
    )
    accounts.execute_trade(
        trade_date=datetime(2024, 12, 1),
        buy=60000.0,
        buy_curr="USD",
        sell=1.0,
        sell_curr="BTC",
        exchange="Strike",
    )

    # Wallet-scoped 2025 export case
    accounts.execute_trade(
        trade_date=datetime(2025, 1, 10),
        buy=0.5,
        buy_curr="BTC",
        sell=25000.0,
        sell_curr="USD",
        exchange="Coldcard",
    )
    accounts.execute_trade(
        trade_date=datetime(2025, 12, 15),
        buy=45000.0,
        buy_curr="USD",
        sell=0.5,
        sell_curr="BTC",
        exchange="Coldcard",
    )

    # Forecast case with mixed holding periods
    accounts.execute_trade(
        trade_date=datetime(2025, 12, 1),
        buy=0.25,
        buy_curr="BTC",
        sell=20000.0,
        sell_curr="USD",
        exchange="Vault",
    )

    yield accounts
    accounts.close()


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
    login_response = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login_response.status_code == 200
    return client


def test_tax_routes_require_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/tax/gains", params={"tax_year": 2024, "coin": "BTC"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_gains_endpoint_returns_summary_and_historical_warning(client: TestClient) -> None:
    response = client.get("/api/tax/gains", params={"tax_year": 2024, "coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "tax_year": 2024,
        "coin": "BTC",
        "wallet_id": None,
        "lot_count": 1,
        "proceeds_usd": 60000.0,
        "cost_basis_usd": 50000.0,
        "gain_loss_usd": 10000.0,
        "short_term_lot_count": 1,
        "long_term_lot_count": 0,
    }
    assert body["lots"][0]["description"] == "1.00000000 BTC"
    assert body["worksheet"][0]["gain_loss_usd"] == 10000.0
    assert body["warnings"][0]["code"] == "global_fifo_historical"
    assert body["warnings"][0]["reference_doc"] == "docs/IRS_2025_WALLET_RULES.md"


def test_tax_policy_endpoint_exposes_wallet_guidance(client: TestClient) -> None:
    response = client.get("/api/tax/policy")

    assert response.status_code == 200
    assert response.json() == {
        "wallet_separation_required_from_tax_year": 2025,
        "strict_wallet_enforcement_for_exports": True,
        "reference_doc": "docs/IRS_2025_WALLET_RULES.md",
        "summary": (
            "Wallet-separated FIFO is required for tax year 2025 and later. "
            "Historical global FIFO remains available only as a convenience view."
        ),
    }


def test_1099b_preview_requires_wallet_for_2025_and_later(client: TestClient) -> None:
    response = client.get("/api/tax/1099b/preview", params={"tax_year": 2025, "coin": "BTC"})

    assert response.status_code == 400
    assert "explicit wallet filter" in response.json()["detail"]


def test_1099b_export_returns_csv_for_wallet_scoped_request(client: TestClient) -> None:
    response = client.get(
        "/api/tax/1099b/export",
        params={"tax_year": 2025, "coin": "BTC", "wallet": "Coldcard"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="1099b_2025_Coldcard.csv"'
    assert "Description,Date Acquired,Date Sold,Proceeds,Cost Basis" in response.text
    assert "0.50000000 BTC,01/10/2025,12/15/2025,45000.00,25000.00" in response.text


def test_forecast_endpoint_returns_fifo_lots_and_balance(client: TestClient) -> None:
    response = client.get(
        "/api/tax/forecast",
        params={
            "coin": "BTC",
            "wallet": "Vault",
            "quantity": 0.2,
            "sale_price_usd": 100000.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == 0.25
    assert body["summary"]["wallet_id"] == "Vault"
    assert body["summary"]["total_proceeds_usd"] == 20000.0
    assert body["summary"]["short_term_quantity"] == 0.2
    assert len(body["lots"]) == 1
    assert body["lots"][0]["acquire_date"] == "2025-12-01"
    assert body["lots"][0]["term"] == "Short"


def test_presets_round_trip_through_web_state_store(client: TestClient) -> None:
    create_response = client.post(
        "/api/tax/presets",
        json={
            "name": "Coldcard 2025 Export",
            "preset_type": "1099b",
            "coin": "BTC",
            "tax_year": 2025,
            "wallet_id": "Coldcard",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Coldcard 2025 Export"
    assert created["preset_type"] == "1099b"
    assert created["wallet_id"] == "Coldcard"

    list_response = client.get("/api/tax/presets")

    assert list_response.status_code == 200
    presets = list_response.json()
    assert len(presets) == 1
    assert presets[0]["preset_id"] == created["preset_id"]

    delete_response = client.delete(f"/api/tax/presets/{created['preset_id']}")

    assert delete_response.status_code == 204
    assert client.get("/api/tax/presets").json() == []


def test_history_endpoint_lists_recent_tax_runs(client: TestClient) -> None:
    client.get("/api/tax/gains", params={"tax_year": 2024, "coin": "BTC"})
    client.get(
        "/api/tax/forecast",
        params={
            "coin": "BTC",
            "wallet": "Vault",
            "quantity": 0.2,
            "sale_price_usd": 100000.0,
        },
    )
    client.get(
        "/api/tax/1099b/export",
        params={"tax_year": 2025, "coin": "BTC", "wallet": "Coldcard"},
    )

    history_response = client.get("/api/tax/history", params={"limit": 5})

    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) >= 3
    actions = [entry["action"] for entry in history]
    assert "gains_report" in actions
    assert "forecast" in actions
    assert "export_1099b" in actions

"""Tests for authenticated portfolio/dashboard API routes."""

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

    accounts.wallet_query.add_wallet(
        wallet_id="Coldcard",
        wallet_type="hardware",
        custody="self-custodied",
        description="Primary vault",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="River",
        wallet_type="exchange",
        custody="custodial",
        description="Broker",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="Casa",
        wallet_type="multisig",
        custody="multisig",
        description="Collaborative vault",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="OldVault",
        wallet_type="hardware",
        custody="self-custodied",
        description="Inactive archive",
    )
    accounts.wallet_query.update_wallet("OldVault", active=False)

    accounts.execute_trade(
        trade_date=datetime(2024, 1, 1),
        buy=1.0,
        buy_curr="BTC",
        sell=50000.0,
        sell_curr="USD",
        exchange="Coldcard",
    )
    accounts.execute_trade(
        trade_date=datetime(2024, 3, 1),
        buy=0.5,
        buy_curr="BTC",
        sell=25000.0,
        sell_curr="USD",
        exchange="River",
    )
    accounts.execute_trade(
        trade_date=datetime(2024, 6, 1),
        buy=0.25,
        buy_curr="BTC",
        sell=15000.0,
        sell_curr="USD",
        exchange="Casa",
    )
    accounts.transfer_funds(
        withdraw_date=datetime(2024, 7, 1),
        deposit_date=datetime(2024, 7, 1),
        tx_amount=0.1,
        tx_coin="BTC",
        from_account="River",
        to_account="Coldcard",
        fee_amount=0.0001,
        fee_coin="BTC",
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
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200
    return client


def test_dashboard_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/portfolio/dashboard")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_dashboard_endpoint_returns_summary_wallets_and_recent_activity(client: TestClient) -> None:
    response = client.get("/api/portfolio/dashboard", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "coin": "BTC",
        "total_balance": pytest.approx(1.7499),
        "average_cost_basis_usd": pytest.approx(51428.57142857143),
        "wallet_count": 4,
        "active_wallet_count": 3,
    }
    assert body["wallets"][0]["wallet_id"] == "Coldcard"
    assert body["wallets"][0]["custody"] == "self-custodied"
    assert body["wallets"][0]["balance"] == pytest.approx(1.1)
    assert body["wallets"][1]["wallet_id"] == "River"
    assert body["wallets"][2]["wallet_id"] == "Casa"
    assert len(body["recent_transactions"]) == 5
    assert body["recent_transactions"][0]["transaction_type"] in {"Deposit", "Withdrawal"}
    assert body["custody_breakdown"][0]["custody"] == "self-custodied"
    assert body["using_inferred_custody"] is False


def test_dashboard_can_include_inactive_wallets(client: TestClient) -> None:
    response = client.get(
        "/api/portfolio/dashboard",
        params={"coin": "BTC", "include_inactive": "true"},
    )

    assert response.status_code == 200
    wallets = response.json()["wallets"]
    wallet_ids = [wallet["wallet_id"] for wallet in wallets]
    assert "OldVault" in wallet_ids


def test_dashboard_ui_shell_is_served_on_tax_path() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/tax")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

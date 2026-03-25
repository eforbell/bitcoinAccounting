"""Tests for authenticated trades and liquidity API routes."""

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
        wallet_id="River",
        wallet_type="exchange",
        custody="custodial",
        description="Broker",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="Strike",
        wallet_type="exchange",
        custody="custodial",
        description="Broker 2",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="Coldcard",
        wallet_type="hardware",
        custody="self-custodied",
        description="Vault",
    )

    # Buy 1.0 BTC at River for $50k
    accounts.execute_trade(
        trade_date=datetime(2024, 1, 15),
        buy=1.0,
        buy_curr="BTC",
        sell=50000.0,
        sell_curr="USD",
        exchange="River",
    )
    # Buy 0.5 BTC at Strike for $25k
    accounts.execute_trade(
        trade_date=datetime(2024, 3, 1),
        buy=0.5,
        buy_curr="BTC",
        sell=25000.0,
        sell_curr="USD",
        exchange="Strike",
    )
    # Sell 0.25 BTC at River for $15k
    accounts.execute_trade(
        trade_date=datetime(2024, 6, 1),
        buy=15000.0,
        buy_curr="USD",
        sell=0.25,
        sell_curr="BTC",
        exchange="River",
    )
    # Transfer 0.5 BTC from River to Coldcard
    accounts.transfer_funds(
        withdraw_date=datetime(2024, 7, 1),
        deposit_date=datetime(2024, 7, 1),
        tx_amount=0.5,
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


# --- Auth ---


def test_trades_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)
    assert client.get("/api/trades").status_code == 401
    assert client.get("/api/trades/liquidity").status_code == 401


# --- Trades endpoint ---


def test_trades_returns_paginated_trades(client: TestClient) -> None:
    response = client.get("/api/trades")
    assert response.status_code == 200

    body = response.json()
    assert body["page"] == 1
    assert body["per_page"] == 50
    assert body["total"] == 3  # 2 buys + 1 sell (transfers not included)
    assert len(body["trades"]) == 3

    # Newest first
    first = body["trades"][0]
    assert first["date"] == "2024-06-01"
    assert first["trade_type"] == "Sell"

    second = body["trades"][1]
    assert second["date"] == "2024-03-01"
    assert second["trade_type"] == "Buy"
    assert second["exchange"] == "Strike"


def test_trades_pagination(client: TestClient) -> None:
    response = client.get("/api/trades", params={"per_page": 2, "page": 1})
    body = response.json()
    assert len(body["trades"]) == 2
    assert body["total"] == 3

    response2 = client.get("/api/trades", params={"per_page": 2, "page": 2})
    body2 = response2.json()
    assert len(body2["trades"]) == 1


def test_trades_filter_by_exchange(client: TestClient) -> None:
    response = client.get("/api/trades", params={"exchange": "Strike"})
    body = response.json()
    assert body["total"] == 1
    assert body["trades"][0]["exchange"] == "Strike"
    assert body["trades"][0]["trade_type"] == "Buy"


def test_trades_filter_by_nonexistent_exchange(client: TestClient) -> None:
    response = client.get("/api/trades", params={"exchange": "Nonexistent"})
    body = response.json()
    assert body["total"] == 0
    assert body["trades"] == []


def test_trade_resource_fields(client: TestClient) -> None:
    response = client.get("/api/trades", params={"exchange": "River", "per_page": 1})
    body = response.json()
    trade = body["trades"][0]

    assert "date" in trade
    assert "trade_type" in trade
    assert "quantity" in trade
    assert trade["quantity"] > 0
    assert "trade_currency" in trade
    assert "unit_cost_usd" in trade
    assert "total_cost_usd" in trade
    assert "exchange" in trade


# --- Liquidity endpoint ---


def test_liquidity_returns_exchange_summary(client: TestClient) -> None:
    response = client.get("/api/trades/liquidity")
    assert response.status_code == 200

    body = response.json()
    exchanges = body["exchanges"]
    # River bought 1.0 BTC, Strike bought 0.5 BTC
    assert len(exchanges) == 2

    # Sorted by total_purchased descending
    assert exchanges[0]["exchange"] == "River"
    assert exchanges[0]["total_purchased"] == pytest.approx(1.0)
    assert exchanges[1]["exchange"] == "Strike"
    assert exchanges[1]["total_purchased"] == pytest.approx(0.5)


def test_liquidity_avg_cost(client: TestClient) -> None:
    response = client.get("/api/trades/liquidity")
    body = response.json()

    river = next(e for e in body["exchanges"] if e["exchange"] == "River")
    # Bought 1.0 BTC for $50k -> avg cost $50k
    assert river["avg_cost_usd"] == pytest.approx(50000.0)

    strike = next(e for e in body["exchanges"] if e["exchange"] == "Strike")
    # Bought 0.5 BTC for $25k -> avg cost $50k
    assert strike["avg_cost_usd"] == pytest.approx(50000.0)


def test_liquidity_summary(client: TestClient) -> None:
    response = client.get("/api/trades/liquidity")
    body = response.json()

    summary = body["summary"]
    assert summary["total_purchased"] == pytest.approx(1.5)
    assert summary["total_usd_spent"] == pytest.approx(75000.0)
    assert summary["avg_cost_basis_usd"] == pytest.approx(50000.0)
    assert summary["total_holdings"] == pytest.approx(
        summary["still_at_exchanges"] + summary["in_cold_storage"]
    )


def test_liquidity_current_balances(client: TestClient) -> None:
    response = client.get("/api/trades/liquidity")
    body = response.json()

    # River: bought 1.0, sold 0.25, transferred 0.5 out -> 0.25 remaining
    river = next(e for e in body["exchanges"] if e["exchange"] == "River")
    assert river["current_balance"] == pytest.approx(0.25, abs=0.001)

    # Strike: bought 0.5, no transfers -> 0.5 remaining
    strike = next(e for e in body["exchanges"] if e["exchange"] == "Strike")
    assert strike["current_balance"] == pytest.approx(0.5)

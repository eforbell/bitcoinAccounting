"""Tests for transaction entry (record) API routes."""

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
        wallet_id="Strike",
        wallet_type="exchange",
        custody="custodial",
        description="Broker",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="Coldcard",
        wallet_type="hardware",
        custody="self-custodied",
        description="Primary vault",
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


def test_record_buy(client: TestClient, seeded_accounts: BitcoinAccounts) -> None:
    response = client.post(
        "/api/ledger/buy",
        json={
            "trade_date": "2024-06-15T10:30:00",
            "buy": 0.5,
            "sell": 25000.0,
            "exchange": "Strike",
            "comment": "DCA buy",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "action": "buy"}

    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    assert len(rows) == 1
    assert float(rows[0]["Buy"]) == pytest.approx(0.5)
    assert rows[0]["Exchange"] == "Strike"


def test_record_sell(client: TestClient, seeded_accounts: BitcoinAccounts) -> None:
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 1, 1),
        buy=1.0, buy_curr="BTC", sell=50000.0, sell_curr="USD",
        exchange="Strike",
    )

    response = client.post(
        "/api/ledger/sell",
        json={
            "trade_date": "2024-12-01T14:00:00",
            "sell": 0.5,
            "buy": 30000.0,
            "exchange": "Strike",
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == "sell"

    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    # Sells are stored as "Trade" with sell_curr=BTC
    sells = [r for r in rows if r["Sell Cur."] == "BTC" and float(r["Sell"] or 0) > 0]
    assert len(sells) == 1
    assert float(sells[0]["Sell"]) == pytest.approx(0.5)


def test_record_transfer(client: TestClient, seeded_accounts: BitcoinAccounts) -> None:
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 1, 1),
        buy=1.0, buy_curr="BTC", sell=50000.0, sell_curr="USD",
        exchange="Strike",
    )

    response = client.post(
        "/api/ledger/transfer",
        json={
            "transfer_date": "2024-07-01T12:00:00",
            "amount": 0.25,
            "from_wallet": "Strike",
            "to_wallet": "Coldcard",
            "fee": 0.0001,
            "comment": "Move to cold storage",
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == "transfer"

    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    types = [r["Type"] for r in rows]
    assert "Withdrawal" in types
    assert "Deposit" in types


def test_record_interest(client: TestClient, seeded_accounts: BitcoinAccounts) -> None:
    response = client.post(
        "/api/ledger/interest",
        json={
            "interest_date": "2024-09-01T00:00:00",
            "amount": 0.001,
            "currency": "BTC",
            "exchange": "Strike",
            "comment": "Monthly rewards",
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == "interest"

    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    interest_rows = [r for r in rows if r["Type"] == "Interest Income"]
    assert len(interest_rows) == 1
    assert float(interest_rows[0]["Buy"]) == pytest.approx(0.001)


def test_record_buy_with_fee(client: TestClient, seeded_accounts: BitcoinAccounts) -> None:
    response = client.post(
        "/api/ledger/buy",
        json={
            "trade_date": "2024-06-15T10:30:00",
            "buy": 0.5,
            "sell": 25000.0,
            "exchange": "Strike",
            "fee": 10.0,
            "fee_curr": "USD",
        },
    )

    assert response.status_code == 200
    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    assert float(rows[0]["Fee"]) == pytest.approx(10.0)
    assert rows[0]["Fee Cur."] == "USD"


def test_record_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    assert client.post("/api/ledger/buy", json={"trade_date": "2024-01-01", "buy": 1, "sell": 50000, "exchange": "X"}).status_code == 401
    assert client.post("/api/ledger/sell", json={"trade_date": "2024-01-01", "buy": 50000, "sell": 1, "exchange": "X"}).status_code == 401
    assert client.post("/api/ledger/transfer", json={"transfer_date": "2024-01-01", "amount": 1, "from_wallet": "A", "to_wallet": "B"}).status_code == 401
    assert client.post("/api/ledger/interest", json={"interest_date": "2024-01-01", "amount": 0.001, "exchange": "X"}).status_code == 401


def test_record_validation_rejects_missing_fields(client: TestClient) -> None:
    response = client.post("/api/ledger/buy", json={"trade_date": "2024-01-01"})
    assert response.status_code == 422


def test_record_buy_malformed_date_returns_422(client: TestClient) -> None:
    """Malformed trade_date must return 422, not 500."""
    response = client.post(
        "/api/ledger/buy",
        json={
            "trade_date": "not-a-date",
            "buy": 0.5,
            "sell": 25000.0,
            "exchange": "Strike",
        },
    )
    assert response.status_code == 422
    assert "Invalid date format" in response.json()["detail"]


def test_record_sell_malformed_date_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/ledger/sell",
        json={
            "trade_date": "yesterday",
            "sell": 0.5,
            "buy": 30000.0,
            "exchange": "Strike",
        },
    )
    assert response.status_code == 422
    assert "Invalid date format" in response.json()["detail"]


def test_record_transfer_malformed_date_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/ledger/transfer",
        json={
            "transfer_date": "2024-13-99",
            "amount": 0.25,
            "from_wallet": "Strike",
            "to_wallet": "Coldcard",
        },
    )
    assert response.status_code == 422
    assert "Invalid date format" in response.json()["detail"]


def test_record_interest_malformed_date_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/ledger/interest",
        json={
            "interest_date": "abc",
            "amount": 0.001,
            "exchange": "Strike",
        },
    )
    assert response.status_code == 422
    assert "Invalid date format" in response.json()["detail"]


def test_record_ui_shell_is_served() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/record")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

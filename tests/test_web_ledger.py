"""Tests for authenticated ledger explorer API routes."""

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

    accounts.execute_trade(
        trade_date=datetime(2024, 1, 15),
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
        buy=30000.0,
        buy_curr="USD",
        sell=0.5,
        sell_curr="BTC",
        exchange="River",
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


def test_ledger_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/ledger")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_ledger_returns_all_transactions_with_summary(client: TestClient) -> None:
    response = client.get("/api/ledger", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["per_page"] == 50
    assert body["total"] >= 4
    assert len(body["transactions"]) == body["total"]

    summary = body["summary"]
    assert summary["count"] == body["total"]
    assert summary["credits"] > 0
    assert summary["balance"] == pytest.approx(
        summary["credits"] - summary["debits"] - summary["fees"]
    )


def test_ledger_wallet_filter(client: TestClient) -> None:
    response = client.get("/api/ledger", params={"coin": "BTC", "wallet": "River"})

    assert response.status_code == 200
    body = response.json()
    for tx in body["transactions"]:
        assert tx["wallet_id"] == "River"


def test_ledger_date_filter(client: TestClient) -> None:
    response = client.get(
        "/api/ledger",
        params={"coin": "BTC", "start_date": "2024-06-01", "end_date": "2024-06-30"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    for tx in body["transactions"]:
        assert "2024-06" in tx["created_at"] or "06/01/2024" in tx["created_at"]


def test_ledger_pagination(client: TestClient) -> None:
    response = client.get("/api/ledger", params={"coin": "BTC", "per_page": "2", "page": "1"})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["per_page"] == 2
    assert len(body["transactions"]) == 2
    assert body["total"] >= 4

    page2 = client.get("/api/ledger", params={"coin": "BTC", "per_page": "2", "page": "2"})
    body2 = page2.json()
    assert body2["page"] == 2
    assert len(body2["transactions"]) >= 1
    assert body2["transactions"][0]["transaction_id"] != body["transactions"][0]["transaction_id"]


def test_ledger_newest_first(client: TestClient) -> None:
    response = client.get("/api/ledger", params={"coin": "BTC"})

    body = response.json()
    dates = [tx["created_at"] for tx in body["transactions"]]
    assert dates == sorted(dates, reverse=True)


def test_ledger_include_deleted(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    tx_id = rows[0]["ID"]
    seeded_accounts.ledger_writer.soft_delete_transaction(tx_id)

    without = client.get("/api/ledger", params={"coin": "BTC"})
    with_deleted = client.get(
        "/api/ledger", params={"coin": "BTC", "include_deleted": "true"}
    )

    assert with_deleted.json()["total"] > without.json()["total"]
    deleted_tx_ids = [
        tx["transaction_id"]
        for tx in with_deleted.json()["transactions"]
        if tx["deleted"]
    ]
    assert tx_id in deleted_tx_ids


def test_ledger_summary_reflects_filters(client: TestClient) -> None:
    all_resp = client.get("/api/ledger", params={"coin": "BTC"})
    wallet_resp = client.get("/api/ledger", params={"coin": "BTC", "wallet": "Coldcard"})

    all_summary = all_resp.json()["summary"]
    wallet_summary = wallet_resp.json()["summary"]
    assert wallet_summary["count"] < all_summary["count"]


def _first_tx_id(client: TestClient) -> int:
    resp = client.get("/api/ledger", params={"coin": "BTC"})
    return resp.json()["transactions"][0]["transaction_id"]


def test_transaction_detail(client: TestClient) -> None:
    tx_id = _first_tx_id(client)
    response = client.get(f"/api/ledger/{tx_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"] == tx_id
    assert body["created_at"]
    assert body["wallet_id"]


def test_transaction_detail_not_found(client: TestClient) -> None:
    response = client.get("/api/ledger/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"


def test_transaction_edit(client: TestClient) -> None:
    tx_id = _first_tx_id(client)
    response = client.patch(
        f"/api/ledger/{tx_id}",
        json={"comment": "edited via API"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"] == tx_id
    assert body["comment"] == "edited via API"

    detail = client.get(f"/api/ledger/{tx_id}")
    assert detail.json()["comment"] == "edited via API"


def test_transaction_edit_numeric_fields(client: TestClient) -> None:
    tx_id = _first_tx_id(client)
    response = client.patch(
        f"/api/ledger/{tx_id}",
        json={"fee_amount": 0.0005, "fee_currency": "BTC"},
    )

    assert response.status_code == 200
    assert response.json()["fee_amount"] == pytest.approx(0.0005)
    assert response.json()["fee_currency"] == "BTC"


def test_transaction_edit_not_found(client: TestClient) -> None:
    response = client.patch("/api/ledger/999999", json={"comment": "nope"})

    assert response.status_code == 404


def test_transaction_soft_delete_and_restore(client: TestClient) -> None:
    tx_id = _first_tx_id(client)

    delete_resp = client.delete(f"/api/ledger/{tx_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    ledger_without = client.get("/api/ledger", params={"coin": "BTC"})
    deleted_ids = [tx["transaction_id"] for tx in ledger_without.json()["transactions"]]
    assert tx_id not in deleted_ids

    restore_resp = client.post(f"/api/ledger/{tx_id}/restore")
    assert restore_resp.status_code == 200
    assert restore_resp.json()["deleted"] is False

    ledger_with = client.get("/api/ledger", params={"coin": "BTC"})
    restored_ids = [tx["transaction_id"] for tx in ledger_with.json()["transactions"]]
    assert tx_id in restored_ids


def test_transaction_delete_not_found(client: TestClient) -> None:
    response = client.delete("/api/ledger/999999")
    assert response.status_code == 404


def test_transaction_restore_not_found(client: TestClient) -> None:
    response = client.post("/api/ledger/999999/restore")
    assert response.status_code == 404


def test_transaction_detail_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)
    assert client.get("/api/ledger/1").status_code == 401
    assert client.patch("/api/ledger/1", json={"comment": "x"}).status_code == 401
    assert client.delete("/api/ledger/1").status_code == 401
    assert client.post("/api/ledger/1/restore").status_code == 401


def test_transfer_pair_both_visible(client: TestClient) -> None:
    """Transfer pair transactions (Deposit + Withdrawal) should both appear."""
    ledger = client.get("/api/ledger", params={"coin": "BTC"})
    transfers = [
        tx for tx in ledger.json()["transactions"]
        if tx["transaction_type"] in ("Deposit", "Withdrawal")
    ]
    assert len(transfers) >= 2
    types = {tx["transaction_type"] for tx in transfers}
    assert "Deposit" in types
    assert "Withdrawal" in types


def test_ledger_summary_coin_matches_filter(client: TestClient) -> None:
    """Summary coin field must reflect the requested coin, not hardcode BTC."""
    btc_resp = client.get("/api/ledger", params={"coin": "BTC"})
    assert btc_resp.json()["summary"]["coin"] == "BTC"

    usd_resp = client.get("/api/ledger", params={"coin": "USD"})
    assert usd_resp.json()["summary"]["coin"] == "USD"


def test_ledger_ui_shell_is_served() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/ledger")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

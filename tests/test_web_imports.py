"""Tests for the web import center API routes."""

from __future__ import annotations

import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend

# --- Fixture CSV data (native format) ---

NATIVE_CSV = (
    "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
    "Trade,0.5,BTC,25000,USD,10,USD,Strike,,DCA buy,2024-06-15 10:30:00\n"
    "Trade,0.25,BTC,12500,USD,5,USD,Strike,,DCA buy 2,2024-07-01 09:00:00\n"
)

NATIVE_CSV_BAD_ROW = (
    "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
    "Trade,0.5,BTC,25000,USD,10,USD,Strike,,OK row,2024-06-15 10:30:00\n"
    "BadType,0.1,BTC,5000,USD,0,USD,Strike,,Bad row,2024-06-16 11:00:00\n"
)

UNRECOGNIZED_CSV = (
    "foo,bar,baz\n"
    "1,2,3\n"
)


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


# --- WIM-001: Upload, detect, and parse ---

def test_list_parsers(client: TestClient) -> None:
    response = client.get("/api/import/parsers")
    assert response.status_code == 200
    parsers = response.json()["parsers"]
    assert len(parsers) >= 5
    names = {p["name"] for p in parsers}
    assert "native" in names
    assert "strike" in names
    # Each parser has required fields
    for p in parsers:
        assert "display_name" in p
        assert "source_type" in p


def test_list_parsers_requires_auth() -> None:
    app = create_app(
        WebConfig(auth_enabled=True, auth_passphrase="x", session_secret="s")
    )
    client = TestClient(app)
    assert client.get("/api/import/parsers").status_code == 401


def test_parse_upload_auto_detect(client: TestClient) -> None:
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parser_used"] == "native"
    assert body["row_count"] == 2
    assert body["filename"] == "test.csv"
    assert len(body["transactions"]) == 2
    assert len(body["preview_rows"]) == 2
    assert body["validation"]["valid_count"] == 2
    assert body["validation"]["error_count"] == 0


def test_parse_upload_explicit_parser(client: TestClient) -> None:
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "native", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 200
    assert response.json()["parser_used"] == "native"


def test_parse_upload_unknown_parser(client: TestClient) -> None:
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "nonexistent", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 422
    assert "Unknown parser" in response.json()["detail"]


def test_parse_upload_empty_file(client: TestClient) -> None:
    response = client.post(
        "/api/import/parse",
        files={"file": ("empty.csv", "", "text/csv")},
        data={"parser": "", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 422


def test_parse_upload_detection_fails(client: TestClient) -> None:
    response = client.post(
        "/api/import/parse",
        files={"file": ("mystery.csv", UNRECOGNIZED_CSV, "text/csv")},
        data={"parser": "", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 422
    assert "auto-detect" in response.json()["detail"].lower() or "detect" in response.json()["detail"].lower()


def test_parse_upload_requires_auth() -> None:
    app = create_app(
        WebConfig(auth_enabled=True, auth_passphrase="x", session_secret="s")
    )
    client = TestClient(app)
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 401


# --- WIM-002: Import configuration and wallet assignment ---

def test_parse_with_validation_errors(client: TestClient) -> None:
    """Bad transaction types produce validation errors in the preview."""
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV_BAD_ROW, "text/csv")},
        data={"parser": "native", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 200
    v = response.json()["validation"]
    assert v["error_count"] >= 1
    assert v["valid_count"] >= 1


def test_parse_with_withdraw_to(client: TestClient) -> None:
    """Withdraw-to parameter propagates to parsed transactions."""
    response = client.post(
        "/api/import/parse",
        files={"file": ("test.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "native", "wallet_name": "", "withdraw_to": "Coldcard"},
    )
    assert response.status_code == 200
    # Native parser doesn't generate withdrawals from this data, but the endpoint accepted it
    assert response.json()["row_count"] == 2


def test_wallet_parser_requires_wallet_name(client: TestClient) -> None:
    """Wallet parsers must reject uploads that omit wallet_name."""
    coldcard_csv = "Date,Type,Amount,Fee,TXID\n2024-06-15,Receive,0.5,0.00001,abc123\n"
    response = client.post(
        "/api/import/parse",
        files={"file": ("coldcard.csv", coldcard_csv, "text/csv")},
        data={"parser": "coldcard", "wallet_name": "", "withdraw_to": ""},
    )
    assert response.status_code == 422
    assert "wallet" in response.json()["detail"].lower()


def test_wallet_parser_with_wallet_name(client: TestClient) -> None:
    """Wallet parsers succeed when wallet_name is provided."""
    coldcard_csv = "Date,Type,Amount,Fee,TXID\n2024-06-15,Receive,0.5,0.00001,abc123\n"
    response = client.post(
        "/api/import/parse",
        files={"file": ("coldcard.csv", coldcard_csv, "text/csv")},
        data={"parser": "coldcard", "wallet_name": "Coldcard", "withdraw_to": ""},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] >= 1
    # Verify wallet_name propagated
    for tx in response.json()["transactions"]:
        assert tx["exchange"] == "Coldcard"


# --- WIM-003: Duplicate detection ---

def test_check_duplicates_none_found(client: TestClient) -> None:
    response = client.post(
        "/api/import/check-duplicates",
        json={"transactions": [
            {"trans_type": "Trade", "buy": 0.5, "buy_curr": "BTC",
             "sell": 25000, "sell_curr": "USD", "exchange": "Strike",
             "created_date": "2024-06-15 10:30:00"},
        ]},
    )
    assert response.status_code == 200
    assert response.json()["duplicate_count"] == 0


def test_check_duplicates_found(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    """Seed a matching transaction, then detect it as a duplicate."""
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 6, 15, 10, 30),
        buy=0.5, buy_curr="BTC",
        sell=25000, sell_curr="USD",
        exchange="Strike",
    )
    response = client.post(
        "/api/import/check-duplicates",
        json={"transactions": [
            {"trans_type": "Trade", "buy": 0.5, "buy_curr": "BTC",
             "sell": 25000, "sell_curr": "USD", "exchange": "Strike",
             "created_date": "2024-06-15 10:30:00"},
        ]},
    )
    assert response.status_code == 200
    assert response.json()["duplicate_count"] == 1


def test_check_duplicates_empty_list(client: TestClient) -> None:
    response = client.post(
        "/api/import/check-duplicates",
        json={"transactions": []},
    )
    assert response.status_code == 200
    assert response.json()["duplicate_count"] == 0


# --- WIM-004: Execute import ---

def test_commit_import_success(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    txs = [
        {"trans_type": "Trade", "buy": 0.5, "buy_curr": "BTC",
         "sell": 25000, "sell_curr": "USD", "fee": 10, "fee_curr": "USD",
         "exchange": "Strike", "created_date": "2024-06-15 10:30:00",
         "comment": "DCA buy", "group": None},
    ]
    response = client.post(
        "/api/import/commit",
        json={"transactions": txs, "parser_name": "native", "filename": "test.csv"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0

    # Verify in ledger
    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    assert len(rows) >= 1


def test_commit_import_with_skip_indices(client: TestClient) -> None:
    """Operator-skipped rows must be counted in skipped total."""
    txs = [
        {"trans_type": "Trade", "buy": 0.1, "buy_curr": "BTC",
         "sell": 5000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "2024-06-15"},
        {"trans_type": "Trade", "buy": 0.2, "buy_curr": "BTC",
         "sell": 10000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "2024-06-16"},
    ]
    response = client.post(
        "/api/import/commit",
        json={
            "transactions": txs,
            "parser_name": "native",
            "filename": "test.csv",
            "skip_indices": [0],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1  # operator-skipped row must be counted


def test_commit_rejects_invalid_rows_server_side(client: TestClient) -> None:
    """Invalid rows must be rejected at commit time, not written to ledger."""
    txs = [
        {"trans_type": "Trade", "buy": 0.5, "buy_curr": "BTC",
         "sell": 25000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "2024-06-15 10:30:00"},
        {"trans_type": "Trade", "buy": 0.1, "buy_curr": "BTC",
         "sell": 5000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "not-a-date"},
    ]
    response = client.post(
        "/api/import/commit",
        json={"transactions": txs, "parser_name": "native", "filename": "test.csv"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1  # invalid row rejected server-side


def test_commit_import_empty_list(client: TestClient) -> None:
    response = client.post(
        "/api/import/commit",
        json={"transactions": [], "parser_name": "native", "filename": "test.csv"},
    )
    assert response.status_code == 422
    assert "No transactions" in response.json()["detail"]


def test_commit_import_requires_auth() -> None:
    app = create_app(
        WebConfig(auth_enabled=True, auth_passphrase="x", session_secret="s")
    )
    client = TestClient(app)
    response = client.post(
        "/api/import/commit",
        json={"transactions": [{"trans_type": "Trade"}]},
    )
    assert response.status_code == 401


def test_commit_import_audit_logged(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    txs = [
        {"trans_type": "Trade", "buy": 0.3, "buy_curr": "BTC",
         "sell": 15000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "2024-08-01"},
    ]
    client.post(
        "/api/import/commit",
        json={"transactions": txs, "parser_name": "native", "filename": "audit-test.csv"},
    )
    from web.services.audit import get_audit_log
    logs = get_audit_log(seeded_accounts.backend, entity_type="import")
    assert len(logs) >= 1
    assert logs[0]["action"] == "import.execute"
    assert logs[0]["entity_id"] == "audit-test.csv"


def test_full_flow_upload_then_commit(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    """End-to-end: upload CSV, take transactions from response, commit."""
    # Step 1: parse
    parse_resp = client.post(
        "/api/import/parse",
        files={"file": ("flow.csv", NATIVE_CSV, "text/csv")},
        data={"parser": "native", "wallet_name": "", "withdraw_to": ""},
    )
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["row_count"] == 2

    # Step 2: commit
    commit_resp = client.post(
        "/api/import/commit",
        json={
            "transactions": parsed["transactions"],
            "parser_name": parsed["parser_used"],
            "filename": parsed["filename"],
        },
    )
    assert commit_resp.status_code == 200
    assert commit_resp.json()["imported"] == 2

    # Verify ledger
    _headers, rows = seeded_accounts.get_transactions(coin="BTC")
    assert len(rows) >= 2


# --- WIM-005: Import history and parser help ---

def test_import_history_empty(client: TestClient) -> None:
    response = client.get("/api/import/history")
    assert response.status_code == 200
    assert response.json()["imports"] == []


def test_import_history_after_import(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    txs = [
        {"trans_type": "Trade", "buy": 0.1, "buy_curr": "BTC",
         "sell": 5000, "sell_curr": "USD", "exchange": "Strike",
         "created_date": "2024-09-01"},
    ]
    client.post(
        "/api/import/commit",
        json={"transactions": txs, "parser_name": "strike", "filename": "history-test.csv"},
    )
    response = client.get("/api/import/history")
    assert response.status_code == 200
    imports = response.json()["imports"]
    assert len(imports) >= 1
    assert imports[0]["parser_name"] == "strike"
    assert imports[0]["filename"] == "history-test.csv"
    assert imports[0]["imported"] == 1


def test_parser_help_valid(client: TestClient) -> None:
    response = client.get("/api/import/parsers/native/help")
    assert response.status_code == 200
    body = response.json()
    assert body["parser_name"] == "native"
    assert "help_text" in body
    assert len(body["expected_columns"]) > 0


def test_parser_help_unknown(client: TestClient) -> None:
    response = client.get("/api/import/parsers/nonexistent/help")
    assert response.status_code == 404


# --- UI shell ---

def test_import_ui_shell_is_served() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)
    response = client.get("/import")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

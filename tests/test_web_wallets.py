"""Tests for authenticated wallet management API routes."""

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
        wallet_id="OldWallet",
        wallet_type="software",
        custody="self-custodied",
        description="Legacy wallet",
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


# --- List ---

def test_list_wallets(client: TestClient) -> None:
    response = client.get("/api/wallets")
    assert response.status_code == 200
    body = response.json()
    assert len(body["wallets"]) == 3
    ids = {w["wallet_id"] for w in body["wallets"]}
    assert ids == {"Coldcard", "River", "OldWallet"}
    # Check transaction counts
    for w in body["wallets"]:
        if w["wallet_id"] == "Coldcard":
            assert w["transaction_count"] >= 1
        if w["wallet_id"] == "OldWallet":
            assert w["transaction_count"] == 0


def test_list_wallets_active_only(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    seeded_accounts.wallet_query.update_wallet("OldWallet", active=False)
    response = client.get("/api/wallets", params={"active_only": "true"})
    assert response.status_code == 200
    ids = {w["wallet_id"] for w in response.json()["wallets"]}
    assert "OldWallet" not in ids


def test_list_wallets_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)
    assert client.get("/api/wallets").status_code == 401


# --- Create ---

def test_create_wallet(client: TestClient) -> None:
    response = client.post("/api/wallets", json={
        "wallet_id": "Trezor",
        "wallet_type": "hardware",
        "custody": "self-custodied",
        "description": "New device",
    })
    assert response.status_code == 201
    assert response.json()["wallet_id"] == "Trezor"
    assert response.json()["active"] is True

    # Verify it appears in list
    listed = client.get("/api/wallets")
    ids = {w["wallet_id"] for w in listed.json()["wallets"]}
    assert "Trezor" in ids


def test_create_wallet_duplicate_409(client: TestClient) -> None:
    response = client.post("/api/wallets", json={
        "wallet_id": "Coldcard",
        "wallet_type": "hardware",
        "custody": "self-custodied",
    })
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- Get detail ---

def test_get_wallet(client: TestClient) -> None:
    response = client.get("/api/wallets/Coldcard")
    assert response.status_code == 200
    body = response.json()
    assert body["wallet_id"] == "Coldcard"
    assert body["wallet_type"] == "hardware"
    assert body["transaction_count"] >= 1


def test_get_wallet_404(client: TestClient) -> None:
    response = client.get("/api/wallets/Nonexistent")
    assert response.status_code == 404


# --- Update ---

def test_update_wallet(client: TestClient) -> None:
    response = client.patch("/api/wallets/OldWallet", json={
        "description": "Updated description",
        "custody": "multisig",
    })
    assert response.status_code == 200
    assert response.json()["custody"] == "multisig"

    detail = client.get("/api/wallets/OldWallet")
    assert detail.json()["custody"] == "multisig"


def test_update_wallet_no_fields(client: TestClient) -> None:
    response = client.patch("/api/wallets/OldWallet", json={})
    assert response.status_code == 422


def test_toggle_active(client: TestClient) -> None:
    response = client.patch("/api/wallets/OldWallet", json={"active": False})
    assert response.status_code == 200
    assert response.json()["active"] is False

    response = client.patch("/api/wallets/OldWallet", json={"active": True})
    assert response.status_code == 200
    assert response.json()["active"] is True


def test_update_wallet_404(client: TestClient) -> None:
    response = client.patch("/api/wallets/NoSuchWallet", json={"custody": "custodial"})
    assert response.status_code == 404


# --- Rename ---

def test_rename_wallet(client: TestClient) -> None:
    response = client.post("/api/wallets/rename", json={
        "wallet_id": "OldWallet",
        "new_wallet_id": "NewWallet",
    })
    assert response.status_code == 200
    assert response.json()["wallet_id"] == "NewWallet"

    # Old name should be gone
    assert client.get("/api/wallets/OldWallet").status_code == 404
    # New name should exist
    assert client.get("/api/wallets/NewWallet").status_code == 200


def test_rename_wallet_to_existing_409(client: TestClient) -> None:
    response = client.post("/api/wallets/rename", json={
        "wallet_id": "OldWallet",
        "new_wallet_id": "Coldcard",
    })
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- Merge ---

def test_merge_wallets(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    # Add a tx to OldWallet so we can verify it moves
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 5, 1),
        buy=0.1,
        buy_curr="BTC",
        sell=5000.0,
        sell_curr="USD",
        exchange="OldWallet",
    )

    response = client.post("/api/wallets/merge", json={
        "source_wallet_id": "OldWallet",
        "target_wallet_id": "Coldcard",
    })
    assert response.status_code == 200
    assert response.json()["action"] == "merge"

    # Source should be gone
    assert client.get("/api/wallets/OldWallet").status_code == 404
    # Target should have more transactions
    detail = client.get("/api/wallets/Coldcard")
    assert detail.json()["transaction_count"] >= 2


def test_merge_wallet_same_id_422(client: TestClient) -> None:
    response = client.post("/api/wallets/merge", json={
        "source_wallet_id": "Coldcard",
        "target_wallet_id": "Coldcard",
    })
    assert response.status_code == 422
    assert "different" in response.json()["detail"]


# --- Sync ---

def test_sync_wallets(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    # Add a ledger entry referencing a wallet not in wallets table
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 8, 1),
        buy=0.01,
        buy_curr="BTC",
        sell=500.0,
        sell_curr="USD",
        exchange="Phantom",
    )

    response = client.post("/api/wallets/sync")
    assert response.status_code == 200
    assert response.json()["created"] >= 1

    # Phantom should now appear
    listed = client.get("/api/wallets")
    ids = {w["wallet_id"] for w in listed.json()["wallets"]}
    assert "Phantom" in ids


# --- Audit log ---

def test_audit_log_on_create(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    client.post("/api/wallets", json={
        "wallet_id": "AuditTest",
        "wallet_type": "mobile",
        "custody": "self-custodied",
    })

    from web.services.audit import get_audit_log
    logs = get_audit_log(seeded_accounts.backend, entity_type="wallet", entity_id="AuditTest")
    assert len(logs) >= 1
    assert logs[0]["action"] == "wallet.create"
    assert logs[0]["outcome"] == "success"


def test_audit_log_on_rename(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    client.post("/api/wallets/rename", json={"wallet_id": "OldWallet", "new_wallet_id": "RenamedWallet"})

    from web.services.audit import get_audit_log
    logs = get_audit_log(seeded_accounts.backend, entity_type="wallet", entity_id="RenamedWallet")
    assert len(logs) >= 1
    assert logs[0]["action"] == "wallet.rename"


def test_audit_log_on_merge(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    client.post("/api/wallets/merge", json={"source_wallet_id": "OldWallet", "target_wallet_id": "Coldcard"})

    from web.services.audit import get_audit_log
    logs = get_audit_log(seeded_accounts.backend, entity_type="wallet", entity_id="Coldcard")
    assert len(logs) >= 1
    assert logs[0]["action"] == "wallet.merge"


# --- Slash-containing wallet IDs ---

def test_wallet_id_with_slash(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    """Wallet IDs containing slashes (e.g. BNB/RUNE LP) must work."""
    client.post("/api/wallets", json={
        "wallet_id": "BNB/RUNE LP",
        "wallet_type": "exchange",
        "custody": "custodial",
    })

    # GET detail with slash in path
    response = client.get("/api/wallets/BNB/RUNE LP")
    assert response.status_code == 200
    assert response.json()["wallet_id"] == "BNB/RUNE LP"

    # PATCH with slash in path
    response = client.patch("/api/wallets/BNB/RUNE LP", json={"description": "LP pool"})
    assert response.status_code == 200
    assert response.json()["description"] == "LP pool"

    # Rename via body (no path issue)
    response = client.post("/api/wallets/rename", json={
        "wallet_id": "BNB/RUNE LP",
        "new_wallet_id": "BNB/RUNE LP v2",
    })
    assert response.status_code == 200
    assert response.json()["wallet_id"] == "BNB/RUNE LP v2"


# --- UI shell ---

# --- Notes preservation ---

def test_wallet_notes_preserved_on_edit(client: TestClient) -> None:
    """Editing other fields must not clear the notes field."""
    client.post("/api/wallets", json={
        "wallet_id": "NotesTest",
        "wallet_type": "hardware",
        "custody": "self-custodied",
        "description": "Test wallet",
        "notes": "Important operational note",
    })

    # Edit only the description — notes must survive
    response = client.patch("/api/wallets/NotesTest", json={
        "description": "Updated description",
    })
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"
    assert response.json()["notes"] == "Important operational note"

    # Verify via GET detail
    detail = client.get("/api/wallets/NotesTest")
    assert detail.json()["notes"] == "Important operational note"


def test_wallet_notes_returned_in_list(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    """Notes field should be present in wallet list responses."""
    seeded_accounts.wallet_query.update_wallet("Coldcard", notes="Cold storage only")

    response = client.get("/api/wallets")
    cc = next(w for w in response.json()["wallets"] if w["wallet_id"] == "Coldcard")
    assert cc["notes"] == "Cold storage only"


def test_wallets_ui_shell_is_served() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/wallets")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

"""Tests for authenticated portfolio/dashboard API routes."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend
from web.services.wallet_verification import record_wallet_verification_run


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
    assert body["portfolio_verification"]["status"] == "stale"
    assert body["portfolio_verification"]["eligible_wallet_count"] == 2
    assert body["wallets"][0]["verification_eligible"] is True
    assert body["wallets"][1]["verification_eligible"] is False


def test_dashboard_reports_verified_posture_when_all_private_wallets_are_verified(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
) -> None:
    verified_at = datetime.now(timezone.utc)
    for wallet_id, balance in [("Coldcard", 1.1), ("Casa", 0.25)]:
        record_wallet_verification_run(
            seeded_accounts.backend,
            wallet_id=wallet_id,
            status="verified",
            coverage="full",
            descriptor_source_type="session",
            recency_window_days=30,
            ledger_balance=balance,
            verified_balance=balance,
            drift_btc=0.0,
            verified_at=verified_at,
        )

    response = client.get("/api/portfolio/dashboard", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_verification"]["status"] == "verified"
    coldcard = next(wallet for wallet in body["wallets"] if wallet["wallet_id"] == "Coldcard")
    casa = next(wallet for wallet in body["wallets"] if wallet["wallet_id"] == "Casa")
    river = next(wallet for wallet in body["wallets"] if wallet["wallet_id"] == "River")
    assert coldcard["verification_status"] == "verified"
    assert coldcard["verification_is_recent"] is True
    assert casa["verification_status"] == "verified"
    assert river["verification_eligible"] is False


def test_dashboard_shows_only_active_wallets_with_nonzero_balance(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
) -> None:
    seeded_accounts.wallet_query.add_wallet(
        wallet_id="EmptyActive",
        wallet_type="hardware",
        custody="self-custodied",
    )
    seeded_accounts.wallet_query.add_wallet(
        wallet_id="DustArchive",
        wallet_type="hardware",
        custody="self-custodied",
    )
    seeded_accounts.wallet_query.update_wallet("DustArchive", active=False)
    seeded_accounts.deposit(
        exchange="DustArchive",
        deposit_date=datetime(2024, 8, 1),
        buy=0.00000001,
        buy_curr="BTC",
    )

    response = client.get(
        "/api/portfolio/dashboard",
        params={"coin": "BTC", "include_inactive": "true"},
    )

    assert response.status_code == 200
    wallet_ids = [wallet["wallet_id"] for wallet in response.json()["wallets"]]
    assert set(wallet_ids) == {"Coldcard", "River", "Casa"}


def test_wallet_detail_returns_balance_and_transactions(client: TestClient) -> None:
    response = client.get("/api/portfolio/wallet/Coldcard", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["wallet"]["wallet_id"] == "Coldcard"
    assert body["wallet"]["custody"] == "self-custodied"
    assert body["wallet"]["balance"] == pytest.approx(1.1)
    assert body["wallet"]["active"] is True
    assert body["wallet"]["percentage"] > 0
    assert body["verification_eligibility"]["eligible"] is True
    assert body["latest_verification"] is None
    assert len(body["recent_transactions"]) >= 1


def test_wallet_detail_includes_latest_verification_state(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
) -> None:
    record_wallet_verification_run(
        seeded_accounts.backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
        descriptor_source_type="session",
        recency_window_days=30,
        ledger_balance=1.1,
        verified_balance=1.1,
        drift_btc=0.0,
        highest_scanned_index=22,
        scan_ceiling=50,
        gap_limit=20,
        verified_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
    )

    response = client.get("/api/portfolio/wallet/Coldcard", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["latest_verification"]["status"] == "verified"
    assert body["latest_verification"]["coverage"] == "full"
    assert body["latest_verification"]["scan_ceiling"] == 50
    assert body["latest_verification"]["gap_limit"] == 20


def test_dashboard_and_wallet_detail_fall_back_to_retained_verification_history(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
) -> None:
    run = record_wallet_verification_run(
        seeded_accounts.backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
        descriptor_source_type="session",
        recency_window_days=30,
        ledger_balance=1.1,
        verified_balance=1.1,
        drift_btc=0.0,
        highest_scanned_index=22,
        scan_ceiling=50,
        gap_limit=20,
        verified_at=datetime.now(timezone.utc),
    )
    seeded_accounts.backend.execute(
        "DELETE FROM web_wallet_verification_state WHERE wallet_id = :wallet_id",
        {"wallet_id": "Coldcard"},
    )
    seeded_accounts.backend.commit()

    dashboard = client.get("/api/portfolio/dashboard", params={"coin": "BTC"})
    detail = client.get("/api/portfolio/wallet/Coldcard", params={"coin": "BTC"})

    assert dashboard.status_code == 200
    dashboard_wallet = next(
        wallet
        for wallet in dashboard.json()["wallets"]
        if wallet["wallet_id"] == "Coldcard"
    )
    assert dashboard_wallet["verification_status"] == "verified"
    assert dashboard_wallet["verification_coverage"] == "full"
    assert detail.status_code == 200
    assert detail.json()["latest_verification"]["verification_id"] == run.verification_id


def test_wallet_detail_prefers_newer_history_over_stale_latest_state(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
) -> None:
    older = datetime(2026, 3, 20, tzinfo=timezone.utc)
    newer = datetime.now(timezone.utc)
    old_run = record_wallet_verification_run(
        seeded_accounts.backend,
        wallet_id="Coldcard",
        status="drift_detected",
        coverage="full",
        verified_at=older,
    )
    new_run = record_wallet_verification_run(
        seeded_accounts.backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
        verified_at=newer,
    )
    seeded_accounts.backend.execute(
        """
        UPDATE web_wallet_verification_state
        SET verification_id = :verification_id,
            status = :status,
            verified_at = :verified_at,
            stale_after = :stale_after
        WHERE wallet_id = :wallet_id
        """,
        {
            "wallet_id": "Coldcard",
            "verification_id": old_run.verification_id,
            "status": old_run.status,
            "verified_at": old_run.verified_at.isoformat(),
            "stale_after": old_run.stale_after.isoformat(),
        },
    )
    seeded_accounts.backend.commit()

    response = client.get("/api/portfolio/wallet/Coldcard", params={"coin": "BTC"})

    assert response.status_code == 200
    latest = response.json()["latest_verification"]
    assert latest["verification_id"] == new_run.verification_id
    assert latest["status"] == "verified"


def test_wallet_detail_marks_custodial_wallet_not_eligible_for_verification(
    client: TestClient,
) -> None:
    response = client.get("/api/portfolio/wallet/River", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["wallet"]["wallet_id"] == "River"
    assert body["verification_eligibility"]["eligible"] is False
    assert "self-custodied or multisig" in body["verification_eligibility"]["reason"]


def test_wallet_detail_returns_404_for_unknown_wallet(client: TestClient) -> None:
    response = client.get("/api/portfolio/wallet/NonExistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


def test_wallet_detail_requires_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    response = client.get("/api/portfolio/wallet/Coldcard")

    assert response.status_code == 401


def test_wallet_detail_for_inactive_wallet(client: TestClient) -> None:
    response = client.get("/api/portfolio/wallet/OldVault", params={"coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["wallet"]["wallet_id"] == "OldVault"
    assert body["wallet"]["active"] is False
    assert body["wallet"]["balance"] == pytest.approx(0.0)


def test_wallet_ui_shell_is_served(client: TestClient) -> None:
    app = create_app(WebConfig(auth_enabled=False))
    unauthenticated = TestClient(app)

    response = unauthenticated.get("/wallet/Coldcard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text


def test_dashboard_ui_shell_is_served_on_tax_path() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    response = client.get("/tax")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Bitcoin Accounting" in response.text

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


def test_sales_index_lists_coins_and_years_with_sales(client: TestClient) -> None:
    response = client.get("/api/tax/sales-index")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["current_year"], int)
    # USD is "sold" when buying BTC, but fiat is never a tax-reportable coin here.
    assert body["coins"] == [{"coin": "BTC", "years": [2025, 2024]}]


def test_overview_lists_only_wallets_with_sales_for_2025(client: TestClient) -> None:
    response = client.get("/api/tax/overview", params={"tax_year": 2025, "coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["has_sales"] is True
    assert body["wallet_separation_required"] is True
    assert body["totals_method"] == "wallet_fifo"
    assert [w["wallet_id"] for w in body["wallets"]] == ["Coldcard"]
    coldcard = body["wallets"][0]
    assert coldcard["sale_count"] == 1
    assert coldcard["quantity_sold"] == 0.5
    assert coldcard["first_sale_date"] == "2025-12-15"
    assert coldcard["gain_loss_usd"] == pytest.approx(20000.0)
    assert coldcard["short_term_gain_usd"] == pytest.approx(20000.0)
    assert body["totals"]["wallet_count"] == 1
    assert body["totals"]["proceeds_usd"] == pytest.approx(45000.0)
    assert body["totals"]["gain_loss_usd"] == pytest.approx(20000.0)
    assert body["warnings"] == []


def test_overview_reports_no_sales_for_empty_year(client: TestClient) -> None:
    response = client.get("/api/tax/overview", params={"tax_year": 2023, "coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["has_sales"] is False
    assert body["wallets"] == []
    assert body["totals"]["sale_count"] == 0
    assert body["message"] == "No sales found for tax year 2023 with digital asset BTC."


def test_overview_uses_global_fifo_totals_before_2025(client: TestClient) -> None:
    response = client.get("/api/tax/overview", params={"tax_year": 2024, "coin": "BTC"})

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_separation_required"] is False
    assert body["totals_method"] == "global_fifo"
    assert [w["wallet_id"] for w in body["wallets"]] == ["Strike"]
    assert body["totals"]["gain_loss_usd"] == pytest.approx(10000.0)
    assert body["warnings"][0]["code"] == "global_fifo_historical"


def test_overview_reports_sales_from_wallet_without_purchase_lots(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    # Coins transferred into an exchange and sold there have no purchase lot in
    # that wallet; the sale must still be reported (with missing basis).
    seeded_accounts.deposit(
        deposit_date=datetime(2025, 3, 1), buy=0.1, buy_curr="BTC", exchange="Kraken"
    )
    seeded_accounts.execute_trade(
        trade_date=datetime(2025, 6, 1),
        buy=9000.0,
        buy_curr="USD",
        sell=0.1,
        sell_curr="BTC",
        exchange="Kraken",
    )

    response = client.get("/api/tax/overview", params={"tax_year": 2025, "coin": "BTC"})

    body = response.json()
    assert [w["wallet_id"] for w in body["wallets"]] == ["Coldcard", "Kraken"]
    kraken = body["wallets"][1]
    assert kraken["proceeds_usd"] == pytest.approx(9000.0)
    assert kraken["cost_basis_usd"] == 0.0
    assert kraken["missing_basis_quantity"] == pytest.approx(0.1)
    assert body["totals"]["proceeds_usd"] == pytest.approx(54000.0)
    assert "missing_basis" in [w["code"] for w in body["warnings"]]


def test_overview_flags_spends_not_included_in_gains(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    seeded_accounts.ledger_writer.spend(
        datetime(2025, 7, 4), 0.01, "BTC", 0.0, "", "Vault", "", "coffee"
    )

    body = client.get("/api/tax/overview", params={"tax_year": 2025, "coin": "BTC"}).json()

    assert body["spend_count"] == 1
    assert "spends_not_included" in [w["code"] for w in body["warnings"]]


def test_holdings_lists_wallets_with_positive_balance(client: TestClient) -> None:
    response = client.get("/api/tax/holdings", params={"coin": "BTC"})

    assert response.status_code == 200
    assert response.json() == {
        "coin": "BTC",
        "total_balance": 0.25,
        "wallets": [{"wallet_id": "Vault", "balance": 0.25, "open_lot_quantity": 0.25}],
    }


def test_holdings_include_exchanges_whose_coins_moved_to_self_custody(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    # Bought on Kraken, then withdrawn to a hardware wallet: Kraken holds
    # nothing but still has the open lots a future sale there would use.
    seeded_accounts.execute_trade(
        trade_date=datetime(2023, 5, 1),
        buy=1.0,
        buy_curr="BTC",
        sell=30000.0,
        sell_curr="USD",
        exchange="Kraken",
    )
    seeded_accounts.transfer_funds(
        withdraw_date=datetime(2023, 5, 2),
        from_account="Kraken",
        tx_amount=1.0,
        to_account="Coldcard",
    )

    body = client.get("/api/tax/holdings", params={"coin": "BTC"}).json()

    assert body["wallets"] == [
        {"wallet_id": "Kraken", "balance": 0.0, "open_lot_quantity": 1.0},
        {"wallet_id": "Vault", "balance": 0.25, "open_lot_quantity": 0.25},
        {"wallet_id": "Coldcard", "balance": 1.0, "open_lot_quantity": 0.0},
    ]

    forecast = client.get(
        "/api/tax/forecast",
        params={"coin": "BTC", "quantity": 0.4, "sale_price_usd": 100000, "wallet": "Kraken"},
    ).json()
    assert forecast["summary"]["total_cost_basis_usd"] == pytest.approx(12000.0)
    assert forecast["summary"]["missing_basis_quantity"] == 0.0
    assert "forecast_exceeds_wallet_balance" in [w["code"] for w in forecast["warnings"]]


def test_overview_keeps_proceeds_of_same_timestamp_sales_in_separate_wallets(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    # Vault sells at the exact timestamp of Coldcard's sale; each sale must keep
    # its own proceeds rather than the first trade found at that time.
    seeded_accounts.execute_trade(
        trade_date=datetime(2025, 12, 15),
        buy=12000.0,
        buy_curr="USD",
        sell=0.1,
        sell_curr="BTC",
        exchange="Vault",
    )

    body = client.get("/api/tax/overview", params={"tax_year": 2025, "coin": "BTC"}).json()

    proceeds = {w["wallet_id"]: w["proceeds_usd"] for w in body["wallets"]}
    assert proceeds == {
        "Coldcard": pytest.approx(45000.0),
        "Vault": pytest.approx(12000.0),
    }


def _add_sales_without_wallet(accounts: BitcoinAccounts, year: int) -> None:
    for day, wallet in ((1, ""), (2, None)):
        accounts.execute_trade(
            trade_date=datetime(year, 8, day),
            buy=1000.0,
            buy_curr="USD",
            sell=0.01,
            sell_curr="BTC",
            exchange=wallet or "",
        )
    accounts.backend.execute(
        "UPDATE ledger SET exchange = NULL WHERE createddate LIKE :day",
        {"day": f"{year}-08-02%"},
    )
    accounts.backend.commit()


def test_overview_separates_2025_sales_with_no_wallet(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    _add_sales_without_wallet(seeded_accounts, 2025)

    body = client.get("/api/tax/overview", params={"tax_year": 2025, "coin": "BTC"}).json()

    assert [w["wallet_id"] for w in body["wallets"]] == ["Coldcard"]
    assert body["unassigned_sale_count"] == 2
    assert body["totals"]["sale_count"] == 1
    assert body["totals"]["proceeds_usd"] == pytest.approx(45000.0)
    warning = next(w for w in body["warnings"] if w["code"] == "unassigned_wallet_sales")
    assert "not included in these totals" in warning["message"]


def test_overview_counts_pre_2025_sales_with_no_wallet_in_global_totals(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    _add_sales_without_wallet(seeded_accounts, 2024)

    body = client.get("/api/tax/overview", params={"tax_year": 2024, "coin": "BTC"}).json()

    assert body["totals_method"] == "global_fifo"
    assert [w["wallet_id"] for w in body["wallets"]] == ["Strike"]
    assert body["totals"]["sale_count"] == 3
    assert body["totals"]["proceeds_usd"] == pytest.approx(62000.0)
    assert "unassigned_wallet_sales" in [w["code"] for w in body["warnings"]]


def test_overview_reports_year_whose_only_sales_have_no_wallet(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    _add_sales_without_wallet(seeded_accounts, 2026)

    body = client.get("/api/tax/overview", params={"tax_year": 2026, "coin": "BTC"}).json()

    assert body["has_sales"] is True
    assert body["wallets"] == []
    assert body["unassigned_sale_count"] == 2
    assert "none has a wallet recorded" in body["message"]


def test_overview_keeps_spend_warning_in_year_without_sales(
    seeded_accounts: BitcoinAccounts, client: TestClient
) -> None:
    seeded_accounts.ledger_writer.spend(
        datetime(2023, 7, 4), 0.01, "BTC", 0.0, "", "Vault", "", "gift"
    )

    body = client.get("/api/tax/overview", params={"tax_year": 2023, "coin": "BTC"}).json()

    assert body["has_sales"] is False
    assert body["message"] == "No sales found for tax year 2023 with digital asset BTC."
    assert [w["code"] for w in body["warnings"]] == ["spends_not_included"]

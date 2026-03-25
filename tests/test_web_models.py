"""Tests for canonical web JSON models."""

from __future__ import annotations

from web.models import (
    CustodyBreakdownResource,
    ForecastSummaryResource,
    ForecastResponse,
    ForecastLotResource,
    GainsLotResource,
    GainsReportResponse,
    GainsSummaryResource,
    GainsWorksheetEntryResource,
    PortfolioDashboardResponse,
    PortfolioSummaryResource,
    TaxPolicyWarningResource,
    TransactionResource,
    WalletBalanceResource,
    WalletResource,
)


def test_wallet_resource_serializes_expected_fields() -> None:
    wallet = WalletResource(
        wallet_id="Coldcard",
        wallet_type="hardware",
        custody="self-custodied",
        description="Primary vault",
        active=True,
    )

    assert wallet.model_dump() == {
        "wallet_id": "Coldcard",
        "wallet_type": "hardware",
        "custody": "self-custodied",
        "description": "Primary vault",
        "notes": None,
        "active": True,
    }


def test_transaction_resource_uses_api_friendly_names() -> None:
    tx = TransactionResource(
        transaction_id=42,
        created_at="2026-03-24T12:00:00Z",
        transaction_type="Trade",
        buy_amount=0.1,
        buy_currency="BTC",
        sell_amount=8000.0,
        sell_currency="USD",
        fee_amount=15.0,
        fee_currency="USD",
        wallet_id="Strike",
        group="",
        comment="DCA",
        deleted=False,
    )

    dumped = tx.model_dump()
    assert dumped["transaction_id"] == 42
    assert dumped["buy_currency"] == "BTC"
    assert dumped["sell_currency"] == "USD"
    assert "Buy Cur." not in dumped


def test_portfolio_and_tax_summary_models_dump_cleanly() -> None:
    portfolio = PortfolioSummaryResource(
        coin="BTC",
        total_balance=1.25,
        average_cost_basis_usd=48250.12,
        wallet_count=3,
        active_wallet_count=2,
    )
    gains = GainsSummaryResource(
        tax_year=2026,
        coin="BTC",
        wallet_id="Coldcard",
        lot_count=4,
        proceeds_usd=12000.0,
        cost_basis_usd=8500.0,
        gain_loss_usd=3500.0,
        short_term_lot_count=1,
        long_term_lot_count=3,
    )
    forecast = ForecastSummaryResource(
        coin="BTC",
        wallet_id="Coldcard",
        quantity=0.25,
        sale_price_usd=92000.0,
        total_cost_basis_usd=7000.0,
        total_proceeds_usd=23000.0,
        short_term_quantity=0.05,
        long_term_quantity=0.20,
        missing_basis_quantity=0.0,
    )

    assert portfolio.model_dump()["coin"] == "BTC"
    assert gains.model_dump()["tax_year"] == 2026
    assert forecast.model_dump()["total_proceeds_usd"] == 23000.0


def test_portfolio_dashboard_payload_dumps_cleanly() -> None:
    payload = PortfolioDashboardResponse(
        summary=PortfolioSummaryResource(
            coin="BTC",
            total_balance=1.25,
            average_cost_basis_usd=48250.12,
            wallet_count=3,
            active_wallet_count=2,
        ),
        custody_breakdown=[
            CustodyBreakdownResource(
                custody="self-custodied",
                balance=1.0,
                percentage=80.0,
            )
        ],
        wallets=[
            WalletBalanceResource(
                wallet_id="Coldcard",
                wallet_type="hardware",
                custody="self-custodied",
                description="Primary vault",
                active=True,
                balance=1.0,
                percentage=80.0,
            )
        ],
        recent_transactions=[
            TransactionResource(
                transaction_id=42,
                created_at="2026-03-24 12:00:00",
                transaction_type="Trade",
                buy_amount=0.1,
                buy_currency="BTC",
                sell_amount=8000.0,
                sell_currency="USD",
                fee_amount=0.0,
                fee_currency="USD",
                wallet_id="Strike",
                group="",
                comment="DCA",
                deleted=False,
            )
        ],
        using_inferred_custody=False,
    )

    dumped = payload.model_dump()
    assert dumped["summary"]["wallet_count"] == 3
    assert dumped["custody_breakdown"][0]["custody"] == "self-custodied"
    assert dumped["wallets"][0]["wallet_id"] == "Coldcard"


def test_tax_report_and_forecast_payloads_dump_cleanly() -> None:
    warning = TaxPolicyWarningResource(
        code="global_fifo_historical",
        severity="info",
        message="Historical preview only.",
    )
    report = GainsReportResponse(
        summary=GainsSummaryResource(
            tax_year=2024,
            coin="BTC",
            wallet_id=None,
            lot_count=1,
            proceeds_usd=60000.0,
            cost_basis_usd=50000.0,
            gain_loss_usd=10000.0,
            short_term_lot_count=1,
            long_term_lot_count=0,
        ),
        lots=[
            GainsLotResource(
                description="1.00000000 BTC",
                date_acquired="01/01/2024",
                date_sold="12/01/2024",
                proceeds_usd=60000.0,
                cost_basis_usd=50000.0,
                term="Short",
            )
        ],
        worksheet=[
            GainsWorksheetEntryResource(
                sale_date="12/01/2024",
                sale_quantity=1.0,
                proceeds_usd=60000.0,
                acquire_date="01/01/2024",
                lot_quantity=1.0,
                unit_cost_basis_usd=50000.0,
                total_cost_basis_usd=50000.0,
                holding_days=334,
                term="Short",
                gain_loss_usd=10000.0,
                missing_basis=False,
            )
        ],
        warnings=[warning],
    )
    forecast = ForecastResponse(
        summary=ForecastSummaryResource(
            coin="BTC",
            wallet_id="Coldcard",
            quantity=0.25,
            sale_price_usd=92000.0,
            total_cost_basis_usd=7000.0,
            total_proceeds_usd=23000.0,
            short_term_quantity=0.05,
            long_term_quantity=0.20,
            missing_basis_quantity=0.0,
        ),
        current_balance=1.25,
        lots=[
            ForecastLotResource(
                acquire_date="2024-01-01",
                quantity=0.25,
                unit_cost_usd=28000.0,
                cost_basis_usd=7000.0,
                holding_days=400,
                term="Long",
                missing_basis=False,
            )
        ],
        warnings=[],
    )

    assert report.model_dump()["warnings"][0]["code"] == "global_fifo_historical"
    assert forecast.model_dump()["lots"][0]["term"] == "Long"

"""Tax reporting service helpers for web routes."""

from __future__ import annotations

import csv
from io import StringIO

from fastapi import HTTPException, status

from bitcoinAccounts import BitcoinAccounts
from web.models import (
    ForecastLotResource,
    ForecastResponse,
    ForecastSummaryResource,
    GainsLotResource,
    GainsReportResponse,
    GainsSummaryResource,
    GainsWorksheetEntryResource,
    TaxPolicyResource,
    TaxPolicyWarningResource,
)

IRS_WALLET_RULES_DOC = "docs/IRS_2025_WALLET_RULES.md"


class TaxPolicyError(ValueError):
    """Raised when a tax workflow violates configured operator policy."""


def _tax_policy_warnings(
    tax_year: int | None = None,
    wallet: str | None = None,
    *,
    strict_wallet_requirement: bool = False,
) -> list[TaxPolicyWarningResource]:
    warnings: list[TaxPolicyWarningResource] = []

    if tax_year is not None and tax_year >= 2025 and wallet is None:
        message = (
            "Tax year 2025 and later requires an explicit wallet filter for "
            "wallet-separated FIFO reporting."
        )
        if strict_wallet_requirement:
            raise TaxPolicyError(message)
        warnings.append(
            TaxPolicyWarningResource(
                code="wallet_required_2025",
                severity="warning",
                message=message,
                reference_doc=IRS_WALLET_RULES_DOC,
            )
        )
    elif tax_year is not None and tax_year < 2025 and wallet is None:
        warnings.append(
            TaxPolicyWarningResource(
                code="global_fifo_historical",
                severity="info",
                message=(
                    "Global FIFO preview is allowed for pre-2025 tax years. "
                    "Use a wallet filter when you want wallet-specific review."
                ),
                reference_doc=IRS_WALLET_RULES_DOC,
            )
        )

    return warnings


def get_tax_policy() -> TaxPolicyResource:
    """Return static tax policy metadata for web clients."""
    return TaxPolicyResource(
        wallet_separation_required_from_tax_year=2025,
        strict_wallet_enforcement_for_exports=True,
        reference_doc=IRS_WALLET_RULES_DOC,
        summary=(
            "Wallet-separated FIFO is required for tax year 2025 and later. "
            "Historical global FIFO remains available only as a convenience view."
        ),
    )


def _parse_float(value: str) -> float:
    return float(value)


def _parse_holding_days(value: str) -> int | None:
    if value == "UNKNOWN":
        return None
    return int(value)


def _worksheet_missing_basis(entry: dict[str, str]) -> bool:
    return entry["Acquire Date"] == "UNKNOWN"


def build_gains_report(
    accounts: BitcoinAccounts,
    *,
    tax_year: int,
    coin: str = "BTC",
    wallet: str | None = None,
    strict_wallet_requirement: bool = False,
) -> GainsReportResponse:
    """Build a JSON gains report from the existing tax calculator."""
    warnings = _tax_policy_warnings(
        tax_year,
        wallet,
        strict_wallet_requirement=strict_wallet_requirement,
    )
    sales, worksheet = accounts.get_sales_for_1099b(coin, tax_year, wallet=wallet)

    lots = [
        GainsLotResource(
            description=row["Description"],
            date_acquired=row["Date Acquired"],
            date_sold=row["Date Sold"],
            proceeds_usd=_parse_float(row["Proceeds"]),
            cost_basis_usd=_parse_float(row["Cost Basis"]),
            term=row["Term"],
        )
        for row in sales
    ]

    worksheet_rows = [
        GainsWorksheetEntryResource(
            sale_date=row["Sale Date"],
            sale_quantity=_parse_float(row["Sale Quantity"]),
            proceeds_usd=_parse_float(row["Proceeds"]),
            acquire_date=row["Acquire Date"],
            lot_quantity=_parse_float(row["Lot Quantity"]),
            unit_cost_basis_usd=_parse_float(row["Unit Cost Basis"]),
            total_cost_basis_usd=_parse_float(row["Total Cost Basis"]),
            holding_days=_parse_holding_days(row["Holding Days"]),
            term=row["Term"],
            gain_loss_usd=_parse_float(row["Gain/Loss"]),
            missing_basis=_worksheet_missing_basis(row),
        )
        for row in worksheet
    ]

    proceeds_total = sum(lot.proceeds_usd for lot in lots)
    cost_basis_total = sum(lot.cost_basis_usd for lot in lots)
    summary = GainsSummaryResource(
        tax_year=tax_year,
        coin=coin,
        wallet_id=wallet,
        lot_count=len(lots),
        proceeds_usd=proceeds_total,
        cost_basis_usd=cost_basis_total,
        gain_loss_usd=proceeds_total - cost_basis_total,
        short_term_lot_count=sum(1 for lot in lots if lot.term == "Short"),
        long_term_lot_count=sum(1 for lot in lots if lot.term == "Long"),
    )

    return GainsReportResponse(
        summary=summary,
        lots=lots,
        worksheet=worksheet_rows,
        warnings=warnings,
    )


def build_forecast_response(
    accounts: BitcoinAccounts,
    *,
    coin: str = "BTC",
    quantity: float,
    sale_price_usd: float,
    wallet: str | None = None,
) -> ForecastResponse:
    """Build a hypothetical sale forecast from the existing tax calculator."""
    warnings = _tax_policy_warnings(wallet=wallet, tax_year=None)
    if wallet:
        current_balance = float(accounts.get_wallet_balance(coin, wallet))
    else:
        current_balance = float(accounts.get_balance(coin))

    lots_data, summary_data = accounts.forecast_capital_gains_fifo(
        coin,
        quantity,
        sale_price_usd,
        wallet=wallet,
    )

    lots = [
        ForecastLotResource(
            acquire_date=(
                lot["acquire_date"].strftime("%Y-%m-%d")
                if lot["acquire_date"] is not None
                else None
            ),
            quantity=float(lot["quantity"]),
            unit_cost_usd=float(lot["unit_cost"]),
            cost_basis_usd=float(lot["cost_basis"]),
            holding_days=int(lot["holding_days"]),
            term=str(lot["term"]),
            missing_basis=lot["acquire_date"] is None,
        )
        for lot in lots_data
    ]

    summary = ForecastSummaryResource(
        coin=coin,
        wallet_id=wallet,
        quantity=float(quantity),
        sale_price_usd=float(sale_price_usd),
        total_cost_basis_usd=float(summary_data.get("total_cost_basis", 0.0)),
        total_proceeds_usd=float(summary_data.get("total_proceeds", quantity * sale_price_usd)),
        short_term_quantity=float(summary_data.get("short_term_quantity", 0.0)),
        long_term_quantity=float(summary_data.get("long_term_quantity", 0.0)),
        missing_basis_quantity=float(summary_data.get("missing_basis_quantity", 0.0)),
    )

    return ForecastResponse(
        summary=summary,
        current_balance=current_balance,
        lots=lots,
        warnings=warnings,
    )


def serialize_1099b_csv(report: GainsReportResponse) -> str:
    """Serialize gains lots to TaxAct-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "Description",
            "Date Acquired",
            "Date Sold",
            "Proceeds",
            "Cost Basis",
            "Adjustment Code",
            "Adjustment Amount",
            "Wash Sale Loss",
            "Form",
            "Term",
        ],
    )
    writer.writeheader()
    for lot in report.lots:
        writer.writerow(
            {
                "Description": lot.description,
                "Date Acquired": lot.date_acquired,
                "Date Sold": lot.date_sold,
                "Proceeds": f"{lot.proceeds_usd:.2f}",
                "Cost Basis": f"{lot.cost_basis_usd:.2f}",
                "Adjustment Code": "",
                "Adjustment Amount": "",
                "Wash Sale Loss": "",
                "Form": "8949",
                "Term": lot.term,
            }
        )
    return output.getvalue()


def serialize_worksheet_csv(report: GainsReportResponse) -> str:
    """Serialize lot worksheet details to CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "Sale Date",
            "Sale Quantity",
            "Proceeds",
            "Acquire Date",
            "Lot Quantity",
            "Unit Cost Basis",
            "Total Cost Basis",
            "Holding Days",
            "Term",
            "Gain/Loss",
        ],
    )
    writer.writeheader()
    for row in report.worksheet:
        writer.writerow(
            {
                "Sale Date": row.sale_date,
                "Sale Quantity": f"{row.sale_quantity:.8f}",
                "Proceeds": f"{row.proceeds_usd:.2f}",
                "Acquire Date": row.acquire_date,
                "Lot Quantity": f"{row.lot_quantity:.8f}",
                "Unit Cost Basis": f"{row.unit_cost_basis_usd:.2f}",
                "Total Cost Basis": f"{row.total_cost_basis_usd:.2f}",
                "Holding Days": row.holding_days if row.holding_days is not None else "UNKNOWN",
                "Term": row.term,
                "Gain/Loss": f"{row.gain_loss_usd:.2f}",
            }
        )
    return output.getvalue()


def policy_http_error(exc: TaxPolicyError) -> HTTPException:
    """Convert a tax policy violation into an HTTP 400."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )

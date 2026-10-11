"""Tax reporting service helpers for web routes."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from fastapi import HTTPException, status

from bitcoinAccounts import BitcoinAccounts
from imports.base import is_fiat
from web.models import (
    ForecastLotResource,
    ForecastResponse,
    ForecastSummaryResource,
    GainsLotResource,
    GainsReportResponse,
    GainsSummaryResource,
    GainsWorksheetEntryResource,
    TaxHoldingsResponse,
    TaxHoldingWalletResource,
    TaxPolicyResource,
    TaxPolicyWarningResource,
    TaxSalesIndexCoinResource,
    TaxSalesIndexResponse,
    TaxYearOverviewResponse,
    TaxYearTotalsResource,
    TaxYearWalletSummaryResource,
)

IRS_WALLET_RULES_DOC = "docs/IRS_2025_WALLET_RULES.md"
WALLET_SEPARATION_FROM_TAX_YEAR = 2025
_DUST = 1e-8


class TaxPolicyError(ValueError):
    """Raised when a tax workflow violates configured operator policy."""


def _tax_policy_warnings(
    tax_year: int | None = None,
    wallet: str | None = None,
    *,
    strict_wallet_requirement: bool = False,
) -> list[TaxPolicyWarningResource]:
    warnings: list[TaxPolicyWarningResource] = []

    if tax_year is not None and tax_year >= WALLET_SEPARATION_FROM_TAX_YEAR and wallet is None:
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
    elif tax_year is not None and tax_year < WALLET_SEPARATION_FROM_TAX_YEAR and wallet is None:
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
        wallet_separation_required_from_tax_year=WALLET_SEPARATION_FROM_TAX_YEAR,
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


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def build_sales_index(accounts: BitcoinAccounts) -> TaxSalesIndexResponse:
    """List every non-fiat coin with sales and the tax years they fall in."""
    years_by_coin: dict[str, set[int]] = defaultdict(set)
    for row in accounts.trade_query.get_disposals():
        coin = str(row["coin"])
        if is_fiat(coin):
            continue
        years_by_coin[coin].add(_as_datetime(row["createddate"]).year)

    coins = [
        TaxSalesIndexCoinResource(coin=coin, years=sorted(years, reverse=True))
        for coin, years in sorted(years_by_coin.items())
    ]
    return TaxSalesIndexResponse(
        current_year=datetime.now(timezone.utc).year,
        coins=coins,
    )


def _summarize_report(report: GainsReportResponse) -> dict[str, float | int]:
    return {
        "lot_count": report.summary.lot_count,
        "proceeds_usd": report.summary.proceeds_usd,
        "cost_basis_usd": report.summary.cost_basis_usd,
        "gain_loss_usd": report.summary.gain_loss_usd,
        "short_term_gain_usd": sum(
            row.gain_loss_usd for row in report.worksheet if row.term == "Short"
        ),
        "long_term_gain_usd": sum(
            row.gain_loss_usd for row in report.worksheet if row.term == "Long"
        ),
        "missing_basis_quantity": sum(
            row.lot_quantity for row in report.worksheet if row.missing_basis
        ),
    }


def build_tax_year_overview(
    accounts: BitcoinAccounts,
    *,
    tax_year: int,
    coin: str = "BTC",
) -> TaxYearOverviewResponse:
    """Find every wallet with sales in a tax year and summarize its gains.

    Each wallet is run through wallet-scoped FIFO. For 2025+ the year totals are
    the sum of those wallet reports; for earlier years the totals come from the
    historical global FIFO view.
    """
    wallet_required = tax_year >= WALLET_SEPARATION_FROM_TAX_YEAR

    sales_by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accounts.trade_query.get_disposals(coin=coin):
        if _as_datetime(row["createddate"]).year == tax_year:
            sales_by_wallet[str(row["exchange"])].append(row)

    spend_count = sum(
        1
        for row in accounts.trade_query.get_disposals(coin=coin, trans_type="Spend")
        if _as_datetime(row["createddate"]).year == tax_year
    )

    wallets: list[TaxYearWalletSummaryResource] = []
    for wallet_id in sorted(sales_by_wallet):
        rows = sales_by_wallet[wallet_id]
        sale_dates = [_as_datetime(row["createddate"]) for row in rows]
        report = build_gains_report(accounts, tax_year=tax_year, coin=coin, wallet=wallet_id)
        wallets.append(
            TaxYearWalletSummaryResource(
                wallet_id=wallet_id,
                sale_count=len(rows),
                quantity_sold=sum(float(row["quantity"]) for row in rows),
                first_sale_date=min(sale_dates).strftime("%Y-%m-%d"),
                last_sale_date=max(sale_dates).strftime("%Y-%m-%d"),
                **_summarize_report(report),
            )
        )

    if wallet_required or not wallets:
        totals_method = "wallet_fifo"
        gains_totals: dict[str, float] = {
            key: sum(float(getattr(w, key)) for w in wallets)
            for key in (
                "proceeds_usd",
                "cost_basis_usd",
                "gain_loss_usd",
                "short_term_gain_usd",
                "long_term_gain_usd",
                "missing_basis_quantity",
            )
        }
    else:
        totals_method = "global_fifo"
        global_summary = _summarize_report(
            build_gains_report(accounts, tax_year=tax_year, coin=coin, wallet=None)
        )
        global_summary.pop("lot_count")
        gains_totals = {key: float(value) for key, value in global_summary.items()}

    totals = TaxYearTotalsResource(
        sale_count=sum(w.sale_count for w in wallets),
        wallet_count=len(wallets),
        quantity_sold=sum(w.quantity_sold for w in wallets),
        **gains_totals,
    )

    warnings: list[TaxPolicyWarningResource] = []
    if wallets and not wallet_required:
        warnings.append(
            TaxPolicyWarningResource(
                code="global_fifo_historical",
                severity="info",
                message=(
                    f"Totals for {tax_year} use historical global FIFO. Per-wallet rows "
                    "use wallet-scoped FIFO, so they may not add up to the totals."
                ),
                reference_doc=IRS_WALLET_RULES_DOC,
            )
        )
    if totals.missing_basis_quantity > _DUST:
        warnings.append(
            TaxPolicyWarningResource(
                code="missing_basis",
                severity="warning",
                message=(
                    f"{totals.missing_basis_quantity:.8f} {coin} sold in {tax_year} has no "
                    "matching acquisition lot in its wallet and is reported with $0 basis. "
                    "Record the original purchase or transfer-in basis before filing."
                ),
            )
        )
    if spend_count:
        warnings.append(
            TaxPolicyWarningResource(
                code="spends_not_included",
                severity="warning",
                message=(
                    f"{spend_count} Spend transaction(s) of {coin} in {tax_year} are "
                    "disposals too, but are not included in these gains figures."
                ),
            )
        )

    if wallets:
        noun = "sale" if totals.sale_count == 1 else "sales"
        where = "wallet" if len(wallets) == 1 else "wallets"
        message = (
            f"{totals.sale_count} {noun} of {coin} across {len(wallets)} {where} in "
            f"tax year {tax_year}. Sales are reportable on Form 8949 even at a loss."
        )
    else:
        message = f"No sales found for tax year {tax_year} with digital asset {coin}."

    return TaxYearOverviewResponse(
        tax_year=tax_year,
        coin=coin,
        wallet_separation_required=wallet_required,
        totals_method=totals_method,
        has_sales=bool(wallets),
        message=message,
        totals=totals,
        wallets=wallets,
        spend_count=spend_count,
        warnings=warnings,
    )


def build_holdings(accounts: BitcoinAccounts, *, coin: str = "BTC") -> TaxHoldingsResponse:
    """List wallets with a positive balance of a coin, largest first."""
    balances = accounts.get_wallet_balance(coin, None)
    wallets = [
        TaxHoldingWalletResource(wallet_id=str(wallet_id), balance=float(balance))
        for wallet_id, balance in balances.items()
        if float(balance) > _DUST
    ]
    wallets.sort(key=lambda w: (-w.balance, w.wallet_id))
    return TaxHoldingsResponse(
        coin=coin,
        total_balance=sum(w.balance for w in wallets),
        wallets=wallets,
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

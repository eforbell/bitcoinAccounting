"""Authenticated tax reporting routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from bitcoinAccounts import BitcoinAccounts
from db import DatabaseBackend
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts, get_request_backend
from web.models import (
    ForecastResponse,
    GainsReportResponse,
    TaxHistoryEntryResource,
    TaxHoldingsResponse,
    TaxPolicyResource,
    TaxSalesIndexResponse,
    TaxYearOverviewResponse,
)
from web.services.tax_reporting import (
    TaxPolicyError,
    build_forecast_response,
    build_gains_report,
    build_holdings,
    build_sales_index,
    build_tax_year_overview,
    get_tax_policy,
    policy_http_error,
    serialize_1099b_csv,
    serialize_worksheet_csv,
)
from web.services.tax_state import list_tax_history, record_tax_history

router = APIRouter(
    prefix="/api/tax",
    tags=["tax"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("/policy", response_model=TaxPolicyResource)
def tax_policy() -> TaxPolicyResource:
    """Return static tax policy metadata."""
    return get_tax_policy()


@router.get("/sales-index", response_model=TaxSalesIndexResponse)
def sales_index(
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TaxSalesIndexResponse:
    """List coins with sales and the tax years those sales fall in."""
    return build_sales_index(accounts)


@router.get("/overview", response_model=TaxYearOverviewResponse)
def tax_year_overview(
    tax_year: int = Query(..., ge=2009),
    coin: str = Query("BTC", min_length=1),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TaxYearOverviewResponse:
    """Summarize realized gains for every wallet with sales in a tax year."""
    return build_tax_year_overview(accounts, tax_year=tax_year, coin=coin)


@router.get("/holdings", response_model=TaxHoldingsResponse)
def holdings(
    coin: str = Query("BTC", min_length=1),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TaxHoldingsResponse:
    """List wallets with a positive balance, for choosing a forecast source."""
    return build_holdings(accounts, coin=coin)


@router.get("/gains", response_model=GainsReportResponse)
def gains_report(
    tax_year: int = Query(..., ge=2009),
    coin: str = Query("BTC", min_length=1),
    wallet: str | None = Query(None),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> GainsReportResponse:
    """Return gains summary and worksheet rows for a tax year."""
    try:
        report = build_gains_report(
            accounts,
            tax_year=tax_year,
            coin=coin,
            wallet=wallet,
            strict_wallet_requirement=False,
        )
        record_tax_history(
            accounts.backend,
            action="gains_report",
            coin=coin,
            tax_year=tax_year,
            wallet_id=wallet,
            artifact_type="json",
        )
        return report
    except TaxPolicyError as exc:
        raise policy_http_error(exc) from exc


@router.get("/1099b/preview", response_model=GainsReportResponse)
def preview_1099b(
    tax_year: int = Query(..., ge=2009),
    coin: str = Query("BTC", min_length=1),
    wallet: str | None = Query(None),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> GainsReportResponse:
    """Return a wallet-aware 1099-B preview payload."""
    try:
        report = build_gains_report(
            accounts,
            tax_year=tax_year,
            coin=coin,
            wallet=wallet,
            strict_wallet_requirement=True,
        )
        record_tax_history(
            accounts.backend,
            action="preview_1099b",
            coin=coin,
            tax_year=tax_year,
            wallet_id=wallet,
            artifact_type="json",
        )
        return report
    except TaxPolicyError as exc:
        raise policy_http_error(exc) from exc


@router.get("/1099b/export")
def export_1099b(
    tax_year: int = Query(..., ge=2009),
    coin: str = Query("BTC", min_length=1),
    wallet: str | None = Query(None),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> Response:
    """Export 1099-B lot rows as CSV."""
    try:
        report = build_gains_report(
            accounts,
            tax_year=tax_year,
            coin=coin,
            wallet=wallet,
            strict_wallet_requirement=True,
        )
    except TaxPolicyError as exc:
        raise policy_http_error(exc) from exc

    record_tax_history(
        accounts.backend,
        action="export_1099b",
        coin=coin,
        tax_year=tax_year,
        wallet_id=wallet,
        artifact_type="csv",
    )
    filename = f"1099b_{tax_year}"
    if wallet:
        filename = f"{filename}_{wallet}"
    return Response(
        content=serialize_1099b_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


@router.get("/1099b/worksheet")
def export_worksheet(
    tax_year: int = Query(..., ge=2009),
    coin: str = Query("BTC", min_length=1),
    wallet: str | None = Query(None),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> Response:
    """Export lot worksheet rows as CSV."""
    try:
        report = build_gains_report(
            accounts,
            tax_year=tax_year,
            coin=coin,
            wallet=wallet,
            strict_wallet_requirement=True,
        )
    except TaxPolicyError as exc:
        raise policy_http_error(exc) from exc

    record_tax_history(
        accounts.backend,
        action="export_worksheet",
        coin=coin,
        tax_year=tax_year,
        wallet_id=wallet,
        artifact_type="csv",
    )
    filename = f"1099b_{tax_year}_worksheet"
    if wallet:
        filename = f"{filename}_{wallet}"
    return Response(
        content=serialize_worksheet_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


@router.get("/forecast", response_model=ForecastResponse)
def forecast(
    coin: str = Query("BTC", min_length=1),
    quantity: float = Query(..., gt=0),
    sale_price_usd: float = Query(..., gt=0),
    wallet: str | None = Query(None),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> ForecastResponse:
    """Return a hypothetical FIFO sale forecast."""
    response = build_forecast_response(
        accounts,
        coin=coin,
        quantity=quantity,
        sale_price_usd=sale_price_usd,
        wallet=wallet,
    )
    record_tax_history(
        accounts.backend,
        action="forecast",
        coin=coin,
        wallet_id=wallet,
        quantity=quantity,
        sale_price_usd=sale_price_usd,
        artifact_type="json",
    )
    return response


@router.get("/history", response_model=list[TaxHistoryEntryResource])
def history(
    limit: int = Query(20, ge=1, le=100),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> list[TaxHistoryEntryResource]:
    """List recent tax workflow runs."""
    return list_tax_history(backend, limit=limit)

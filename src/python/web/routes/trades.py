"""Authenticated trades and liquidity routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from bitcoinAccounts import BitcoinAccounts
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts
from web.models import ExchangeListResponse, LiquidityResponse, TradesResponse
from web.services.trades import build_liquidity_response, build_trades_response, get_trade_exchanges

router = APIRouter(
    prefix="/api/trades",
    tags=["trades"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("", response_model=TradesResponse)
def trades(
    exchange: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TradesResponse:
    """Return paginated trade history with cost basis."""
    return build_trades_response(
        accounts,
        exchange=exchange,
        page=page,
        per_page=per_page,
    )


@router.get("/exchanges", response_model=ExchangeListResponse)
def exchanges(
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> ExchangeListResponse:
    """Return sorted list of all exchanges with trade activity."""
    return ExchangeListResponse(exchanges=get_trade_exchanges(accounts))


@router.get("/liquidity", response_model=LiquidityResponse)
def liquidity(
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> LiquidityResponse:
    """Return per-exchange liquidity summary with cost basis metrics."""
    return build_liquidity_response(accounts)

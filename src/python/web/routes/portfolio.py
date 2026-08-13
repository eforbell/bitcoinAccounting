"""Authenticated portfolio/dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from bitcoinAccounts import BitcoinAccounts
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts
from web.models import PortfolioDashboardResponse, WalletDetailResponse
from web.services.portfolio import build_portfolio_dashboard, build_wallet_detail

router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("/dashboard", response_model=PortfolioDashboardResponse)
def dashboard(
    coin: str = Query("BTC", min_length=1),
    recent_limit: int = Query(5, ge=1, le=20),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> PortfolioDashboardResponse:
    """Return the dashboard/portfolio home payload."""
    return build_portfolio_dashboard(
        accounts,
        coin=coin,
        recent_limit=recent_limit,
    )


@router.get("/wallet/{wallet_id:path}", response_model=WalletDetailResponse)
def wallet_detail(
    wallet_id: str,
    coin: str = Query("BTC", min_length=1),
    recent_limit: int = Query(20, ge=1, le=100),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletDetailResponse:
    """Return detail for a single wallet with recent activity."""
    result = build_wallet_detail(
        accounts, wallet_id=wallet_id, coin=coin, recent_limit=recent_limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return result

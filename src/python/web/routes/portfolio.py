"""Authenticated portfolio/dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from bitcoinAccounts import BitcoinAccounts
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts
from web.models import PortfolioDashboardResponse
from web.services.portfolio import build_portfolio_dashboard

router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("/dashboard", response_model=PortfolioDashboardResponse)
def dashboard(
    coin: str = Query("BTC", min_length=1),
    include_inactive: bool = Query(False),
    recent_limit: int = Query(5, ge=1, le=20),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> PortfolioDashboardResponse:
    """Return the dashboard/portfolio home payload."""
    return build_portfolio_dashboard(
        accounts,
        coin=coin,
        include_inactive=include_inactive,
        recent_limit=recent_limit,
    )

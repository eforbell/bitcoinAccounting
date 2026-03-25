"""Trades and liquidity read models for the web UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bitcoinAccounts import BitcoinAccounts
from web.models import (
    CostBasisSummaryResource,
    ExchangeLiquidityResource,
    LiquidityResponse,
    TradeResource,
    TradesResponse,
)


def build_trades_response(
    accounts: BitcoinAccounts,
    exchange: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> TradesResponse:
    """Build a paginated trade history response with cost basis."""
    all_trades = accounts.trade_query.get_trade_cost("BTC", "USD")

    # Optionally filter by exchange
    if exchange:
        all_trades = [t for t in all_trades if t.get("exchange") == exchange]

    # Sort newest-first
    all_trades.reverse()
    total = len(all_trades)

    # Paginate
    start = (page - 1) * per_page
    page_trades = all_trades[start : start + per_page]

    trades = [
        TradeResource(
            date=t["date"].strftime("%Y-%m-%d") if isinstance(t["date"], datetime) else str(t["date"])[:10],
            trade_type="Buy" if t.get("quantity", 0) > 0 else "Sell",
            quantity=abs(t.get("quantity", 0)),
            trade_currency=t.get("trade_curr", "USD"),
            unit_cost_usd=t.get("unit_cost"),
            total_cost_usd=t.get("total_cost"),
            exchange=t.get("exchange"),
        )
        for t in page_trades
    ]

    return TradesResponse(
        trades=trades,
        page=page,
        per_page=per_page,
        total=total,
    )


def build_liquidity_response(accounts: BitcoinAccounts) -> LiquidityResponse:
    """Build exchange liquidity summary with cost basis metrics."""
    all_trades = accounts.trade_query.get_trade_cost("BTC", "USD")

    # Group purchases by exchange
    exchange_data: dict[str, dict[str, float]] = {}
    for t in all_trades:
        if t.get("quantity", 0) <= 0:
            continue

        exchange = t.get("exchange", "Unknown")
        if exchange not in exchange_data:
            exchange_data[exchange] = {"purchased": 0.0, "usd_spent": 0.0}

        exchange_data[exchange]["purchased"] += t["quantity"]
        if t.get("total_cost") is not None:
            exchange_data[exchange]["usd_spent"] += t["total_cost"]

    # Build per-exchange rows with current balances
    exchange_rows: list[ExchangeLiquidityResource] = []
    total_purchased = 0.0
    total_balance = 0.0
    total_usd_spent = 0.0

    for exchange, data in exchange_data.items():
        purchased = data["purchased"]
        usd_spent = data["usd_spent"]

        if purchased > 0:
            balance = accounts.get_wallet_balance("BTC", exchange)
            avg_cost = usd_spent / purchased

            exchange_rows.append(
                ExchangeLiquidityResource(
                    exchange=exchange,
                    total_purchased=purchased,
                    current_balance=balance,
                    avg_cost_usd=avg_cost,
                )
            )

            total_purchased += purchased
            total_balance += balance
            total_usd_spent += usd_spent

    # Sort by total purchased descending
    exchange_rows.sort(key=lambda x: x.total_purchased, reverse=True)

    # Overall summary
    overall_balance = accounts.get_balance("BTC")
    in_cold_storage = overall_balance - total_balance
    avg_cost_basis = total_usd_spent / total_purchased if total_purchased > 0 else None

    summary = CostBasisSummaryResource(
        total_purchased=total_purchased,
        total_usd_spent=total_usd_spent,
        avg_cost_basis_usd=avg_cost_basis,
        still_at_exchanges=total_balance,
        in_cold_storage=in_cold_storage,
        total_holdings=overall_balance,
    )

    return LiquidityResponse(
        exchanges=exchange_rows,
        summary=summary,
    )

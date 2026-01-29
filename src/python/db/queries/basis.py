"""
Cost basis calculation functions.

This module provides cost basis calculations, particularly the weighted
average purchase price for a given coin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .trades import TradeQuery


class BasisCalculator:
    """Calculates cost basis information for cryptocurrency trades."""

    def __init__(self, trade_query: TradeQuery) -> None:
        """
        Initialize the basis calculator.

        Args:
            trade_query: TradeQuery instance for retrieving trade cost data
        """
        self.trade_query = trade_query

    def get_avg_purchase_price(
        self, coin: str, cost_currency: str = "USD"
    ) -> float | None:
        """
        Calculate the weighted average purchase price for a coin.

        This calculates the average cost basis across all purchase trades,
        weighted by quantity. Only purchases (quantity > 0) are included.
        Trades with missing price data (unit_cost = None) are excluded.

        Args:
            coin: The coin symbol to calculate average price for
            cost_currency: The currency to express the price in (default: USD)

        Returns:
            Weighted average purchase price, or None if:
            - No purchases exist for this coin
            - All purchases have missing price data
        """
        # Get all trade costs for this coin
        trade_costs = self.trade_query.get_trade_cost(coin, cost_currency)

        # Filter to purchases only (quantity > 0) and exclude trades without price data
        purchases = [
            trade
            for trade in trade_costs
            if trade["quantity"] > 0 and trade["unit_cost"] is not None
        ]

        # Return None if no valid purchases
        if not purchases:
            return None

        # Calculate weighted average: sum(unit_cost * quantity) / sum(quantity)
        total_cost: float = sum(trade["unit_cost"] * trade["quantity"] for trade in purchases)
        total_quantity: float = sum(trade["quantity"] for trade in purchases)

        # Avoid division by zero (should not happen given our filters, but be safe)
        if total_quantity == 0:
            return None

        avg_price: float = total_cost / total_quantity
        return avg_price

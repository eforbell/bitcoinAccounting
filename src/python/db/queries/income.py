"""
Income tracking functions for interest and dividend income.

This module provides queries for retrieving interest income and dividend
transactions with cost basis calculations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend
    from .price import PriceLookup


class IncomeQuery:
    """Queries for income-related transactions (interest, dividends)."""

    def __init__(
        self, backend: DatabaseBackend, price_lookup: PriceLookup | None = None
    ) -> None:
        """
        Initialize the income query handler.

        Args:
            backend: DatabaseBackend instance for executing queries
            price_lookup: Optional PriceLookup instance for price conversions.
                         If None, a new instance will be created.
        """
        self.backend = backend
        if price_lookup is None:
            from .price import PriceLookup

            price_lookup = PriceLookup(backend)
        self.price_lookup = price_lookup

    def get_interest_income(
        self, coin: str, cost_currency: str = "USD"
    ) -> list[dict[str, Any]]:
        """
        Get all interest income transactions for a coin with cost basis.

        Returns interest income transactions with their cost basis calculated
        in the specified currency. Uses price lookups to convert to the cost
        currency.

        Args:
            coin: The coin symbol to get interest income for
            cost_currency: The currency to express costs in (default: USD)

        Returns:
            List of dictionaries with keys:
            - date: Transaction timestamp (ISO 8601 string)
            - to_curr: The coin received (same as coin parameter)
            - to_quantity: Amount of coin received
            - cost_curr: The cost currency (same as cost_currency parameter)
            - unit_cost: Price per unit in cost currency, or None if unavailable
            - total_cost: Total cost (to_quantity * unit_cost), or None if unavailable
            - cost_curr_quote_date: Date of price quote used, or None if unavailable

            Returns empty list [] if no interest income transactions exist.
        """
        # Query for all Interest Income transactions for this coin
        query = """
            SELECT createddate, buy, exchange
            FROM ledger
            WHERE trans_type = 'Interest Income' AND buy_curr = :coin
            ORDER BY createddate
        """

        rows = self.backend.execute(query, {"coin": coin})

        # Build result with price lookups
        results: list[dict[str, Any]] = []
        for row in rows:
            date = row["createddate"]
            to_quantity = row["buy"]
            exchange = row["exchange"]

            # Lookup price for this coin in the cost currency
            unit_cost = self.price_lookup.get_price(coin, cost_currency, date)
            cost_curr_quote_date = self.price_lookup.get_price_date(
                coin, cost_currency, date
            )

            # Calculate total cost (or None if no price)
            if unit_cost is not None:
                total_cost = to_quantity * unit_cost
            else:
                total_cost = None

            results.append(
                {
                    "date": date,
                    "to_curr": coin,
                    "to_quantity": to_quantity,
                    "cost_curr": cost_currency,
                    "unit_cost": unit_cost,
                    "total_cost": total_cost,
                    "cost_curr_quote_date": cost_curr_quote_date,
                    "exchange": exchange,
                }
            )

        return results

    def get_dividend_cost(
        self, coin: str, cost_currency: str = "USD"
    ) -> list[dict[str, Any]]:
        """
        Get all dividend transactions for a coin with cost basis.

        This method is functionally identical to get_interest_income() and is
        kept as a separate method for API compatibility with the PostgreSQL
        function interface.

        Args:
            coin: The coin symbol to get dividend income for
            cost_currency: The currency to express costs in (default: USD)

        Returns:
            List of dictionaries with same structure as get_interest_income().
            Returns empty list [] if no dividend transactions exist.
        """
        # In this implementation, dividends and interest income are both
        # recorded as 'Interest Income' trans_type, so this delegates to
        # get_interest_income()
        return self.get_interest_income(coin, cost_currency)

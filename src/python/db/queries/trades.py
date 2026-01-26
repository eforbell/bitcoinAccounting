"""Trade query operations for cryptocurrency accounting.

This module provides the TradeQuery class for retrieving and analyzing
trade transactions from the ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend


class TradeQuery:
    """Query and analyze trade transactions.

    This class provides methods to retrieve trade history with proper
    perspective (buy vs sell) relative to the coin being queried.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize the trade query handler.

        Args:
            backend: Database backend to use for queries
        """
        self.backend = backend

    def get_trades(self, coin: str) -> list[dict[str, Any]]:
        """Get all trades involving a specific coin.

        Returns trade history with amounts signed relative to the coin:
        - Positive to_quantity: coin was acquired (buy)
        - Negative to_quantity: coin was sold (sell)

        Each trade includes the date, currencies involved, quantities, and
        calculated price (counter_amount / coin_amount).

        Args:
            coin: The currency code to get trades for (e.g., 'BTC', 'ETH')

        Returns:
            List of trade dictionaries ordered by date (ascending).
            Each dict contains:
            - date: Transaction timestamp (ISO 8601 string)
            - to_curr: The coin being queried
            - to_quantity: Amount of coin (positive=buy, negative=sell)
            - price: Exchange rate (counter_amount / coin_amount)
            - from_curr: The counter currency
            - from_quantity: Amount of counter currency

            Returns empty list [] if no trades found.
        """
        query = """
            SELECT
                createddate AS date,
                CASE
                    WHEN buy_curr = :coin THEN buy_curr
                    WHEN sell_curr = :coin THEN sell_curr
                END AS to_curr,
                CASE
                    WHEN buy_curr = :coin THEN buy
                    WHEN sell_curr = :coin THEN -sell
                END AS to_quantity,
                CASE
                    WHEN buy_curr = :coin THEN sell / buy
                    WHEN sell_curr = :coin THEN buy / sell
                END AS price,
                CASE
                    WHEN buy_curr = :coin THEN sell_curr
                    WHEN sell_curr = :coin THEN buy_curr
                END AS from_curr,
                CASE
                    WHEN buy_curr = :coin THEN sell
                    WHEN sell_curr = :coin THEN buy
                END AS from_quantity
            FROM ledger
            WHERE trans_type = 'Trade'
              AND (buy_curr = :coin OR sell_curr = :coin)
            ORDER BY createddate ASC
        """

        results = self.backend.execute(query, {"coin": coin})
        return [dict(row) for row in results]

"""Trade query operations for cryptocurrency accounting.

This module provides the TradeQuery class for retrieving and analyzing
trade transactions from the ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend
    from .price import PriceLookup


class TradeQuery:
    """Query and analyze trade transactions.

    This class provides methods to retrieve trade history with proper
    perspective (buy vs sell) relative to the coin being queried.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        price_lookup: PriceLookup | None = None
    ) -> None:
        """Initialize the trade query handler.

        Args:
            backend: Database backend to use for queries
            price_lookup: Optional PriceLookup instance for cost calculations.
                         If None, a new instance will be created.
        """
        self.backend = backend
        if price_lookup is None:
            from .price import PriceLookup
            price_lookup = PriceLookup(backend)
        self.price_lookup = price_lookup

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
            - exchange: Wallet/exchange name

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
                END AS from_quantity,
                exchange
            FROM ledger
            WHERE trans_type = 'Trade'
              AND (buy_curr = :coin OR sell_curr = :coin)
              AND (deleted = 0 OR deleted IS NULL)
            ORDER BY createddate ASC
        """

        results = self.backend.execute(query, {"coin": coin})
        return [dict(row) for row in results]

    def get_trade_cost(
        self,
        coin: str,
        cost_currency: str = 'USD'
    ) -> list[dict[str, Any]]:
        """Get trade history with cost basis information.

        For each trade, calculates the cost in a specified currency.
        Handles cross-currency trades by looking up prices.

        Args:
            coin: The currency code to get trades for (e.g., 'BTC', 'ETH')
            cost_currency: Currency to express costs in (default: 'USD')

        Returns:
            List of trade dictionaries with cost information ordered by date.
            Each dict contains:
            - date: Transaction timestamp (ISO 8601 string)
            - curr: The coin being queried
            - quantity: Amount of coin (positive=buy, negative=sell)
            - trade_curr: The counter currency
            - trade_quantity: Amount of counter currency
            - cost_curr: The currency costs are expressed in
            - unit_cost: Cost per unit of coin in cost_currency (None if price unavailable)
            - total_cost: Total cost of trade in cost_currency (None if price unavailable)
            - cost_curr_quote_date: Timestamp of price used for conversion (trade date if direct)
            - exchange: Wallet/exchange name where trade occurred

            Returns empty list [] if no trades found.
        """
        trades = self.get_trades(coin)
        result = []

        for trade in trades:
            trade_date = trade['date']
            trade_curr = trade['from_curr']
            trade_quantity = trade['from_quantity']
            quantity = trade['to_quantity']

            # Determine if we need price conversion
            if trade_curr == cost_currency:
                # Direct trade in cost currency - use trade price directly
                unit_cost = trade['price']
                total_cost = unit_cost * abs(quantity)
                cost_curr_quote_date = trade_date
            else:
                # Need to convert from trade_curr to cost_currency
                price = self.price_lookup.get_price(
                    trade_curr,
                    cost_currency,
                    trade_date
                )

                if price is None:
                    # No price available for conversion
                    unit_cost = None
                    total_cost = None
                    cost_curr_quote_date = None
                else:
                    # Calculate cost using the looked-up price
                    unit_cost = trade['price'] * price
                    total_cost = unit_cost * abs(quantity)
                    cost_curr_quote_date = self.price_lookup.get_price_date(
                        trade_curr,
                        cost_currency,
                        trade_date
                    )

            result.append({
                'date': trade_date,
                'curr': coin,
                'quantity': quantity,
                'trade_curr': trade_curr,
                'trade_quantity': trade_quantity,
                'cost_curr': cost_currency,
                'unit_cost': unit_cost,
                'total_cost': total_cost,
                'cost_curr_quote_date': cost_curr_quote_date,
                'exchange': trade.get('exchange')
            })

        return result

    def get_sales(
        self,
        coin: str,
        through_date: str | None = None,
        wallet: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all sales of a coin, optionally filtered by date and wallet.

        Args:
            coin: The currency code to get sales for (e.g., 'BTC', 'ETH')
            through_date: Optional ISO 8601 date to filter sales through (inclusive)
            wallet: Optional wallet/exchange name to filter by

        Returns:
            List of sale dictionaries ordered by date (ascending).
            Each dict contains:
            - createddate: Transaction timestamp
            - quantity: Amount sold (as positive number)
            - exchange: Wallet/exchange name
            - id: Transaction ID

            Returns empty list [] if no sales found.
        """
        query = """
            SELECT createddate, sell as quantity, exchange, id
            FROM ledger
            WHERE sell_curr = :coin
                AND trans_type = 'Trade'
                AND sell > 0
                AND (deleted = 0 OR deleted IS NULL)
        """

        params: dict[str, Any] = {"coin": coin}

        if through_date is not None:
            query += " AND createddate <= :through_date"
            params["through_date"] = through_date

        if wallet is not None:
            query += " AND exchange = :wallet"
            params["wallet"] = wallet

        query += " ORDER BY createddate ASC"

        results = self.backend.execute(query, params)
        return [dict(row) for row in results]

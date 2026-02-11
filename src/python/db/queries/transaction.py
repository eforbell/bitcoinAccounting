"""Transaction query operations for cryptocurrency accounting.

This module provides the TransactionQuery class for retrieving and filtering
transactions from the ledger table.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend


class TransactionQuery:
    """Query and filter ledger transactions.

    This class provides methods to retrieve transactions with optional filtering
    by coin, wallet, and date range.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize the transaction query handler.

        Args:
            backend: Database backend to use for queries
        """
        self.backend = backend

    def get_transactions(
        self,
        coin: str | None = None,
        wallet: str | list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Get all transactions with optional filtering.

        Args:
            coin: Filter by currency code (e.g., 'BTC', 'ETH')
            wallet: Filter by wallet/exchange (single string or list of strings)
            start_date: Start date (YYYY-MM-DD format or date object)
            end_date: End date (YYYY-MM-DD format or date object)

        Returns:
            tuple: (column_names, transactions)
                - column_names: List of column names
                - transactions: List of transaction dictionaries
        """
        base_query = '''select l.createddate "Date", l.trans_type "Type", l.buy "Buy", l.buy_curr "Buy Cur.", l.sell "Sell", l.sell_curr "Sell Cur.", l.fee "Fee", l.fee_curr "Fee Cur.", l.exchange "Exchange", l."group" "Group", l."comment" "Comment" from ledger l'''

        # Build WHERE clause with filters
        where_clauses = []
        params = {}

        if coin is not None:
            where_clauses.append("(l.buy_curr = :coin OR l.sell_curr = :coin OR l.fee_curr = :coin)")
            params['coin'] = coin

        if wallet is not None:
            # Support both single wallet string and list of wallets
            if isinstance(wallet, str):
                where_clauses.append("l.exchange = :wallet")
                params['wallet'] = wallet
            elif isinstance(wallet, (list, tuple)):
                # Build OR conditions for multiple wallets
                wallet_conditions = []
                for i, w in enumerate(wallet):
                    wallet_conditions.append(f"l.exchange = :wallet{i}")
                    params[f'wallet{i}'] = w
                where_clauses.append(f"({' OR '.join(wallet_conditions)})")
            else:
                raise ValueError(f"wallet must be string or list, not {type(wallet)}")

        if start_date is not None:
            where_clauses.append("l.createddate >= :start_date")
            params['start_date'] = start_date

        if end_date is not None:
            # Include the entire end date by adding 1 day in Python (database-agnostic)
            if isinstance(end_date, str):
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                end_date_obj = end_date
            next_day = end_date_obj + timedelta(days=1)
            where_clauses.append("l.createddate < :end_date_exclusive")
            params['end_date_exclusive'] = next_day.strftime('%Y-%m-%d')

        # Build final query
        if where_clauses:
            query = base_query + " WHERE " + " AND ".join(where_clauses) + " ORDER BY createddate ASC, l.id ASC"
        else:
            query = base_query + " ORDER BY createddate ASC, l.id ASC"

        rows = self.backend.execute(query, params) if params else self.backend.execute(query)

        transactions = [dict(row) for row in rows]
        colnames = list(transactions[0].keys()) if transactions else []
        return colnames, transactions

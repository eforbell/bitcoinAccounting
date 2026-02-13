"""Balance calculation queries for cryptocurrency accounting.

This module provides the BalanceCalculator class for computing coin balances
and transfer sums from the ledger table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backend import DatabaseBackend


class BalanceCalculator:
    """Calculate balances and transfer sums for cryptocurrency holdings.

    This class provides methods to compute:
    - Total balance: buys minus sells for a given coin
    - Transfer sum: sum of deposits and withdrawals only

    Both methods exclude stake transactions from purchases and return 0.0
    (not None) when no matching transactions exist.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize the balance calculator.

        Args:
            backend: Database backend to use for queries
        """
        self.backend = backend

    def get_balance(self, coin: str) -> float:
        """Calculate the total balance for a coin.

        Computes: SUM(buy where buy_curr=coin) - SUM(sell where sell_curr=coin)

        Stake transactions are excluded from the buy sum, matching the behavior
        of the PostgreSQL get_balance() function.

        Args:
            coin: The currency code to calculate balance for (e.g., 'BTC', 'ETH')

        Returns:
            The net balance as a float. Returns 0.0 if no transactions exist.
            Can be negative if more was sold than bought.
        """
        query = """
            SELECT
                COALESCE(
                    (SELECT SUM(buy) FROM ledger
                     WHERE buy_curr = :coin AND trans_type != 'Stake'
                     AND (deleted = 0 OR deleted IS NULL)),
                    0
                ) - COALESCE(
                    (SELECT SUM(sell) FROM ledger
                     WHERE sell_curr = :coin
                     AND (deleted = 0 OR deleted IS NULL)),
                    0
                ) AS balance
        """

        result = self.backend.execute_scalar(query, {"coin": coin})
        return float(result) if result is not None else 0.0

    def get_sum_of_all_transfers(self, coin: str) -> float:
        """Calculate the sum of all transfers (deposits and withdrawals) for a coin.

        Computes: SUM(buy where buy_curr=coin) - SUM(sell where sell_curr=coin)
        but only for transactions with trans_type IN ('Withdrawal', 'Deposit').

        Args:
            coin: The currency code to calculate transfer sum for

        Returns:
            The net transfer sum as a float. Returns 0.0 if no transfers exist.
            Can be negative if more was withdrawn than deposited.
        """
        query = """
            SELECT
                COALESCE(
                    (SELECT SUM(buy) FROM ledger
                     WHERE buy_curr = :coin
                     AND trans_type IN ('Withdrawal', 'Deposit')
                     AND (deleted = 0 OR deleted IS NULL)),
                    0
                ) - COALESCE(
                    (SELECT SUM(sell) FROM ledger
                     WHERE sell_curr = :coin
                     AND trans_type IN ('Withdrawal', 'Deposit')
                     AND (deleted = 0 OR deleted IS NULL)),
                    0
                ) AS transfer_sum
        """

        result = self.backend.execute_scalar(query, {"coin": coin})
        return float(result) if result is not None else 0.0

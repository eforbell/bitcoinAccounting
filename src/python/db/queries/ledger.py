"""Ledger transaction writing operations for cryptocurrency accounting.

This module provides the LedgerWriter class for recording transactions
into the ledger table.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backend import DatabaseBackend


class LedgerWriter:
    """Write transactions to the ledger table.

    This class provides methods to record different transaction types
    (deposits, withdrawals, trades, etc.) into the ledger.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize the ledger writer.

        Args:
            backend: Database backend to use for writes
        """
        self.backend = backend

    def deposit(
        self,
        createddate: str | datetime,
        buy: float,
        buy_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        commit: bool = True
    ) -> None:
        """Record a deposit transaction.

        Args:
            createddate: Transaction date (string or datetime)
            buy: Amount received
            buy_curr: Currency received (e.g., 'BTC', 'USD')
            exchange: Exchange/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, buy, buy_curr, exchange, "group", comment)
                   values (:createddate, 'Deposit', :buy, :buy_curr, :exchange, :group, :comment)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "buy": buy,
            "buy_curr": buy_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment
        })
        if commit:
            self.backend.commit()

    def withdraw(
        self,
        createddate: str | datetime,
        sell: float,
        sell_curr: str,
        fee: float,
        fee_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        commit: bool = True
    ) -> None:
        """Record a withdrawal transaction.

        Args:
            createddate: Transaction date (string or datetime)
            sell: Amount withdrawn
            sell_curr: Currency withdrawn (e.g., 'BTC', 'USD')
            fee: Withdrawal fee amount
            fee_curr: Fee currency
            exchange: Exchange/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, sell, sell_curr, fee, fee_curr, exchange, "group", comment)
                   values (:createddate, 'Withdrawal', :sell, :sell_curr, :fee, :fee_curr, :exchange, :group, :comment)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "sell": sell,
            "sell_curr": sell_curr,
            "fee": fee,
            "fee_curr": fee_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment
        })
        if commit:
            self.backend.commit()

    def spend(
        self,
        createddate: str | datetime,
        sell: float,
        sell_curr: str,
        fee: float,
        fee_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        commit: bool = True
    ) -> None:
        """Record a spend transaction.

        Args:
            createddate: Transaction date (string or datetime)
            sell: Amount spent
            sell_curr: Currency spent (e.g., 'BTC', 'USD')
            fee: Transaction fee amount
            fee_curr: Fee currency
            exchange: Exchange/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, sell, sell_curr, fee, fee_curr, exchange, "group", comment)
                   values (:createddate, 'Spend', :sell, :sell_curr, :fee, :fee_curr, :exchange, :group, :comment)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "sell": sell,
            "sell_curr": sell_curr,
            "fee": fee,
            "fee_curr": fee_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment
        })
        if commit:
            self.backend.commit()

    def trade(
        self,
        createddate: str | datetime,
        buy: float,
        buy_curr: str,
        sell: float,
        sell_curr: str,
        fee: float,
        fee_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        commit: bool = True
    ) -> None:
        """Record a trade transaction.

        Args:
            createddate: Transaction date (string or datetime)
            buy: Amount received
            buy_curr: Currency received (e.g., 'BTC')
            sell: Amount sold
            sell_curr: Currency sold (e.g., 'USD')
            fee: Trade fee amount
            fee_curr: Fee currency
            exchange: Exchange/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, "group", comment)
                   values (:createddate, 'Trade', :buy, :buy_curr, :sell, :sell_curr, :fee, :fee_curr, :exchange, :group, :comment)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "buy": buy,
            "buy_curr": buy_curr,
            "sell": sell,
            "sell_curr": sell_curr,
            "fee": fee,
            "fee_curr": fee_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment
        })
        if commit:
            self.backend.commit()

    def mining(
        self,
        createddate: str | datetime,
        buy: float,
        buy_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        transactionid: str = "",
        commit: bool = True
    ) -> None:
        """Record a mining reward transaction.

        Args:
            createddate: Transaction date (string or datetime)
            buy: Amount mined
            buy_curr: Currency mined (e.g., 'BTC')
            exchange: Mining pool/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            transactionid: Optional transaction ID/hash
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, buy, buy_curr, exchange, "group", comment, transactionid)
                   values (:createddate, 'Mining', :buy, :buy_curr, :exchange, :group, :comment, :transactionid)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "buy": buy,
            "buy_curr": buy_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment,
            "transactionid": transactionid
        })
        if commit:
            self.backend.commit()

    def interest_income(
        self,
        createddate: str | datetime,
        buy: float,
        buy_curr: str,
        exchange: str,
        group: str = "",
        comment: str = "",
        commit: bool = True
    ) -> None:
        """Record an interest income transaction.

        Args:
            createddate: Transaction date (string or datetime)
            buy: Amount earned
            buy_curr: Currency earned (e.g., 'BTC', 'USD')
            exchange: Exchange/wallet name
            group: Optional grouping label
            comment: Optional transaction comment
            commit: Whether to commit immediately (default True)
        """
        query = """insert into ledger (createddate, trans_type, buy, buy_curr, exchange, "group", comment)
                   values (:createddate, 'Interest Income', :buy, :buy_curr, :exchange, :group, :comment)"""

        self.backend.execute(query, {
            "createddate": createddate,
            "buy": buy,
            "buy_curr": buy_curr,
            "exchange": exchange,
            "group": group,
            "comment": comment
        })
        if commit:
            self.backend.commit()

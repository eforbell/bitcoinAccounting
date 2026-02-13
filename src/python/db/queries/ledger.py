"""Ledger transaction writing operations for cryptocurrency accounting.

This module provides the LedgerWriter class for recording transactions
into the ledger table.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend

UPDATABLE_FIELDS = frozenset({
    'createddate', 'trans_type', 'buy', 'buy_curr',
    'sell', 'sell_curr', 'fee', 'fee_curr',
    'exchange', 'group', 'comment',
})


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
        exchange = exchange.strip()
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
        exchange = exchange.strip()
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
        exchange = exchange.strip()
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
        exchange = exchange.strip()
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
        exchange = exchange.strip()
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
        exchange = exchange.strip()
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

    def _get_transaction(self, tx_id: int) -> dict[str, Any]:
        """Fetch a single transaction by ID or raise ValueError."""
        row = self.backend.execute_one(
            'SELECT * FROM ledger WHERE id = :id',
            {'id': tx_id}
        )
        if row is None:
            raise ValueError(f"Transaction with id {tx_id} does not exist")
        return dict(row)

    def update_transaction(self, tx_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update specified fields on a ledger row by id.

        Args:
            tx_id: The ledger row id to update.
            **kwargs: Field names and new values. Allowed fields:
                createddate, trans_type, buy, buy_curr, sell, sell_curr,
                fee, fee_curr, exchange, group, comment.

        Returns:
            The updated row as a dictionary.

        Raises:
            ValueError: If tx_id does not exist or no valid fields provided.
        """
        self._get_transaction(tx_id)

        updates = {k: v for k, v in kwargs.items() if k in UPDATABLE_FIELDS}
        if not updates:
            raise ValueError("No valid fields to update. "
                             f"Allowed fields: {sorted(UPDATABLE_FIELDS)}")

        # Strip whitespace on exchange/wallet name
        if 'exchange' in updates and isinstance(updates['exchange'], str):
            updates['exchange'] = updates['exchange'].strip()

        set_clause = ', '.join(
            f'"{col}" = :{col}' if col == 'group'
            else f'{col} = :{col}'
            for col in updates
        )
        params = {**updates, 'id': tx_id}
        self.backend.execute(
            f'UPDATE ledger SET {set_clause} WHERE id = :id',
            params
        )
        self.backend.commit()
        return self._get_transaction(tx_id)

    def soft_delete_transaction(self, tx_id: int) -> dict[str, Any]:
        """Soft-delete a ledger row by setting deleted=1 and deleted_date=now.

        Args:
            tx_id: The ledger row id to soft-delete.

        Returns:
            The updated row as a dictionary.

        Raises:
            ValueError: If tx_id does not exist.
        """
        self._get_transaction(tx_id)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.backend.execute(
            'UPDATE ledger SET deleted = 1, deleted_date = :now WHERE id = :id',
            {'now': now, 'id': tx_id}
        )
        self.backend.commit()
        return self._get_transaction(tx_id)

    def restore_transaction(self, tx_id: int) -> dict[str, Any]:
        """Restore a soft-deleted ledger row by setting deleted=0 and deleted_date=NULL.

        Args:
            tx_id: The ledger row id to restore.

        Returns:
            The updated row as a dictionary.

        Raises:
            ValueError: If tx_id does not exist.
        """
        self._get_transaction(tx_id)

        self.backend.execute(
            'UPDATE ledger SET deleted = 0, deleted_date = NULL WHERE id = :id',
            {'id': tx_id}
        )
        self.backend.commit()
        return self._get_transaction(tx_id)

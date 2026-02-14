"""Wallet query operations for cryptocurrency accounting.

This module provides the WalletQuery class for wallet-related queries including
wallet listings and balance calculations per wallet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend


class WalletQuery:
    """Query wallet information and balances.

    This class provides methods to retrieve wallet metadata and calculate
    balances for specific wallets or all wallets.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize the wallet query handler.

        Args:
            backend: Database backend to use for queries
        """
        self.backend = backend

    def _wallet_exists(self, wallet_id: str) -> bool:
        """Return True if a wallet record exists."""
        query = "SELECT COUNT(*) FROM wallets WHERE wallet_id = :wallet_id"
        return self.backend.execute_scalar(query, {"wallet_id": wallet_id}) > 0

    def get_balance_by_account(self, coin: str = 'BTC', account: str = 'Vault') -> float:
        """Get balance for a specific account/wallet.

        Fees are already included in buy/sell amounts, not subtracted separately.
        Stake transactions are excluded from the balance, consistent with get_balance().

        Args:
            coin: Currency code (e.g., 'BTC', 'USD')
            account: Wallet/exchange name

        Returns:
            float: Account balance
        """
        account = account.strip()
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN buy_curr = :coin AND trans_type != 'Stake' THEN buy ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN sell_curr = :coin THEN sell ELSE 0 END), 0)
            FROM ledger
            WHERE exchange = :account
            AND (deleted = 0 OR deleted IS NULL)
        """
        result = self.backend.execute_scalar(query, {"coin": coin, "account": account})
        balance = float(result) if result is not None else 0.0
        # Return 0 for very small amounts (dust)
        return balance if abs(balance) > 0.0000000000001 else 0.0

    def get_wallets(self, active_only: bool = False) -> list[dict[str, Any]]:
        """Get list of all wallets with metadata (if wallets table exists).

        Args:
            active_only: If True, only return active wallets. Default False returns all.

        Returns:
            List of wallet dictionaries with keys: wallet_id, type, custody, description, active
        """
        # Check if wallets table exists (backend-specific)
        from ..sqlite import SqliteBackend
        if isinstance(self.backend, SqliteBackend):
            # SQLite: check sqlite_master
            check_query = """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='wallets'
            """
        else:
            # PostgreSQL: check information_schema
            check_query = """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'wallets'
            """

        table_exists = self.backend.execute_scalar(check_query) > 0

        if table_exists:
            # Get wallet metadata from wallets table
            # Use TRUE for boolean - works in both SQLite and PostgreSQL
            active_filter = "WHERE active = TRUE" if active_only else ""
            query = f"""
                SELECT wallet_id, wallet_type, custody, description, active
                FROM wallets
                {active_filter}
                ORDER BY wallet_id
            """
            rows = self.backend.execute(query)
            wallets = [{'wallet_id': row['wallet_id'], 'type': row['wallet_type'], 'custody': row['custody'],
                        'description': row['description'], 'active': row['active']}
                       for row in rows]

            # If table exists but is empty, fall back to ledger
            if wallets:
                return wallets
            # Fall through to ledger fallback below

        # Fallback: get distinct exchange values from ledger
        # (used when table doesn't exist OR table is empty)
        query = """
            SELECT DISTINCT exchange
            FROM ledger
            WHERE exchange IS NOT NULL
            AND (deleted = 0 OR deleted IS NULL)
            ORDER BY exchange
        """
        rows = self.backend.execute(query)
        return [{'wallet_id': row['exchange'],
                 'type': 'unknown',
                 'custody': self.infer_custody_type(row['exchange']),
                 'description': None,
                 'active': True}
               for row in rows]

    def infer_custody_type(self, wallet_id: str) -> str:
        """Infer custody type from wallet name using heuristics.

        Args:
            wallet_id: Wallet/exchange name

        Returns:
            str: 'custodial', 'self-custodied', 'multisig', or 'unknown'
        """
        name_lower = wallet_id.lower()

        # Known exchanges and custodial services
        custodial_keywords = [
            'coinbase', 'kraken', 'binance', 'gemini', 'bitstamp', 'bitfinex',
            'swan', 'strike', 'cashapp', 'cash app', 'river', 'blockfi',
            'celsius', 'nexo', 'ftx', 'kucoin', 'bittrex', 'poloniex',
            'okx', 'huobi', 'bitflyer', 'liquid', 'exchange', 'custodial'
        ]

        # Known multisig services
        multisig_keywords = [
            'unchained', 'casa', 'caravan', 'electrum', 'multisig', 'multi-sig',
            'collaborative'
        ]

        # Known self-custody wallets (hardware, software)
        self_custody_keywords = [
            'ledger', 'trezor', 'coldcard', 'bitbox', 'keepkey', 'blockstream',
            'jade', 'specter', 'sparrow', 'blue wallet', 'bluewallet', 'samourai',
            'wasabi', 'green', 'muun', 'phoenix', 'breez', 'blixt',
            'vault', 'cold', 'hardware', 'personal', 'private', 'my wallet',
            'self', 'hot wallet', 'mobile'
        ]

        # Check for matches
        for keyword in custodial_keywords:
            if keyword in name_lower:
                return 'custodial'

        for keyword in multisig_keywords:
            if keyword in name_lower:
                return 'multisig'

        for keyword in self_custody_keywords:
            if keyword in name_lower:
                return 'self-custodied'

        # Default: assume self-custodied for unknown wallets
        # (conservative assumption - better to assume user controls keys)
        return 'self-custodied'

    def get_balance_by_wallet(self, coin: str = 'BTC', wallet: str | None = None) -> float | dict[str, float]:
        """Get balance for a specific wallet, or all wallets if wallet=None.

        Args:
            coin: Currency code (e.g., 'BTC', 'USD')
            wallet: Wallet/exchange name. If None, returns all wallets.

        Returns:
            If wallet specified: float (balance)
            If wallet=None: dict {wallet_id: balance}
        """
        if wallet:
            # Balance for specific wallet - use get_balance_by_account
            return self.get_balance_by_account(coin, wallet)
        else:
            # Balance for all wallets
            # Note: Fees are already included in buy/sell amounts, not subtracted separately
            query = """
                SELECT
                    exchange,
                    COALESCE(SUM(CASE WHEN buy_curr = :coin THEN buy ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN sell_curr = :coin THEN sell ELSE 0 END), 0) as balance
                FROM ledger
                WHERE exchange IS NOT NULL
                AND (deleted = 0 OR deleted IS NULL)
                GROUP BY exchange
                ORDER BY exchange
            """
            rows = self.backend.execute(query, {"coin": coin})
            return {row['exchange']: float(row['balance']) for row in rows}

    def add_wallet(
        self,
        wallet_id: str,
        wallet_type: str,
        custody: str,
        description: str | None = None,
        notes: str | None = None
    ) -> None:
        """Add a new wallet to the wallets table.

        Args:
            wallet_id: Unique wallet identifier/name
            wallet_type: Type of wallet (e.g., 'exchange', 'hardware', 'software', 'mobile', 'paper', 'other')
            custody: Custody type ('self-custodied', 'custodial', 'multisig')
            description: Optional wallet description
            notes: Optional additional notes

        Raises:
            Exception: If wallet_id already exists (duplicate key violation)
        """
        wallet_id = wallet_id.strip()
        query = """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, notes)
            VALUES (:wallet_id, :wallet_type, :custody, :description, :notes)
        """
        self.backend.execute(
            query,
            {
                "wallet_id": wallet_id,
                "wallet_type": wallet_type,
                "custody": custody,
                "description": description,
                "notes": notes
            }
        )
        self.backend.commit()

    def update_wallet(self, wallet_id: str, **kwargs: Any) -> None:
        """Update wallet metadata fields.

        Args:
            wallet_id: Wallet identifier to update
            **kwargs: Fields to update (wallet_type, custody, description, active, notes)

        Raises:
            ValueError: If no valid fields provided
            Exception: If wallet_id doesn't exist
        """
        wallet_id = wallet_id.strip()
        valid_fields = {'wallet_type', 'custody', 'description', 'active', 'notes'}
        update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}

        if not update_fields:
            raise ValueError("No valid fields to update")
        if not self._wallet_exists(wallet_id):
            raise ValueError(f"Wallet '{wallet_id}' does not exist")

        # Build SET clause dynamically
        set_clause = ", ".join(f"{field} = :{field}" for field in update_fields)
        query = f"UPDATE wallets SET {set_clause} WHERE wallet_id = :wallet_id"

        params = {**update_fields, "wallet_id": wallet_id}
        self.backend.execute(query, params)
        self.backend.commit()

    def rename_wallet(self, old_id: str, new_id: str) -> None:
        """Rename a wallet, updating all ledger references atomically.

        This operation updates both the wallets table and all ledger.exchange
        references in a single transaction to maintain referential integrity.

        Args:
            old_id: Current wallet identifier
            new_id: New wallet identifier

        Raises:
            ValueError: If new_id already exists
            Exception: If old_id doesn't exist
        """
        old_id = old_id.strip()
        new_id = new_id.strip()
        if old_id == new_id:
            raise ValueError("New wallet name must be different from current name")
        if not self._wallet_exists(old_id):
            raise ValueError(f"Wallet '{old_id}' does not exist")

        # Check if new_id already exists
        if self._wallet_exists(new_id):
            raise ValueError(f"Wallet '{new_id}' already exists")

        # Perform atomic rename in transaction
        # Note: backend.execute() handles transactions internally for multi-statement operations
        update_wallets = "UPDATE wallets SET wallet_id = :new_id WHERE wallet_id = :old_id"
        update_ledger = "UPDATE ledger SET exchange = :new_id WHERE exchange = :old_id"

        # Execute both updates as a single transaction.
        try:
            self.backend.execute(update_wallets, {"old_id": old_id, "new_id": new_id})
            self.backend.execute(update_ledger, {"old_id": old_id, "new_id": new_id})
            self.backend.commit()
        except Exception:
            try:
                self.backend.rollback()
            except Exception:
                pass
            raise

    def merge_wallets(self, source_id: str, target_id: str) -> None:
        """Merge two wallets by moving all transactions from source to target.

        All ledger rows with source_id are reassigned to target_id, then the
        source wallet record is deleted.

        Args:
            source_id: Wallet to merge from (will be deleted)
            target_id: Wallet to merge into (will receive all transactions)

        Raises:
            Exception: If target_id doesn't exist
        """
        source_id = source_id.strip()
        target_id = target_id.strip()
        if source_id == target_id:
            raise ValueError("Source and target wallets must be different")
        if not self._wallet_exists(source_id):
            raise ValueError(f"Source wallet '{source_id}' does not exist")
        if not self._wallet_exists(target_id):
            raise ValueError(f"Target wallet '{target_id}' does not exist")

        # Update all ledger rows to point to target
        update_ledger = "UPDATE ledger SET exchange = :target_id WHERE exchange = :source_id"
        delete_wallet = "DELETE FROM wallets WHERE wallet_id = :source_id"

        try:
            self.backend.execute(update_ledger, {"source_id": source_id, "target_id": target_id})
            # Delete source wallet record
            self.backend.execute(delete_wallet, {"source_id": source_id})
            self.backend.commit()
        except Exception:
            try:
                self.backend.rollback()
            except Exception:
                pass
            raise

    def sync_wallets_from_ledger(self) -> int:
        """Create wallet records for exchanges in ledger that lack wallet entries.

        This bridges the gap between implicit wallet references (exchange names
        in ledger) and explicit wallet management (wallets table). Useful for
        existing databases or after imports that reference new wallets.

        Returns:
            int: Number of new wallet records created
        """
        # Get all distinct exchange names from ledger
        ledger_query = """
            SELECT DISTINCT exchange
            FROM ledger
            WHERE exchange IS NOT NULL
            AND (deleted = 0 OR deleted IS NULL)
            ORDER BY exchange
        """
        ledger_wallets = [row['exchange'] for row in self.backend.execute(ledger_query)]

        # Get existing wallet IDs from wallets table only (not ledger fallback)
        wallets_query = "SELECT wallet_id FROM wallets"
        existing = {row['wallet_id'] for row in self.backend.execute(wallets_query)}

        # Find wallets that need to be created
        missing = [w for w in ledger_wallets if w not in existing]

        # Create wallet records for missing ones
        for wallet_id in missing:
            custody = self.infer_custody_type(wallet_id)
            # Infer wallet_type from custody
            wallet_type = 'exchange' if custody == 'custodial' else 'hardware'
            self.add_wallet(
                wallet_id=wallet_id,
                wallet_type=wallet_type,
                custody=custody,
                description=None,
                notes='Auto-synced from ledger'
            )

        return len(missing)

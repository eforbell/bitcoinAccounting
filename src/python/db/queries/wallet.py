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
                GROUP BY exchange
                ORDER BY exchange
            """
            rows = self.backend.execute(query, {"coin": coin})
            return {row['exchange']: float(row['balance']) for row in rows}

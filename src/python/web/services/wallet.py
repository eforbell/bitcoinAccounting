"""Wallet management service for web routes."""

from __future__ import annotations

from typing import Any

from bitcoinAccounts import BitcoinAccounts
from web.models import WalletListResource, WalletResource


def _tx_counts_by_wallet(accounts: BitcoinAccounts) -> dict[str, int]:
    """Return {wallet_id: count} for all wallets referenced in the ledger."""
    query = """
        SELECT exchange, COUNT(*) as cnt
        FROM ledger
        WHERE exchange IS NOT NULL
        AND (deleted = 0 OR deleted IS NULL)
        GROUP BY exchange
    """
    rows = accounts.backend.execute(query)
    return {row["exchange"]: int(row["cnt"]) for row in rows}


def list_wallets(
    accounts: BitcoinAccounts,
    active_only: bool = False,
) -> list[WalletListResource]:
    """Return all wallets enriched with transaction counts."""
    wallets = accounts.wallet_query.get_wallets(active_only=active_only)
    counts = _tx_counts_by_wallet(accounts)
    return [
        WalletListResource(
            wallet_id=w["wallet_id"],
            wallet_type=w["type"],
            custody=w["custody"],
            description=w.get("description"),
            notes=w.get("notes"),
            active=bool(w["active"]),
            transaction_count=counts.get(w["wallet_id"], 0),
        )
        for w in wallets
    ]


def get_wallet(
    accounts: BitcoinAccounts,
    wallet_id: str,
) -> WalletListResource | None:
    """Return a single wallet with its transaction count, or None."""
    wallets = accounts.wallet_query.get_wallets()
    counts = _tx_counts_by_wallet(accounts)
    for w in wallets:
        if w["wallet_id"] == wallet_id:
            return WalletListResource(
                wallet_id=w["wallet_id"],
                wallet_type=w["type"],
                custody=w["custody"],
                description=w.get("description"),
                notes=w.get("notes"),
                active=bool(w["active"]),
                transaction_count=counts.get(w["wallet_id"], 0),
            )
    return None


def create_wallet(
    accounts: BitcoinAccounts,
    wallet_id: str,
    wallet_type: str,
    custody: str,
    description: str | None = None,
    notes: str | None = None,
) -> WalletResource:
    """Create a wallet and return its resource representation."""
    accounts.wallet_query.add_wallet(
        wallet_id=wallet_id,
        wallet_type=wallet_type,
        custody=custody,
        description=description,
        notes=notes,
    )
    return WalletResource(
        wallet_id=wallet_id,
        wallet_type=wallet_type,
        custody=custody,
        description=description,
        notes=notes,
        active=True,
    )


def _wallet_resource(w: dict[str, Any]) -> WalletResource:
    """Build a WalletResource from a get_wallets() dict."""
    return WalletResource(
        wallet_id=w["wallet_id"],
        wallet_type=w["type"],
        custody=w["custody"],
        description=w.get("description"),
        notes=w.get("notes"),
        active=bool(w["active"]),
    )


def update_wallet(
    accounts: BitcoinAccounts,
    wallet_id: str,
    **kwargs: Any,
) -> WalletResource | None:
    """Update wallet fields and return the updated resource."""
    accounts.wallet_query.update_wallet(wallet_id, **kwargs)
    wallets = accounts.wallet_query.get_wallets()
    for w in wallets:
        if w["wallet_id"] == wallet_id:
            return _wallet_resource(w)
    return None


def rename_wallet(
    accounts: BitcoinAccounts,
    old_id: str,
    new_id: str,
) -> WalletResource | None:
    """Rename a wallet and return the resource under the new name."""
    accounts.wallet_query.rename_wallet(old_id, new_id)
    wallets = accounts.wallet_query.get_wallets()
    for w in wallets:
        if w["wallet_id"] == new_id:
            return _wallet_resource(w)
    return None


def merge_wallets(
    accounts: BitcoinAccounts,
    source_id: str,
    target_id: str,
) -> dict[str, Any]:
    """Merge source into target. Returns summary."""
    accounts.wallet_query.merge_wallets(source_id, target_id)
    return {
        "status": "ok",
        "action": "merge",
        "source": source_id,
        "target": target_id,
    }


def sync_wallets(accounts: BitcoinAccounts) -> dict[str, Any]:
    """Sync wallets from ledger. Returns count of created wallets."""
    created = accounts.wallet_query.sync_wallets_from_ledger()
    return {"status": "ok", "action": "sync", "created": created}

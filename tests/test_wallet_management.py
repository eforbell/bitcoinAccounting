"""Tests for wallet management CRUD operations (WM-001).

This module tests the new wallet management methods added to WalletQuery:
- add_wallet()
- update_wallet()
- rename_wallet()
- merge_wallets()
- sync_wallets_from_ledger()
"""

from __future__ import annotations

import pytest

from src.python.db.backend import DatabaseBackend
from src.python.db.queries.ledger import LedgerWriter
from src.python.db.queries.wallet import WalletQuery
from src.python.db.schema import create_tables
from src.python.db.sqlite import SqliteBackend


@pytest.fixture
def backend() -> DatabaseBackend:
    """Create an in-memory SQLite backend for testing."""
    backend = SqliteBackend(":memory:")
    create_tables(backend)
    return backend


@pytest.fixture
def wallet_query(backend: DatabaseBackend) -> WalletQuery:
    """Create a WalletQuery instance."""
    return WalletQuery(backend)


@pytest.fixture
def ledger_writer(backend: DatabaseBackend) -> LedgerWriter:
    """Create a LedgerWriter instance for setting up test data."""
    return LedgerWriter(backend)


class TestAddWallet:
    """Test add_wallet() method."""

    def test_add_wallet_basic(self, wallet_query: WalletQuery) -> None:
        """Test adding a basic wallet."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        wallets = wallet_query.get_wallets()
        assert len(wallets) == 1
        assert wallets[0]['wallet_id'] == "Coinbase"
        assert wallets[0]['type'] == "exchange"
        assert wallets[0]['custody'] == "custodial"
        assert wallets[0]['description'] is None
        # SQLite returns 1 for True
        assert wallets[0]['active'] == 1 or wallets[0]['active'] is True

    def test_add_wallet_with_optional_fields(self, wallet_query: WalletQuery) -> None:
        """Test adding a wallet with description and notes."""
        wallet_query.add_wallet(
            wallet_id="Ledger",
            wallet_type="hardware",
            custody="self-custodied",
            description="Nano X hardware wallet",
            notes="24-word seed stored in safe"
        )

        wallets = wallet_query.get_wallets()
        assert len(wallets) == 1
        assert wallets[0]['wallet_id'] == "Ledger"
        assert wallets[0]['description'] == "Nano X hardware wallet"

    def test_add_wallet_strips_whitespace(self, wallet_query: WalletQuery) -> None:
        """Test that wallet_id whitespace is stripped."""
        wallet_query.add_wallet(
            wallet_id="  Strike  ",
            wallet_type="exchange",
            custody="custodial"
        )

        wallets = wallet_query.get_wallets()
        assert wallets[0]['wallet_id'] == "Strike"

    def test_add_wallet_duplicate_raises_error(self, wallet_query: WalletQuery) -> None:
        """Test that adding duplicate wallet_id raises an error."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        # Attempt to add duplicate should raise exception
        with pytest.raises(Exception):
            wallet_query.add_wallet(
                wallet_id="Coinbase",
                wallet_type="exchange",
                custody="custodial"
            )


class TestUpdateWallet:
    """Test update_wallet() method."""

    def test_update_wallet_single_field(self, wallet_query: WalletQuery) -> None:
        """Test updating a single field."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        wallet_query.update_wallet("Coinbase", description="Main exchange account")

        wallets = wallet_query.get_wallets()
        assert wallets[0]['description'] == "Main exchange account"

    def test_update_wallet_multiple_fields(self, wallet_query: WalletQuery) -> None:
        """Test updating multiple fields at once."""
        wallet_query.add_wallet(
            wallet_id="Ledger",
            wallet_type="hardware",
            custody="self-custodied"
        )

        wallet_query.update_wallet(
            "Ledger",
            wallet_type="hardware",
            description="Nano X",
            notes="Primary cold storage"
        )

        wallets = wallet_query.get_wallets()
        assert wallets[0]['description'] == "Nano X"

    def test_update_wallet_active_status(self, wallet_query: WalletQuery) -> None:
        """Test toggling active status."""
        wallet_query.add_wallet(
            wallet_id="OldExchange",
            wallet_type="exchange",
            custody="custodial"
        )

        # Deactivate wallet (SQLite uses 0/1 for boolean)
        wallet_query.update_wallet("OldExchange", active=0)

        # Should not appear when filtering for active only
        active_wallets = wallet_query.get_wallets(active_only=True)
        assert len(active_wallets) == 0

        # Should still appear without filter
        all_wallets = wallet_query.get_wallets(active_only=False)
        assert len(all_wallets) == 1
        # SQLite returns 0 for False
        assert all_wallets[0]['active'] == 0 or all_wallets[0]['active'] is False

    def test_update_wallet_strips_whitespace(self, wallet_query: WalletQuery) -> None:
        """Test that wallet_id whitespace is stripped in update."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        wallet_query.update_wallet("  Coinbase  ", description="Updated")

        wallets = wallet_query.get_wallets()
        assert wallets[0]['description'] == "Updated"

    def test_update_wallet_no_fields_raises_error(self, wallet_query: WalletQuery) -> None:
        """Test that update with no valid fields raises ValueError."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        with pytest.raises(ValueError, match="No valid fields to update"):
            wallet_query.update_wallet("Coinbase")

    def test_update_wallet_invalid_fields_ignored(self, wallet_query: WalletQuery) -> None:
        """Test that invalid fields are ignored."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )

        # Should ignore invalid_field, only update description
        wallet_query.update_wallet(
            "Coinbase",
            description="Updated",
            invalid_field="should be ignored"  # type: ignore
        )

        wallets = wallet_query.get_wallets()
        assert wallets[0]['description'] == "Updated"


class TestRenameWallet:
    """Test rename_wallet() method."""

    def test_rename_wallet_basic(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test basic wallet rename."""
        # Create wallet
        wallet_query.add_wallet(
            wallet_id="Stike",  # typo
            wallet_type="exchange",
            custody="custodial"
        )

        # Add some transactions
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Stike")
        ledger_writer.deposit("2024-01-02", 0.5, "BTC", "Stike")

        # Rename wallet
        wallet_query.rename_wallet("Stike", "Strike")

        # Verify wallet was renamed
        wallets = wallet_query.get_wallets()
        wallet_ids = [w['wallet_id'] for w in wallets]
        assert "Strike" in wallet_ids
        assert "Stike" not in wallet_ids

        # Verify all ledger references were updated
        balance = wallet_query.get_balance_by_account("BTC", "Strike")
        assert balance == 1.5
        balance_old = wallet_query.get_balance_by_account("BTC", "Stike")
        assert balance_old == 0.0

    def test_rename_wallet_duplicate_raises_error(self, wallet_query: WalletQuery) -> None:
        """Test that renaming to existing wallet_id raises ValueError."""
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial"
        )
        wallet_query.add_wallet(
            wallet_id="Strike",
            wallet_type="exchange",
            custody="custodial"
        )

        with pytest.raises(ValueError, match="already exists"):
            wallet_query.rename_wallet("Strike", "Coinbase")

    def test_rename_wallet_strips_whitespace(
        self,
        wallet_query: WalletQuery
    ) -> None:
        """Test that whitespace is stripped in rename."""
        wallet_query.add_wallet(
            wallet_id="OldName",
            wallet_type="exchange",
            custody="custodial"
        )

        wallet_query.rename_wallet("  OldName  ", "  NewName  ")

        wallets = wallet_query.get_wallets()
        assert wallets[0]['wallet_id'] == "NewName"


class TestMergeWallets:
    """Test merge_wallets() method."""

    def test_merge_wallets_basic(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test basic wallet merge."""
        # Create two wallets
        wallet_query.add_wallet(
            wallet_id="coinbase",
            wallet_type="exchange",
            custody="custodial"
        )
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial",
            description="Main exchange"
        )

        # Add transactions to both
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "coinbase")
        ledger_writer.deposit("2024-01-02", 2.0, "BTC", "Coinbase")

        # Merge coinbase into Coinbase
        wallet_query.merge_wallets("coinbase", "Coinbase")

        # Verify source wallet was deleted
        wallets = wallet_query.get_wallets()
        wallet_ids = [w['wallet_id'] for w in wallets]
        assert "Coinbase" in wallet_ids
        assert "coinbase" not in wallet_ids

        # Verify all transactions moved to target
        balance = wallet_query.get_balance_by_account("BTC", "Coinbase")
        assert balance == 3.0
        balance_old = wallet_query.get_balance_by_account("BTC", "coinbase")
        assert balance_old == 0.0

    def test_merge_wallets_strips_whitespace(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that whitespace is stripped in merge."""
        wallet_query.add_wallet(
            wallet_id="Source",
            wallet_type="exchange",
            custody="custodial"
        )
        wallet_query.add_wallet(
            wallet_id="Target",
            wallet_type="exchange",
            custody="custodial"
        )

        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Source")

        wallet_query.merge_wallets("  Source  ", "  Target  ")

        wallets = wallet_query.get_wallets()
        wallet_ids = [w['wallet_id'] for w in wallets]
        assert "Target" in wallet_ids
        assert "Source" not in wallet_ids

    def test_merge_preserves_target_metadata(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that merge preserves target wallet metadata."""
        wallet_query.add_wallet(
            wallet_id="Source",
            wallet_type="exchange",
            custody="custodial",
            description="Will be deleted"
        )
        wallet_query.add_wallet(
            wallet_id="Target",
            wallet_type="hardware",
            custody="self-custodied",
            description="Keep this description"
        )

        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Source")

        wallet_query.merge_wallets("Source", "Target")

        wallets = wallet_query.get_wallets()
        target_wallet = next(w for w in wallets if w['wallet_id'] == "Target")
        assert target_wallet['description'] == "Keep this description"
        assert target_wallet['type'] == "hardware"
        assert target_wallet['custody'] == "self-custodied"


class TestSyncWalletsFromLedger:
    """Test sync_wallets_from_ledger() method."""

    def test_sync_creates_missing_wallets(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that sync creates wallet records for ledger exchanges."""
        # Add transactions without creating wallet records
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Coinbase")
        ledger_writer.deposit("2024-01-02", 0.5, "BTC", "Ledger")
        ledger_writer.deposit("2024-01-03", 0.3, "BTC", "Strike")

        # Sync should create 3 wallet records
        count = wallet_query.sync_wallets_from_ledger()
        assert count == 3

        # Verify wallets were created
        wallets = wallet_query.get_wallets()
        wallet_ids = {w['wallet_id'] for w in wallets}
        assert wallet_ids == {"Coinbase", "Ledger", "Strike"}

    def test_sync_infers_custody_type(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that sync infers custody type correctly."""
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Coinbase")
        ledger_writer.deposit("2024-01-02", 0.5, "BTC", "Ledger")

        wallet_query.sync_wallets_from_ledger()

        wallets = {w['wallet_id']: w for w in wallet_query.get_wallets()}
        assert wallets["Coinbase"]['custody'] == "custodial"
        assert wallets["Ledger"]['custody'] == "self-custodied"

    def test_sync_skips_existing_wallets(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that sync doesn't create duplicates for existing wallets."""
        # Create one wallet explicitly
        wallet_query.add_wallet(
            wallet_id="Coinbase",
            wallet_type="exchange",
            custody="custodial",
            description="My main exchange"
        )

        # Add transactions to both existing and new wallets
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Coinbase")
        ledger_writer.deposit("2024-01-02", 0.5, "BTC", "Strike")

        # Sync should create only 1 new wallet (Strike)
        count = wallet_query.sync_wallets_from_ledger()
        assert count == 1

        # Verify Coinbase metadata wasn't overwritten
        wallets = {w['wallet_id']: w for w in wallet_query.get_wallets()}
        assert wallets["Coinbase"]['description'] == "My main exchange"

    def test_sync_returns_zero_when_all_exist(
        self,
        wallet_query: WalletQuery,
        ledger_writer: LedgerWriter
    ) -> None:
        """Test that sync returns 0 when all wallets already exist."""
        ledger_writer.deposit("2024-01-01", 1.0, "BTC", "Coinbase")

        # First sync creates the wallet
        count1 = wallet_query.sync_wallets_from_ledger()
        assert count1 == 1

        # Second sync should do nothing
        count2 = wallet_query.sync_wallets_from_ledger()
        assert count2 == 0

    def test_sync_with_empty_ledger(self, wallet_query: WalletQuery) -> None:
        """Test that sync with empty ledger returns 0."""
        count = wallet_query.sync_wallets_from_ledger()
        assert count == 0

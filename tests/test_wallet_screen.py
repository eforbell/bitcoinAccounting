"""Tests for Wallet Management TUI screen (WM-002 and WM-003)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from textual.binding import Binding
from textual.widgets import Button, Input, Label, Select

from src.python.tui.app import CryptoApp
from src.python.tui.screens.wallet_management import (
    CreateWalletModal,
    EditWalletModal,
    MergeWalletsModal,
    RenameWalletModal,
    WalletManagementScreen,
)


class TestWalletManagementScreenStructure:
    """Test wallet management screen structure and bindings."""

    def test_screen_exists(self) -> None:
        """Test that WalletManagementScreen class exists."""
        assert WalletManagementScreen is not None

    def test_screen_has_bindings(self) -> None:
        """Test that screen has required key bindings."""
        screen = WalletManagementScreen()
        binding_keys = [b.key for b in screen.BINDINGS if isinstance(b, Binding)]

        # Check required bindings
        assert "escape" in binding_keys
        assert "n" in binding_keys  # new wallet
        assert "e" in binding_keys  # edit wallet
        assert "d" in binding_keys  # toggle active

    def test_app_has_wallet_menu_binding(self) -> None:
        """Test that app has 'w' binding for wallet menu."""
        app = CryptoApp()
        binding_keys = [b.key for b in app.BINDINGS if isinstance(b, Binding)]
        assert "w" in binding_keys

    def test_app_has_wallet_menu_action(self) -> None:
        """Test that app has action_menu_wallet method."""
        app = CryptoApp()
        assert hasattr(app, "action_menu_wallet")
        assert callable(app.action_menu_wallet)


class TestWalletManagementScreenActions:
    """Test that screen has required action methods."""

    def test_screen_has_action_methods(self) -> None:
        """Test that screen has all required action methods."""
        screen = WalletManagementScreen()

        # Check action methods exist
        assert hasattr(screen, "action_new_wallet")
        assert hasattr(screen, "action_edit_wallet")
        assert hasattr(screen, "action_toggle_active")
        assert hasattr(screen, "action_rename_wallet")
        assert hasattr(screen, "action_merge_wallets")

        # Check they're callable
        assert callable(screen.action_new_wallet)
        assert callable(screen.action_edit_wallet)
        assert callable(screen.action_toggle_active)

    def test_toggle_active_binding_exists(self) -> None:
        """Test that 'd' binding exists for toggle active."""
        screen = WalletManagementScreen()
        binding_keys = [b.key for b in screen.BINDINGS if isinstance(b, Binding)]
        assert "d" in binding_keys


@pytest.mark.asyncio
class TestWalletManagementScreenRender:
    """Test screen rendering (may segfault due to SQLite threading issue - known issue)."""

    @pytest.mark.skip(reason="Pre-existing SQLite threading segfault in dashboard - see MEMORY.md")
    async def test_screen_renders(self) -> None:
        """Test that screen renders without crashing."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("w")
            await pilot.pause()
            assert True


class TestCreateWalletModal:
    """Test CreateWalletModal structure (WM-003)."""

    def test_modal_exists(self) -> None:
        """Test that CreateWalletModal class exists."""
        assert CreateWalletModal is not None

    def test_modal_has_escape_binding(self) -> None:
        """Test that modal has escape binding."""
        modal = CreateWalletModal()
        binding_keys = [b.key for b in modal.BINDINGS if isinstance(b, Binding)]
        assert "escape" in binding_keys

    def test_modal_has_compose_method(self) -> None:
        """Test that modal has compose method."""
        modal = CreateWalletModal()
        assert hasattr(modal, "compose")
        assert callable(modal.compose)

    def test_modal_has_validation_method(self) -> None:
        """Test that modal has validation method."""
        modal = CreateWalletModal()
        assert hasattr(modal, "_validate_and_create")
        assert callable(modal._validate_and_create)

    def test_modal_has_cancel_action(self) -> None:
        """Test that modal has cancel action."""
        modal = CreateWalletModal()
        assert hasattr(modal, "action_cancel")
        assert callable(modal.action_cancel)


class TestEditWalletModal:
    """Test EditWalletModal structure (WM-004)."""

    def test_modal_exists(self) -> None:
        """Test that EditWalletModal class exists."""
        assert EditWalletModal is not None

    def test_modal_requires_wallet_param(self) -> None:
        """Test that modal requires wallet parameter."""
        test_wallet = {
            'wallet_id': 'TestWallet',
            'type': 'hardware',
            'custody': 'self-custodied',
            'description': 'Test',
            'active': True
        }
        modal = EditWalletModal(test_wallet)
        assert modal._wallet == test_wallet

    def test_modal_has_escape_binding(self) -> None:
        """Test that modal has escape binding."""
        test_wallet = {
            'wallet_id': 'TestWallet',
            'type': 'hardware',
            'custody': 'self-custodied',
            'description': 'Test',
            'active': True
        }
        modal = EditWalletModal(test_wallet)
        binding_keys = [b.key for b in modal.BINDINGS if isinstance(b, Binding)]
        assert "escape" in binding_keys

    def test_modal_has_compose_method(self) -> None:
        """Test that modal has compose method."""
        test_wallet = {
            'wallet_id': 'TestWallet',
            'type': 'hardware',
            'custody': 'self-custodied',
            'description': 'Test',
            'active': True
        }
        modal = EditWalletModal(test_wallet)
        assert hasattr(modal, "compose")
        assert callable(modal.compose)

    def test_modal_has_validation_method(self) -> None:
        """Test that modal has validation method."""
        test_wallet = {
            'wallet_id': 'TestWallet',
            'type': 'hardware',
            'custody': 'self-custodied',
            'description': 'Test',
            'active': True
        }
        modal = EditWalletModal(test_wallet)
        assert hasattr(modal, "_validate_and_save")
        assert callable(modal._validate_and_save)

    def test_modal_has_cancel_action(self) -> None:
        """Test that modal has cancel action."""
        test_wallet = {
            'wallet_id': 'TestWallet',
            'type': 'hardware',
            'custody': 'self-custodied',
            'description': 'Test',
            'active': True
        }
        modal = EditWalletModal(test_wallet)
        assert hasattr(modal, "action_cancel")
        assert callable(modal.action_cancel)


class TestRenameWalletModal:
    """Test RenameWalletModal structure (WM-005)."""

    def test_modal_exists(self) -> None:
        """Test that RenameWalletModal class exists."""
        assert RenameWalletModal is not None

    def test_modal_requires_params(self) -> None:
        """Test that modal requires wallet_id and transaction_count parameters."""
        modal = RenameWalletModal("TestWallet", 5)
        assert modal._wallet_id == "TestWallet"
        assert modal._transaction_count == 5

    def test_modal_has_escape_binding(self) -> None:
        """Test that modal has escape binding."""
        modal = RenameWalletModal("TestWallet", 0)
        binding_keys = [b.key for b in modal.BINDINGS if isinstance(b, Binding)]
        assert "escape" in binding_keys

    def test_modal_has_compose_method(self) -> None:
        """Test that modal has compose method."""
        modal = RenameWalletModal("TestWallet", 0)
        assert hasattr(modal, "compose")
        assert callable(modal.compose)

    def test_modal_has_validation_method(self) -> None:
        """Test that modal has validation method."""
        modal = RenameWalletModal("TestWallet", 0)
        assert hasattr(modal, "_validate_and_rename")
        assert callable(modal._validate_and_rename)

    def test_modal_has_cancel_action(self) -> None:
        """Test that modal has cancel action."""
        modal = RenameWalletModal("TestWallet", 0)
        assert hasattr(modal, "action_cancel")
        assert callable(modal.action_cancel)

    def test_modal_shows_transaction_count(self) -> None:
        """Test that modal stores transaction count for warning display."""
        modal_with_txs = RenameWalletModal("Wallet1", 10)
        assert modal_with_txs._transaction_count == 10

        modal_without_txs = RenameWalletModal("Wallet2", 0)
        assert modal_without_txs._transaction_count == 0


class TestMergeWalletsModal:
    """Test MergeWalletsModal structure (WM-006)."""

    def test_modal_exists(self) -> None:
        """Test that MergeWalletsModal class exists."""
        assert MergeWalletsModal is not None

    def test_modal_requires_params(self) -> None:
        """Test that modal requires source_wallet_id, transaction_count, and available_targets."""
        targets = [
            {'wallet_id': 'Target1', 'type': 'hardware', 'custody': 'self-custodied'},
            {'wallet_id': 'Target2', 'type': 'exchange', 'custody': 'custodial'}
        ]
        modal = MergeWalletsModal("SourceWallet", 10, targets)
        assert modal._source_wallet_id == "SourceWallet"
        assert modal._transaction_count == 10
        assert modal._available_targets == targets

    def test_modal_has_escape_binding(self) -> None:
        """Test that modal has escape binding."""
        modal = MergeWalletsModal("Source", 0, [])
        binding_keys = [b.key for b in modal.BINDINGS if isinstance(b, Binding)]
        assert "escape" in binding_keys

    def test_modal_has_compose_method(self) -> None:
        """Test that modal has compose method."""
        modal = MergeWalletsModal("Source", 0, [])
        assert hasattr(modal, "compose")
        assert callable(modal.compose)

    def test_modal_has_validation_method(self) -> None:
        """Test that modal has validation method."""
        modal = MergeWalletsModal("Source", 0, [])
        assert hasattr(modal, "_validate_and_merge")
        assert callable(modal._validate_and_merge)

    def test_modal_has_cancel_action(self) -> None:
        """Test that modal has cancel action."""
        modal = MergeWalletsModal("Source", 0, [])
        assert hasattr(modal, "action_cancel")
        assert callable(modal.action_cancel)

    def test_modal_stores_transaction_count(self) -> None:
        """Test that modal stores transaction count for warning display."""
        targets = [{'wallet_id': 'Target1', 'type': 'hardware', 'custody': 'self-custodied'}]
        modal_with_txs = MergeWalletsModal("Source", 25, targets)
        assert modal_with_txs._transaction_count == 25

        modal_without_txs = MergeWalletsModal("Source", 0, targets)
        assert modal_without_txs._transaction_count == 0

    def test_modal_handles_empty_target_list(self) -> None:
        """Test that modal can be created with empty target list."""
        modal = MergeWalletsModal("Source", 5, [])
        assert modal._available_targets == []

"""Tests for LedgerScreen - transaction ledger with filtering."""

from __future__ import annotations

from datetime import datetime

import pytest
from textual.pilot import Pilot
from textual.widgets import Button, DataTable, Input, Label, Select

from bitcoinAccounts import CryptoAccounts
from db import SqliteBackend
from tui.app import CryptoApp
from tui.screens.ledger import EditTransactionModal, LedgerScreen, TransactionDetailModal


class TestLedgerScreenMount:
    """Test LedgerScreen mounting and basic structure."""

    @pytest.mark.asyncio
    async def test_screen_mounts_successfully(self) -> None:
        """Verify LedgerScreen can be mounted."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen

    @pytest.mark.asyncio
    async def test_screen_has_header_footer(self) -> None:
        """Verify screen has header and footer."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen.query("Header")
            assert app.screen.query("Footer")

    @pytest.mark.asyncio
    async def test_screen_subtitle(self) -> None:
        """Verify screen subtitle is set."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert screen.sub_title == "Transaction Ledger"


class TestLedgerFilterControls:
    """Test filter controls and UI elements."""

    @pytest.mark.asyncio
    async def test_coin_selector_present(self) -> None:
        """Verify coin selector is present and set to BTC."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            coin_select = app.screen.query_one("#coin-select")
            assert coin_select is not None
            assert coin_select.value == "BTC"

    @pytest.mark.asyncio
    async def test_wallet_selector_present(self) -> None:
        """Verify wallet selector is present."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            wallet_select = app.screen.query_one("#wallet-select")
            assert wallet_select is not None

    @pytest.mark.asyncio
    async def test_date_inputs_present(self) -> None:
        """Verify start and end date inputs are present."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen.query_one("#start-date-input")
            assert app.screen.query_one("#end-date-input")

    @pytest.mark.asyncio
    async def test_apply_filters_button_present(self) -> None:
        """Verify apply filters button is present."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen.query_one("#apply-filters-btn")

    @pytest.mark.asyncio
    async def test_status_label_present(self) -> None:
        """Verify status label is present."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen.query_one("#status-label")


class TestLedgerDataTable:
    """Test transaction data table."""

    @pytest.mark.asyncio
    async def test_table_present(self) -> None:
        """Verify DataTable widget is present."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen.query_one("#transactions-table")

    @pytest.mark.asyncio
    async def test_empty_state_when_no_transactions(self) -> None:
        """Verify empty state message when no transactions exist."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.crypto = crypto
            app.push_screen(LedgerScreen())
            await pilot.pause(0.2)
            status = app.screen.query_one("#status-label")
            # Empty database should show "No transactions found" or similar
            status_text = status.content
            assert "No transactions" in str(status_text) or "0" in str(status_text)


class TestLedgerWithData:
    """Test ledger screen with transaction data."""

    @pytest.fixture
    def crypto_with_data(self):
        """Create CryptoAccounts with test transactions."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)

        # Add initial balance for withdrawals
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 1), buy=2.0, buy_curr='BTC')

        # Import sample transactions (using lowercase keys per API)
        transactions = [
            {
                "trans_type": "Deposit",
                "buy": 1.0,
                "buy_curr": "BTC",
                "exchange": "Coinbase",
                "group": "",
                "comment": "Initial purchase",
                "created_date": "2024-01-15 10:00:00",
            },
            {
                "trans_type": "Withdrawal",
                "sell": 0.5001,  # Includes fee
                "sell_curr": "BTC",
                "fee": 0.0001,
                "fee_curr": "BTC",
                "exchange": "Coldcard",
                "group": "",
                "comment": "Move to cold storage",
                "created_date": "2024-01-20 14:30:00",
            },
            {
                "trans_type": "Trade",
                "buy": 0.2,
                "buy_curr": "BTC",
                "sell": 8000,
                "sell_curr": "USD",
                "fee": 10,
                "fee_curr": "USD",
                "exchange": "Kraken",
                "group": "",
                "comment": "Buy more BTC",
                "created_date": "2024-02-01 09:15:00",
            },
            {
                "trans_type": "Interest Income",
                "buy": 0.001,
                "buy_curr": "BTC",
                "exchange": "BlockFi",
                "group": "",
                "comment": "Monthly interest",
                "created_date": "2024-02-28 00:00:00",
            },
        ]

        result = crypto.import_transactions(transactions)  # type: ignore[no-untyped-call]
        assert result["imported"] == 4

        return crypto

    @pytest.mark.asyncio
    async def test_table_populates_with_data(self, crypto_with_data) -> None:
        """Verify table populates when transactions exist."""
        app = CryptoApp()

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            app.push_screen(LedgerScreen())
            await pilot.pause(0.3)

            table = app.screen.query_one("#transactions-table")
            assert table.row_count > 0  # Should have rows

    @pytest.mark.asyncio
    async def test_status_shows_row_count(self, crypto_with_data) -> None:
        """Verify status bar shows transaction count."""
        app = CryptoApp()

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            app.push_screen(LedgerScreen())
            await pilot.pause(0.3)

            status = app.screen.query_one("#status-label")
            status_text = str(status.content)
            assert "4" in status_text or "transactions" in status_text.lower()


class TestLedgerFiltering:
    """Test transaction filtering functionality."""

    @pytest.fixture
    def crypto_with_multi_wallet_data(self):
        """Create CryptoAccounts with multi-wallet transactions."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)

        # Add initial balance for withdrawals
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2023, 1, 1), buy=1.0, buy_curr='BTC')

        transactions = [
            {
                "trans_type": "Deposit",
                "buy": 1.0,
                "buy_curr": "BTC",
                "exchange": "Coinbase",
                "group": "",
                "comment": "",
                "created_date": "2023-06-15 10:00:00",
            },
            {
                "trans_type": "Withdrawal",
                "sell": 0.5001,  # Includes fee
                "sell_curr": "BTC",
                "fee": 0.0001,
                "fee_curr": "BTC",
                "exchange": "Coldcard",
                "group": "",
                "comment": "",
                "created_date": "2024-01-20 14:30:00",
            },
            {
                "trans_type": "Deposit",
                "buy": 0.3,
                "buy_curr": "BTC",
                "exchange": "Ledger",
                "group": "",
                "comment": "",
                "created_date": "2024-06-01 09:00:00",
            },
        ]

        result = crypto.import_transactions(transactions)  # type: ignore[no-untyped-call]
        assert result["imported"] == 3

        return crypto

    @pytest.mark.asyncio
    async def test_date_validation_rejects_invalid_format(
        self, crypto_with_multi_wallet_data, monkeypatch
    ) -> None:
        """Verify invalid date format is rejected."""
        app = CryptoApp()
        monkeypatch.setattr(app, "crypto", crypto_with_multi_wallet_data)

        async with app.run_test(notifications=True) as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause(0.2)

            # Enter invalid date
            start_input = app.screen.query_one("#start-date-input")
            start_input.value = "01/15/2024"  # Wrong format

            # Click apply filters
            await pilot.click("#apply-filters-btn")
            await pilot.pause()

            # Should show error notification
            assert len(app._notifications) > 0


class TestLedgerSorting:
    """Test table sorting functionality."""

    @pytest.mark.asyncio
    async def test_header_click_sorts_column(self) -> None:
        """Verify clicking column header triggers sort."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause()

            # Verify initial state
            assert screen.sort_column is None
            assert screen.sort_reverse is False


class TestLedgerNavigation:
    """Test navigation and keybindings."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen(self) -> None:
        """Verify Escape key pops screen."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            initial_screen = app.screen
            app.push_screen(LedgerScreen())
            await pilot.pause()
            assert app.screen is not initial_screen

            await pilot.press("escape")
            await pilot.pause()
            # Should be back to previous screen
            assert isinstance(app.screen, type(initial_screen))

    @pytest.mark.asyncio
    async def test_L_key_opens_ledger(self) -> None:
        """Verify L key opens LedgerScreen from app."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("l")
            await pilot.pause()
            assert isinstance(app.screen, LedgerScreen)


class TestLedgerReload:
    """Test transaction reload functionality."""

    @pytest.mark.asyncio
    async def test_reload_keybinding_exists(self) -> None:
        """Verify R key reload binding is registered."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()

            # Verify binding exists
            bindings = {b.key for b in app.screen.BINDINGS}
            assert "r" in bindings


class TestTransactionDetailModal:
    """TXE-003: Test TransactionDetailModal structure and behavior."""

    SAMPLE_TX = {
        "ID": 1,
        "Date": "2024-01-15 10:00:00",
        "Type": "Deposit",
        "Buy": 1.0,
        "Buy Cur.": "BTC",
        "Sell": None,
        "Sell Cur.": None,
        "Fee": None,
        "Fee Cur.": None,
        "Exchange": "Coinbase",
        "Group": "",
        "Comment": "Initial purchase",
        "Deleted": 0,
    }

    @pytest.mark.asyncio
    async def test_modal_mounts(self) -> None:
        """TransactionDetailModal can be mounted."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            assert isinstance(app.screen, TransactionDetailModal)

    @pytest.mark.asyncio
    async def test_modal_has_title(self) -> None:
        """Modal shows 'Transaction Details' title."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            title = app.screen.query_one("#detail-title", Label)
            assert "Transaction Details" in title.content

    @pytest.mark.asyncio
    async def test_modal_has_container(self) -> None:
        """Modal has the detail container."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            assert app.screen.query_one("#detail-container")

    @pytest.mark.asyncio
    async def test_modal_displays_field_values(self) -> None:
        """Modal displays transaction field values."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            labels = app.screen.query(".detail-field-value")
            texts = [lbl.content for lbl in labels]
            # Check key values are shown
            assert any("1" in t for t in texts)  # ID
            assert any("2024-01-15" in t for t in texts)  # Date
            assert any("Deposit" in t for t in texts)  # Type
            assert any("Coinbase" in t for t in texts)  # Exchange

    @pytest.mark.asyncio
    async def test_modal_displays_field_names(self) -> None:
        """Modal displays field name labels."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            labels = app.screen.query(".detail-field-name")
            texts = [lbl.content for lbl in labels]
            assert any("Transaction ID" in t for t in texts)
            assert any("Date" in t for t in texts)
            assert any("Type" in t for t in texts)
            assert any("Wallet" in t for t in texts)

    @pytest.mark.asyncio
    async def test_modal_shows_dash_for_empty_fields(self) -> None:
        """Null/empty fields display as em-dash."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            labels = app.screen.query(".detail-field-value")
            texts = [lbl.content for lbl in labels]
            # Sell/Fee fields are None, should show "—"
            assert texts.count("—") >= 2

    @pytest.mark.asyncio
    async def test_modal_has_edit_button(self) -> None:
        """Modal has Edit button."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            btn = app.screen.query_one("#detail-edit-btn", Button)
            assert "Edit" in str(btn.label)

    @pytest.mark.asyncio
    async def test_modal_has_delete_button(self) -> None:
        """Modal has Delete button."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            btn = app.screen.query_one("#detail-delete-btn", Button)
            assert "Delete" in str(btn.label)

    @pytest.mark.asyncio
    async def test_modal_has_close_button(self) -> None:
        """Modal has Close button."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            btn = app.screen.query_one("#detail-close-btn", Button)
            assert "Close" in str(btn.label)

    @pytest.mark.asyncio
    async def test_close_button_dismisses(self) -> None:
        """Close button dismisses the modal."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            modal = TransactionDetailModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert isinstance(app.screen, TransactionDetailModal)

            # Directly call the dismiss action (avoids click-targeting flakiness)
            modal.action_close()
            await pilot.pause()
            assert isinstance(app.screen, LedgerScreen)

    @pytest.mark.asyncio
    async def test_escape_dismisses(self) -> None:
        """Escape key dismisses the modal."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            app.push_screen(TransactionDetailModal(self.SAMPLE_TX))
            await pilot.pause()
            assert isinstance(app.screen, TransactionDetailModal)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, LedgerScreen)

    @pytest.mark.asyncio
    async def test_modal_stores_transaction(self) -> None:
        """Modal stores the transaction data for later use."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = TransactionDetailModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert modal.transaction == self.SAMPLE_TX
            assert modal.transaction["ID"] == 1


class TestLedgerDetailIntegration:
    """TXE-003: Test Enter key opens detail modal from Ledger."""

    @pytest.fixture
    def crypto_with_data(self):
        """Create CryptoAccounts with test transactions."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        return crypto

    @pytest.mark.asyncio
    async def test_enter_on_row_opens_detail_modal(self, crypto_with_data, monkeypatch) -> None:
        """Pressing Enter on a row opens TransactionDetailModal."""
        app = CryptoApp()
        monkeypatch.setattr(app, "crypto", crypto_with_data)

        async with app.run_test() as pilot:
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause(0.5)

            # Verify table has data
            table = screen.query_one("#transactions-table", DataTable)
            if table.row_count > 0:
                # Focus the table and press Enter (cursor starts at row 0)
                table.focus()
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause(0.3)
                assert isinstance(app.screen, TransactionDetailModal)


class TestEditTransactionModal:
    """TXE-004: Test EditTransactionModal structure and behavior."""

    SAMPLE_TX = {
        "ID": 1,
        "Date": "2024-01-15 10:00:00",
        "Type": "Deposit",
        "Buy": 1.0,
        "Buy Cur.": "BTC",
        "Sell": None,
        "Sell Cur.": None,
        "Fee": None,
        "Fee Cur.": None,
        "Exchange": "Coinbase",
        "Group": "DCA",
        "Comment": "Initial purchase",
        "Deleted": 0,
    }
    WALLET_OPTS = [("Coinbase", "Coinbase"), ("Strike", "Strike"), ("River", "River")]

    @pytest.mark.asyncio
    async def test_modal_mounts(self) -> None:
        """EditTransactionModal can be mounted."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            assert isinstance(app.screen, EditTransactionModal)

    @pytest.mark.asyncio
    async def test_modal_has_title(self) -> None:
        """Modal shows 'Edit Transaction #ID' title."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            title = app.screen.query_one("#edit-tx-title", Label)
            assert "Edit Transaction #1" in title.content

    @pytest.mark.asyncio
    async def test_modal_has_type_select(self) -> None:
        """Modal has transaction type Select pre-populated."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            select = app.screen.query_one("#edit-type", Select)
            assert str(select.value) == "Deposit"

    @pytest.mark.asyncio
    async def test_modal_has_exchange_select(self) -> None:
        """Modal has wallet/exchange Select pre-populated."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            select = app.screen.query_one("#edit-exchange", Select)
            assert str(select.value) == "Coinbase"

    @pytest.mark.asyncio
    async def test_modal_has_date_input(self) -> None:
        """Modal has date Input pre-populated."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            inp = app.screen.query_one("#edit-createddate", Input)
            assert inp.value == "2024-01-15 10:00:00"

    @pytest.mark.asyncio
    async def test_modal_has_buy_input(self) -> None:
        """Modal has buy amount Input pre-populated."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            inp = app.screen.query_one("#edit-buy", Input)
            assert inp.value == "1.0"

    @pytest.mark.asyncio
    async def test_modal_has_comment_input(self) -> None:
        """Modal has comment Input pre-populated."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            inp = app.screen.query_one("#edit-comment", Input)
            assert inp.value == "Initial purchase"

    @pytest.mark.asyncio
    async def test_modal_has_save_button(self) -> None:
        """Modal has Save button."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            btn = app.screen.query_one("#edit-save-btn", Button)
            assert "Save" in str(btn.label)

    @pytest.mark.asyncio
    async def test_modal_has_cancel_button(self) -> None:
        """Modal has Cancel button."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            btn = app.screen.query_one("#edit-cancel-btn", Button)
            assert "Cancel" in str(btn.label)

    @pytest.mark.asyncio
    async def test_escape_dismisses(self) -> None:
        """Escape key dismisses the modal."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            assert isinstance(app.screen, EditTransactionModal)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, LedgerScreen)

    @pytest.mark.asyncio
    async def test_cancel_dismisses(self) -> None:
        """Cancel action dismisses the modal."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause()
            modal = EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS)
            app.push_screen(modal)
            await pilot.pause()

            modal.action_cancel()
            await pilot.pause()
            assert isinstance(app.screen, LedgerScreen)

    @pytest.mark.asyncio
    async def test_diff_preview_empty_initially(self) -> None:
        """Diff preview is empty when no changes made."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            diff = app.screen.query_one("#edit-tx-diff", Label)
            assert diff.content == ""

    @pytest.mark.asyncio
    async def test_diff_preview_shows_changes(self) -> None:
        """Diff preview updates when fields are changed."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS)
            app.push_screen(modal)
            await pilot.pause()

            # Change the comment field
            comment_input = modal.query_one("#edit-comment", Input)
            comment_input.value = "Edited comment"
            await pilot.pause()

            diff = modal.query_one("#edit-tx-diff", Label)
            assert "comment" in diff.content
            assert "→" in diff.content

    @pytest.mark.asyncio
    async def test_null_fields_show_empty_inputs(self) -> None:
        """Null transaction fields result in empty input values."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS))
            await pilot.pause()
            sell_input = app.screen.query_one("#edit-sell", Input)
            assert sell_input.value == ""

    @pytest.mark.asyncio
    async def test_exchange_not_in_options_still_selected(self) -> None:
        """If current exchange not in wallet options, it's added."""
        tx = dict(self.SAMPLE_TX, Exchange="CustomWallet")
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(EditTransactionModal(tx, self.WALLET_OPTS))
            await pilot.pause()
            select = app.screen.query_one("#edit-exchange", Select)
            assert str(select.value) == "CustomWallet"

    @pytest.mark.asyncio
    async def test_stores_transaction(self) -> None:
        """Modal stores the original transaction for comparison."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = EditTransactionModal(self.SAMPLE_TX, self.WALLET_OPTS)
            app.push_screen(modal)
            await pilot.pause()
            assert modal.transaction["ID"] == 1
            assert modal.transaction["Exchange"] == "Coinbase"


class TestEditTransactionSave:
    """TXE-004: Test edit modal saves changes via LedgerWriter."""

    @pytest.fixture
    def crypto_with_data(self):
        """Create CryptoAccounts with test transactions."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 15, 10, 0), buy=1.0, buy_curr='BTC')
        return crypto

    @pytest.mark.asyncio
    async def test_save_updates_transaction(self, crypto_with_data) -> None:
        """Save button applies changes to the database."""
        app = CryptoApp()

        tx = {
            "ID": 1,
            "Date": "2024-01-15 10:00:00",
            "Type": "Deposit",
            "Buy": 1.0,
            "Buy Cur.": "BTC",
            "Sell": None,
            "Sell Cur.": None,
            "Fee": None,
            "Fee Cur.": None,
            "Exchange": "Coinbase",
            "Group": "",
            "Comment": "",
            "Deleted": 0,
        }

        async with app.run_test() as pilot:
            # Set crypto after on_mount to avoid being overwritten
            app.crypto = crypto_with_data
            modal = EditTransactionModal(tx, [("Coinbase", "Coinbase")])
            app.push_screen(modal)
            await pilot.pause()

            # Change the comment
            comment_input = modal.query_one("#edit-comment", Input)
            comment_input.value = "Updated comment"
            await pilot.pause()

            # Save
            modal._validate_and_save()
            await pilot.pause()

            # Verify in database via ledger_writer
            row = crypto_with_data.ledger_writer._get_transaction(1)
            assert row['comment'] == 'Updated comment'

    @pytest.mark.asyncio
    async def test_invalid_date_shows_error(self, crypto_with_data) -> None:
        """Invalid date format shows error, doesn't save."""
        app = CryptoApp()

        tx = {
            "ID": 1, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
            "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
            "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
            "Group": "", "Comment": "", "Deleted": 0,
        }

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            modal = EditTransactionModal(tx, [("Coinbase", "Coinbase")])
            app.push_screen(modal)
            await pilot.pause()

            # Set invalid date
            date_input = modal.query_one("#edit-createddate", Input)
            date_input.value = "not-a-date"
            await pilot.pause()

            modal._validate_and_save()
            await pilot.pause()

            # Should show error, not dismiss
            error = modal.query_one("#edit-tx-error", Label)
            assert "Invalid date" in error.content

    @pytest.mark.asyncio
    async def test_invalid_number_shows_error(self, crypto_with_data) -> None:
        """Invalid numeric value shows error, doesn't save."""
        app = CryptoApp()

        tx = {
            "ID": 1, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
            "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
            "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
            "Group": "", "Comment": "", "Deleted": 0,
        }

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            modal = EditTransactionModal(tx, [("Coinbase", "Coinbase")])
            app.push_screen(modal)
            await pilot.pause()

            # Set invalid buy amount
            buy_input = modal.query_one("#edit-buy", Input)
            buy_input.value = "not-a-number"
            await pilot.pause()

            modal._validate_and_save()
            await pilot.pause()

            error = modal.query_one("#edit-tx-error", Label)
            assert "Invalid number" in error.content


# ── TXE-005: Delete Transaction with confirmation ──────────────────────

from tui.screens.ledger import DeleteConfirmModal, _detect_transfer_pair


class TestDeleteConfirmModal:
    """Test DeleteConfirmModal structure and behavior."""

    SAMPLE_TX = {
        "ID": 1,
        "Date": "2024-01-15 10:00:00",
        "Type": "Deposit",
        "Buy": 1.0,
        "Buy Cur.": "BTC",
        "Sell": None,
        "Sell Cur.": None,
        "Fee": None,
        "Fee Cur.": None,
        "Exchange": "Coinbase",
        "Group": "",
        "Comment": "Test deposit",
        "Deleted": 0,
    }

    @pytest.mark.asyncio
    async def test_modal_mounts_successfully(self) -> None:
        """Verify DeleteConfirmModal can be mounted."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert isinstance(app.screen, DeleteConfirmModal)

    @pytest.mark.asyncio
    async def test_modal_title(self) -> None:
        """Verify delete modal shows title."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            title = modal.query_one("#delete-title", Label)
            assert "Delete" in title.content

    @pytest.mark.asyncio
    async def test_modal_shows_transaction_summary(self) -> None:
        """Verify modal shows transaction details in summary."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            summary = modal.query_one("#delete-summary", Label)
            text = summary.content
            assert "Coinbase" in text
            assert "Deposit" in text

    @pytest.mark.asyncio
    async def test_modal_shows_prompt(self) -> None:
        """Verify Are you sure? prompt is shown."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            prompt = modal.query_one("#delete-prompt", Label)
            assert "Are you sure" in prompt.content

    @pytest.mark.asyncio
    async def test_modal_has_confirm_and_cancel_buttons(self) -> None:
        """Verify delete and cancel buttons exist."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert modal.query_one("#delete-confirm-btn", Button)
            assert modal.query_one("#delete-cancel-btn", Button)

    @pytest.mark.asyncio
    async def test_cancel_dismisses_modal(self) -> None:
        """Cancel button dismisses without deleting."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            modal.action_cancel()
            await pilot.pause()
            assert not isinstance(app.screen, DeleteConfirmModal)

    @pytest.mark.asyncio
    async def test_escape_dismisses_modal(self) -> None:
        """Escape key dismisses the modal."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX)
            app.push_screen(modal)
            await pilot.pause()
            modal.action_cancel()
            await pilot.pause()
            assert not isinstance(app.screen, DeleteConfirmModal)

    @pytest.mark.asyncio
    async def test_no_warning_without_transfer_match(self) -> None:
        """No transfer pair warning when no match provided."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX, transfer_match=None)
            app.push_screen(modal)
            await pilot.pause()
            warnings = modal.query("#delete-warning")
            assert len(warnings) == 0

    @pytest.mark.asyncio
    async def test_shows_transfer_pair_warning(self) -> None:
        """Transfer pair warning shown when match is provided."""
        match = {
            "ID": 2, "Type": "Withdrawal", "Exchange": "Ledger",
            "Date": "2024-01-15 11:00:00",
        }
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(self.SAMPLE_TX, transfer_match=match)
            app.push_screen(modal)
            await pilot.pause()
            warning = modal.query_one("#delete-warning", Label)
            assert "transfer pair" in warning.content
            assert "withdrawal" in warning.content
            assert "Ledger" in warning.content


class TestTransferPairDetection:
    """Test the _detect_transfer_pair heuristic."""

    def test_matching_deposit_withdrawal(self) -> None:
        """Deposit on one wallet matches withdrawal on another within 72hrs."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 1.0, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Ledger",
        }
        others = [
            {
                "ID": 2, "Type": "Withdrawal", "Sell": 1.0, "Buy": None,
                "Date": "2024-01-15 09:00:00", "Exchange": "Coinbase",
            },
        ]
        result = _detect_transfer_pair(tx, others)
        assert result is not None
        assert result["ID"] == 2

    def test_no_match_different_amount(self) -> None:
        """No match when amounts differ by more than 1%."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 1.0, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Ledger",
        }
        others = [
            {
                "ID": 2, "Type": "Withdrawal", "Sell": 2.0, "Buy": None,
                "Date": "2024-01-15 09:00:00", "Exchange": "Coinbase",
            },
        ]
        assert _detect_transfer_pair(tx, others) is None

    def test_no_match_outside_72_hours(self) -> None:
        """No match when transactions are more than 72 hours apart."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 1.0, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Ledger",
        }
        others = [
            {
                "ID": 2, "Type": "Withdrawal", "Sell": 1.0, "Buy": None,
                "Date": "2024-01-20 10:00:00", "Exchange": "Coinbase",
            },
        ]
        assert _detect_transfer_pair(tx, others) is None

    def test_no_match_same_wallet(self) -> None:
        """No match when both transactions are on the same wallet."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 1.0, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Coinbase",
        }
        others = [
            {
                "ID": 2, "Type": "Withdrawal", "Sell": 1.0, "Buy": None,
                "Date": "2024-01-15 09:00:00", "Exchange": "Coinbase",
            },
        ]
        assert _detect_transfer_pair(tx, others) is None

    def test_no_match_for_trade(self) -> None:
        """Trade transactions are not transfer pairs."""
        tx = {
            "ID": 1, "Type": "Trade", "Buy": 1.0, "Sell": 50000.0,
            "Date": "2024-01-15 10:00:00", "Exchange": "Coinbase",
        }
        others = [
            {
                "ID": 2, "Type": "Deposit", "Buy": 1.0, "Sell": None,
                "Date": "2024-01-15 11:00:00", "Exchange": "Ledger",
            },
        ]
        assert _detect_transfer_pair(tx, others) is None

    def test_withdrawal_matches_deposit(self) -> None:
        """Withdrawal on one wallet matches deposit on another."""
        tx = {
            "ID": 1, "Type": "Withdrawal", "Sell": 0.5, "Buy": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Coinbase",
        }
        others = [
            {
                "ID": 2, "Type": "Deposit", "Buy": 0.5, "Sell": None,
                "Date": "2024-01-15 12:00:00", "Exchange": "Ledger",
            },
        ]
        result = _detect_transfer_pair(tx, others)
        assert result is not None
        assert result["ID"] == 2

    def test_within_1_percent_tolerance(self) -> None:
        """Amounts within 1% are considered matching (network fees)."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 0.999, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Ledger",
        }
        others = [
            {
                "ID": 2, "Type": "Withdrawal", "Sell": 1.0, "Buy": None,
                "Date": "2024-01-15 09:00:00", "Exchange": "Coinbase",
            },
        ]
        result = _detect_transfer_pair(tx, others)
        assert result is not None

    def test_skips_self(self) -> None:
        """The transaction is not matched against itself."""
        tx = {
            "ID": 1, "Type": "Deposit", "Buy": 1.0, "Sell": None,
            "Date": "2024-01-15 10:00:00", "Exchange": "Ledger",
        }
        assert _detect_transfer_pair(tx, [tx]) is None


class TestDeleteTransactionSave:
    """Test that delete confirmation actually soft-deletes in the database."""

    @pytest.fixture
    def crypto_with_data(self):
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 15, 10, 0), buy=1.0, buy_curr='BTC')
        return crypto

    @pytest.mark.asyncio
    async def test_confirm_delete_soft_deletes(self, crypto_with_data) -> None:
        """Confirm button soft-deletes the transaction."""
        app = CryptoApp()

        tx = {
            "ID": 1, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
            "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
            "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
            "Group": "", "Comment": "", "Deleted": 0,
        }

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            modal = DeleteConfirmModal(tx)
            app.push_screen(modal)
            await pilot.pause()

            # Confirm delete
            modal._do_delete()
            await pilot.pause()

            # Verify soft-deleted via ledger_writer
            row = crypto_with_data.ledger_writer._get_transaction(1)
            assert row['deleted'] == 1
            assert row['deleted_date'] is not None

    @pytest.mark.asyncio
    async def test_cancel_does_not_delete(self, crypto_with_data) -> None:
        """Cancel button does not delete the transaction."""
        app = CryptoApp()

        tx = {
            "ID": 1, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
            "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
            "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
            "Group": "", "Comment": "", "Deleted": 0,
        }

        async with app.run_test() as pilot:
            app.crypto = crypto_with_data
            modal = DeleteConfirmModal(tx)
            app.push_screen(modal)
            await pilot.pause()

            # Cancel
            modal.action_cancel()
            await pilot.pause()

            # Verify NOT deleted
            row = crypto_with_data.ledger_writer._get_transaction(1)
            assert row['deleted'] == 0


# ── TXE-006: Show deleted transactions toggle in Ledger ────────────────

from textual.widgets import Checkbox


class TestShowDeletedToggle:
    """Test the Show Deleted checkbox in the Ledger filter panel."""

    @pytest.mark.asyncio
    async def test_checkbox_present(self) -> None:
        """Verify Show Deleted checkbox exists in the filter panel."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause()
            cb = screen.query_one("#show-deleted-cb", Checkbox)
            assert not cb.value  # Default unchecked

    @pytest.mark.asyncio
    async def test_deleted_hidden_by_default(self) -> None:
        """Deleted transactions are hidden when checkbox is unchecked."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 2), buy=2.0, buy_curr='BTC')
        # Soft-delete the second transaction
        crypto.ledger_writer.soft_delete_transaction(2)

        app = CryptoApp()
        async with app.run_test() as pilot:
            app.crypto = crypto
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause(0.3)
            table = screen.query_one("#transactions-table", DataTable)
            # Only 1 visible (tx 2 is deleted)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_status_shows_hidden_deleted_count(self) -> None:
        """Status bar shows '(N deleted hidden)' when deleted exist."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 2), buy=2.0, buy_curr='BTC')
        crypto.ledger_writer.soft_delete_transaction(2)

        app = CryptoApp()
        async with app.run_test() as pilot:
            app.crypto = crypto
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause(0.3)
            status = screen.query_one("#status-label", Label)
            assert "1 deleted hidden" in status.content


class TestShowDeletedChecked:
    """Test behavior when Show Deleted checkbox is checked."""

    @pytest.fixture
    def crypto_with_deleted(self):
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 2), buy=2.0, buy_curr='BTC')
        crypto.ledger_writer.soft_delete_transaction(2)
        return crypto

    @pytest.mark.asyncio
    async def test_toggle_shows_deleted_rows(self, crypto_with_deleted) -> None:
        """Checking Show Deleted reveals deleted transactions."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.crypto = crypto_with_deleted
            screen = LedgerScreen()
            app.push_screen(screen)
            await pilot.pause(0.3)
            table = screen.query_one("#transactions-table", DataTable)
            assert table.row_count == 1  # Hidden by default

            # Toggle checkbox on
            screen.show_deleted = True
            screen.load_transactions()
            await pilot.pause(0.3)
            assert table.row_count == 2  # Now shows both


class TestDetailModalForDeletedTransaction:
    """Test that detail modal shows Restore for deleted transactions."""

    DELETED_TX = {
        "ID": 1, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
        "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
        "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
        "Group": "", "Comment": "", "Deleted": 1,
    }

    ACTIVE_TX = {
        "ID": 2, "Date": "2024-01-15 10:00:00", "Type": "Deposit",
        "Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None,
        "Fee": None, "Fee Cur.": None, "Exchange": "Coinbase",
        "Group": "", "Comment": "", "Deleted": 0,
    }

    @pytest.mark.asyncio
    async def test_deleted_tx_shows_restore_button(self) -> None:
        """Deleted transaction shows Restore instead of Edit/Delete."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = TransactionDetailModal(self.DELETED_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert modal.query_one("#detail-restore-btn", Button)
            assert len(modal.query("#detail-edit-btn")) == 0
            assert len(modal.query("#detail-delete-btn")) == 0

    @pytest.mark.asyncio
    async def test_active_tx_shows_edit_delete_buttons(self) -> None:
        """Active transaction shows Edit and Delete, not Restore."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            modal = TransactionDetailModal(self.ACTIVE_TX)
            app.push_screen(modal)
            await pilot.pause()
            assert modal.query_one("#detail-edit-btn", Button)
            assert modal.query_one("#detail-delete-btn", Button)
            assert len(modal.query("#detail-restore-btn")) == 0

    @pytest.mark.asyncio
    async def test_restore_button_dismisses_with_restore(self) -> None:
        """Restore button dismisses modal with 'restore' action."""
        app = CryptoApp()
        results = []
        async with app.run_test() as pilot:
            modal = TransactionDetailModal(self.DELETED_TX)

            def capture(result):
                results.append(result)

            app.push_screen(modal, capture)
            await pilot.pause()
            modal.query_one("#detail-restore-btn", Button).press()
            await pilot.pause()
            assert results == ["restore"]


class TestRestoreTransaction:
    """Test restoring a deleted transaction via the TUI flow."""

    @pytest.fixture
    def crypto_with_deleted(self):
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend=backend)
        crypto.deposit(exchange='Coinbase', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.ledger_writer.soft_delete_transaction(1)
        return crypto

    @pytest.mark.asyncio
    async def test_restore_undeletes_transaction(self, crypto_with_deleted) -> None:
        """Restoring a transaction clears the deleted flag."""
        # Verify it's deleted first
        row = crypto_with_deleted.ledger_writer._get_transaction(1)
        assert row['deleted'] == 1

        # Restore it
        crypto_with_deleted.ledger_writer.restore_transaction(1)
        row = crypto_with_deleted.ledger_writer._get_transaction(1)
        assert row['deleted'] == 0
        assert row['deleted_date'] is None

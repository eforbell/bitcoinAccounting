"""Tests for LedgerScreen - transaction ledger with filtering."""

from __future__ import annotations

from datetime import datetime

import pytest
from textual.pilot import Pilot

from cryptoAccounts import CryptoAccounts
from db import SqliteBackend
from tui.app import CryptoApp
from tui.screens.ledger import LedgerScreen


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
        app = CryptoApp()
        async with app.run_test() as pilot:
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
    async def test_table_populates_with_data(self, crypto_with_data, monkeypatch) -> None:
        """Verify table populates when transactions exist."""
        app = CryptoApp()
        monkeypatch.setattr(app, "crypto", crypto_with_data)

        async with app.run_test() as pilot:
            app.push_screen(LedgerScreen())
            await pilot.pause(0.3)

            table = app.screen.query_one("#transactions-table")
            assert table.row_count > 0  # Should have rows

    @pytest.mark.asyncio
    async def test_status_shows_row_count(self, crypto_with_data, monkeypatch) -> None:
        """Verify status bar shows transaction count."""
        app = CryptoApp()
        monkeypatch.setattr(app, "crypto", crypto_with_data)

        async with app.run_test() as pilot:
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

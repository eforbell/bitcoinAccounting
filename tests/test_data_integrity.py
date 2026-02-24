"""Tests for data integrity: wallet name normalization and wallet selectors.

DIF-001: Whitespace-padded exchange names are trimmed on storage and query.
DIF-002: Buy form uses wallet selector dropdown instead of free-text input.
DIF-003: Sell, Transfer, Interest forms use wallet selector dropdowns.
DIF-004: Import Wizard wallet selectors for withdraw-to and wallet-name.
"""
import sys
import os
import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from bitcoinAccounts import CryptoAccounts
from db import SqliteBackend
from db.queries.ledger import LedgerWriter
from db.queries.wallet import WalletQuery


class TestLedgerWriterWhitespaceNormalization:
    """LedgerWriter methods strip whitespace from exchange before storing."""

    def setup_method(self) -> None:
        self.backend = SqliteBackend(':memory:', auto_create_tables=True)
        self.writer = LedgerWriter(self.backend)

    def teardown_method(self) -> None:
        self.backend.close()

    def _get_stored_exchange(self) -> str:
        """Helper: read the exchange value from the last inserted row."""
        rows = self.backend.execute(
            "SELECT exchange FROM ledger ORDER BY rowid DESC LIMIT 1"
        )
        return rows[0]['exchange']

    def test_deposit_strips_whitespace(self) -> None:
        self.writer.deposit('2025-01-01', 1.0, 'BTC', '  Strike  ')
        assert self._get_stored_exchange() == 'Strike'

    def test_withdraw_strips_whitespace(self) -> None:
        self.writer.withdraw('2025-01-01', 0.5, 'BTC', 0.0001, 'BTC', ' Ledger\t')
        assert self._get_stored_exchange() == 'Ledger'

    def test_trade_strips_whitespace(self) -> None:
        self.writer.trade('2025-01-01', 0.01, 'BTC', 500.0, 'USD', 1.0, 'USD', '\tCoinbase ')
        assert self._get_stored_exchange() == 'Coinbase'

    def test_spend_strips_whitespace(self) -> None:
        self.writer.spend('2025-01-01', 0.001, 'BTC', 0.0, 'BTC', '  Sparrow ')
        assert self._get_stored_exchange() == 'Sparrow'

    def test_mining_strips_whitespace(self) -> None:
        self.writer.mining('2025-01-01', 0.0005, 'BTC', ' SlushPool  ')
        assert self._get_stored_exchange() == 'SlushPool'

    def test_interest_income_strips_whitespace(self) -> None:
        self.writer.interest_income('2025-01-01', 0.001, 'BTC', '  River ')
        assert self._get_stored_exchange() == 'River'

    def test_already_clean_name_unchanged(self) -> None:
        self.writer.deposit('2025-01-01', 1.0, 'BTC', 'Strike')
        assert self._get_stored_exchange() == 'Strike'


class TestWalletQueryWhitespaceNormalization:
    """WalletQuery.get_balance_by_account strips the account parameter."""

    def setup_method(self) -> None:
        self.backend = SqliteBackend(':memory:', auto_create_tables=True)
        self.writer = LedgerWriter(self.backend)
        self.wallet_query = WalletQuery(self.backend)

    def teardown_method(self) -> None:
        self.backend.close()

    def test_get_balance_by_account_strips_whitespace(self) -> None:
        self.writer.deposit('2025-01-01', 1.0, 'BTC', 'Strike')
        balance = self.wallet_query.get_balance_by_account('BTC', '  Strike  ')
        assert balance == pytest.approx(1.0)

    def test_get_balance_by_account_tabs_stripped(self) -> None:
        self.writer.deposit('2025-01-01', 0.5, 'BTC', 'Ledger')
        balance = self.wallet_query.get_balance_by_account('BTC', '\tLedger\t')
        assert balance == pytest.approx(0.5)


class TestImportTransactionsWhitespaceNormalization:
    """CryptoAccounts.import_transactions strips exchange whitespace."""

    def setup_method(self) -> None:
        self.backend = SqliteBackend(':memory:', auto_create_tables=True)
        self.crypto = CryptoAccounts(self.backend)

    def teardown_method(self) -> None:
        self.crypto.close()

    def test_import_strips_exchange_whitespace(self) -> None:
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01',
                'buy': 1.0,
                'buy_curr': 'BTC',
                'exchange': '  Strike  ',
            }
        ]
        result = self.crypto.import_transactions(transactions)
        assert result['imported'] == 1

        # Verify stored with trimmed name
        rows = self.backend.execute("SELECT exchange FROM ledger")
        assert rows[0]['exchange'] == 'Strike'

    def test_import_multiple_types_all_stripped(self) -> None:
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01',
                'buy': 10000.0,
                'buy_curr': 'USD',
                'exchange': ' Strike ',
            },
            {
                'trans_type': 'Trade',
                'created_date': '2025-01-02',
                'buy': 0.1,
                'buy_curr': 'BTC',
                'sell': 5000.0,
                'sell_curr': 'USD',
                'fee': 1.0,
                'fee_curr': 'USD',
                'exchange': '  Strike\t',
            },
            {
                'trans_type': 'Interest Income',
                'created_date': '2025-06-01',
                'buy': 0.001,
                'buy_curr': 'BTC',
                'exchange': '\tRiver  ',
            },
        ]
        result = self.crypto.import_transactions(transactions)
        assert result['imported'] == 3

        rows = self.backend.execute(
            "SELECT DISTINCT exchange FROM ledger ORDER BY exchange"
        )
        exchanges = [r['exchange'] for r in rows]
        assert exchanges == ['River', 'Strike']


# --- DIF-002: Wallet selector on Buy form ---

from tui.app import CryptoApp
from tui.screens.record_transaction import RecordTransactionScreen, NEW_WALLET_SENTINEL
from textual.widgets import Select, Input


def _make_app_with_wallets() -> CryptoApp:
    """Create a CryptoApp backed by in-memory SQLite with seed data."""
    app = CryptoApp()
    return app


class TestBuyFormWalletSelector:
    """DIF-002: Buy form uses Select dropdown for exchange."""

    @pytest.mark.asyncio
    async def test_buy_form_has_select_widget(self) -> None:
        """Buy form should have a Select widget for exchange, not a plain Input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, RecordTransactionScreen)
            # Should have a Select with id="exchange"
            sel = screen.query_one("#exchange", Select)
            assert sel is not None

    @pytest.mark.asyncio
    async def test_buy_form_select_has_new_wallet_option(self) -> None:
        """The exchange Select should include '+ New Wallet...' option."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            sel = screen.query_one("#exchange", Select)
            # Check that NEW_WALLET_SENTINEL is among the option values
            # sel._options is a list of (prompt, value) tuples
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_buy_form_new_wallet_input_hidden_by_default(self) -> None:
        """New wallet input row should be hidden when an existing wallet is selected."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            new_row = screen.query_one("#new-wallet-row")
            # If there are wallets in the DB, the new wallet row should be hidden
            # If DB is empty, it should be visible (only '+ New Wallet...' available)
            sel = screen.query_one("#exchange", Select)
            if sel.value == NEW_WALLET_SENTINEL:
                assert new_row.has_class("visible")
            else:
                assert not new_row.has_class("visible")

    @pytest.mark.asyncio
    async def test_buy_form_new_wallet_input_shown_on_new_wallet_select(self) -> None:
        """Selecting '+ New Wallet...' should show the new wallet input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            # Programmatically set the select to new wallet
            sel = screen.query_one("#exchange", Select)
            sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-wallet-row")
            assert new_row.has_class("visible")


# --- DIF-003: Wallet selector on Sell, Transfer, Interest forms ---


class TestSellFormWalletSelector:
    """DIF-003: Sell form uses Select dropdown for exchange."""

    @pytest.mark.asyncio
    async def test_sell_form_has_select_widget(self) -> None:
        """Sell form should have a Select widget for exchange."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, RecordTransactionScreen)
            screen._current_type = "sell"
            screen._show_sell_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            assert sel is not None

    @pytest.mark.asyncio
    async def test_sell_form_select_has_new_wallet_option(self) -> None:
        """Sell form exchange Select should include '+ New Wallet...'."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "sell"
            screen._show_sell_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_sell_form_new_wallet_toggle(self) -> None:
        """Selecting '+ New Wallet...' on sell form shows new wallet input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "sell"
            screen._show_sell_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-wallet-row")
            assert new_row.has_class("visible")


class TestTransferFormWalletSelector:
    """DIF-003: Transfer form uses Select dropdowns for from/to wallets."""

    @pytest.mark.asyncio
    async def test_transfer_form_has_from_wallet_select(self) -> None:
        """Transfer form should have a Select widget for from_wallet."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, RecordTransactionScreen)
            screen._current_type = "transfer"
            screen._show_transfer_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#from_wallet", Select)
            assert sel is not None
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_transfer_form_has_to_wallet_select(self) -> None:
        """Transfer form should have a Select widget for to_wallet."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "transfer"
            screen._show_transfer_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#to_wallet", Select)
            assert sel is not None
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_transfer_form_new_wallet_toggles(self) -> None:
        """Both from_wallet and to_wallet show new wallet input on sentinel."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "transfer"
            screen._show_transfer_form()
            await pilot.pause(0.3)

            # Toggle from_wallet
            from_sel = screen.query_one("#from_wallet", Select)
            from_sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            from_row = screen.query_one("#new-from-wallet-row")
            assert from_row.has_class("visible")

            # Toggle to_wallet
            to_sel = screen.query_one("#to_wallet", Select)
            to_sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            to_row = screen.query_one("#new-to-wallet-row")
            assert to_row.has_class("visible")


class TestInterestFormWalletSelector:
    """DIF-003: Interest form uses Select dropdown for exchange."""

    @pytest.mark.asyncio
    async def test_interest_form_has_select_widget(self) -> None:
        """Interest form should have a Select widget for exchange."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, RecordTransactionScreen)
            screen._current_type = "interest"
            screen._show_interest_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            assert sel is not None

    @pytest.mark.asyncio
    async def test_interest_form_select_has_new_wallet_option(self) -> None:
        """Interest form exchange Select should include '+ New Wallet...'."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "interest"
            screen._show_interest_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_interest_form_new_wallet_toggle(self) -> None:
        """Selecting '+ New Wallet...' on interest form shows new wallet input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.5)
            screen = app.screen
            screen._current_type = "interest"
            screen._show_interest_form()
            await pilot.pause(0.3)
            sel = screen.query_one("#exchange", Select)
            sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-wallet-row")
            assert new_row.has_class("visible")


# --- DIF-004: Wallet selector on Import Wizard ---

from tui.screens.imports import ImportWizardScreen, _WIZARD_WALLET_MAP
from textual.containers import Horizontal


class TestImportWizardWithdrawToSelector:
    """DIF-004: Import Wizard step 2 uses wallet selector for withdraw-to."""

    @pytest.mark.asyncio
    async def test_wizard_step2_has_withdraw_to_select(self) -> None:
        """Step 2 should have a Select for withdraw-to with sentinel option."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, ImportWizardScreen)
            # Manually advance to step 2
            screen.show_step_2()
            await pilot.pause(0.3)
            sel = screen.query_one("#select-withdraw-to", Select)
            assert sel is not None
            option_values = [opt[1] for opt in sel._options]
            assert NEW_WALLET_SENTINEL in option_values

    @pytest.mark.asyncio
    async def test_wizard_withdraw_to_new_wallet_row_hidden_by_default(self) -> None:
        """Withdraw-to new-wallet row should be hidden by default (allow_blank)."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, ImportWizardScreen)
            screen.show_step_2()
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-withdraw-to-row", Horizontal)
            # allow_blank=True means default is BLANK; row hidden via CSS
            assert not new_row.display

    @pytest.mark.asyncio
    async def test_wizard_withdraw_to_new_wallet_toggle(self) -> None:
        """Selecting '+ New Wallet...' on withdraw-to shows the input row."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, ImportWizardScreen)
            screen.show_step_2()
            await pilot.pause(0.3)
            sel = screen.query_one("#select-withdraw-to", Select)
            sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-withdraw-to-row", Horizontal)
            assert new_row.display

    @pytest.mark.asyncio
    async def test_wizard_withdraw_to_input_strips_whitespace(self) -> None:
        """New wallet input value should be stripped of whitespace."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, ImportWizardScreen)
            screen.show_step_2()
            await pilot.pause(0.3)
            sel = screen.query_one("#select-withdraw-to", Select)
            sel.value = NEW_WALLET_SENTINEL
            await pilot.pause(0.3)
            inp = screen.query_one("#new-withdraw-to-input", Input)
            inp.value = "  My Cold Storage  "
            val = screen._get_wizard_wallet_value("select-withdraw-to")
            assert val == "My Cold Storage"


class TestImportWizardWalletNameSelector:
    """DIF-004: Import Wizard wallet-name selector for wallet imports."""

    @pytest.mark.asyncio
    async def test_wizard_wallet_name_empty_db_shows_new_wallet_row(self) -> None:
        """With empty DB, wallet-name new-wallet row should be visible with placeholder."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, ImportWizardScreen)
            # Simulate wallet import parser
            from unittest.mock import MagicMock
            screen.parser = MagicMock()
            screen.parser.source_type = 'wallet'
            screen.parser.name = 'Ledger Live'
            screen.parsed_transactions = [{'trans_type': 'Deposit'}]
            # Clear wallet list to simulate empty DB
            screen.wallet_names = []
            screen.show_step_2()
            await pilot.pause(0.3)
            new_row = screen.query_one("#new-wallet-name-row", Horizontal)
            assert new_row.display
            inp = screen.query_one("#new-wallet-name-input", Input)
            assert "No wallets yet" in inp.placeholder

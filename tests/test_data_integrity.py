"""Tests for data integrity: wallet name normalization and wallet selectors.

DIF-001: Whitespace-padded exchange names are trimmed on storage and query.
DIF-002: Buy form uses wallet selector dropdown instead of free-text input.
"""
import sys
import os
import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from cryptoAccounts import CryptoAccounts
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

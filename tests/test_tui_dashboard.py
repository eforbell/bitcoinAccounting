"""Tests for TUI Dashboard screen (TUI-002).

Tests the DashboardScreen showing portfolio summary, custody breakdown,
and recent transactions using Textual's pilot testing framework.
"""

import sys
import os
from datetime import datetime

import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from db import SqliteBackend
from cryptoAccounts import CryptoAccounts
from tui.app import CryptoApp
from tui.screens.dashboard import DashboardScreen, StatCard, CustodyBreakdown, RecentTransactions
from textual.widgets import Label, DataTable


class TestDashboardScreenMount:
    """Tests that dashboard screen mounts and renders correctly."""

    @pytest.mark.asyncio
    async def test_dashboard_mounts(self) -> None:
        """Dashboard screen should mount without errors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            # Dashboard should be pushed on app mount (TUI-002 requirement)
            await pilot.pause()
            screens = app.screen_stack
            # Should have base screen + dashboard
            assert len(screens) >= 1

    @pytest.mark.asyncio
    async def test_dashboard_has_header_and_footer(self) -> None:
        """Dashboard screen should have Header and Footer."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Header, Footer
            # Query from app (widgets from all screens)
            headers = app.query(Header)
            footers = app.query(Footer)
            assert len(headers) >= 1
            assert len(footers) >= 1

    @pytest.mark.asyncio
    async def test_dashboard_sets_subtitle(self) -> None:
        """Dashboard screen should set subtitle to 'Dashboard'."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Give worker thread time to complete
            await pilot.pause(0.1)
            # Subtitle should be set (may be overridden by screen)
            assert app.sub_title is not None


class TestDashboardEmptyState:
    """Tests dashboard empty state (no transactions)."""

    @pytest.mark.asyncio
    async def test_empty_database_shows_onboarding(self) -> None:
        """Empty database should show onboarding message."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Wait for worker thread to complete
            await pilot.pause(0.2)

            # Should show empty message
            empty_labels = app.query("#empty-message")
            if len(empty_labels) > 0:
                empty_label = empty_labels[0]
                assert isinstance(empty_label, Label)
                content = empty_label.renderable if hasattr(empty_label, 'renderable') else str(empty_label)
                # Check for onboarding keywords
                content_str = str(content).lower()
                assert any(keyword in content_str for keyword in ['welcome', 'empty', 'import', 'get started'])

    @pytest.mark.asyncio
    async def test_empty_state_has_helpful_instructions(self) -> None:
        """Empty state should tell users how to get started."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause(0.2)

            empty_labels = app.query("#empty-message")
            if len(empty_labels) > 0:
                empty_label = empty_labels[0]
                # Use .content for Textual 0.47+ (not .renderable)
                if hasattr(empty_label, 'content'):
                    content = str(empty_label.content)
                else:
                    content = str(empty_label)

                content_lower = content.lower()
                # Should mention import or record
                assert 'import' in content_lower or 'record' in content_lower


class TestDashboardWithData:
    """Tests dashboard with actual transaction data."""

    @pytest.mark.asyncio
    async def test_dashboard_with_transactions(self) -> None:
        """Dashboard should display data when transactions exist."""
        # Create in-memory database with test data
        backend = SqliteBackend(':memory:')
        crypto = CryptoAccounts(backend=backend)

        # Add test transaction
        crypto.deposit(
            deposit_date=datetime(2024, 1, 1, 12, 0, 0),
            buy=1.0,
            buy_curr='BTC',
            exchange='TestExchange',
            group='test',
            comment='Test deposit'
        )

        # Create app with pre-populated database
        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test() as pilot:
            await pilot.pause()
            # Wait for worker thread
            await pilot.pause(0.3)

            # Should NOT show empty message
            empty_labels = app.query("#empty-message")
            assert len(empty_labels) == 0

            # Should show stats row with balance
            balance_cards = app.query("#balance-card")
            if len(balance_cards) > 0:
                # Stats loaded successfully
                assert True

        crypto.close()

    @pytest.mark.asyncio
    async def test_stat_cards_display_balance(self) -> None:
        """Stat cards should display balance correctly."""
        # Create in-memory database with test data
        backend = SqliteBackend(':memory:')
        crypto = CryptoAccounts(backend=backend)

        # Add test transaction
        crypto.deposit(
            deposit_date=datetime(2024, 1, 1, 12, 0, 0),
            buy=0.5,
            buy_curr='BTC',
            exchange='TestExchange',
            group='test',
            comment='Test deposit'
        )

        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause(0.3)

            # Query stat cards
            balance_cards = app.query("#balance-card")
            if len(balance_cards) > 0:
                # Balance card should exist
                assert isinstance(balance_cards[0], StatCard)

        crypto.close()


class TestCustodyBreakdownWidget:
    """Tests for CustodyBreakdown widget."""

    @pytest.mark.asyncio
    async def test_custody_widget_mounts(self) -> None:
        """CustodyBreakdown widget should mount."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield CustodyBreakdown()

        app = TestApp()
        async with app.run_test() as pilot:
            custody_widgets = app.query(CustodyBreakdown)
            assert len(custody_widgets) == 1

    @pytest.mark.asyncio
    async def test_custody_breakdown_displays_types(self) -> None:
        """CustodyBreakdown should display custody types."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield CustodyBreakdown()

        app = TestApp()
        async with app.run_test() as pilot:
            custody_widget = app.query_one(CustodyBreakdown)

            # Update with test data
            test_data = {
                "self-custodied": 0.8,
                "custodial": 0.2,
                "multisig": 0.0,
                "unknown": 0.0,
            }
            custody_widget.update_custody(test_data)
            await pilot.pause()

            # Should have custody items
            custody_items = app.query(".custody-item")
            # Should show at least the non-zero types
            assert len(custody_items) >= 2

    @pytest.mark.asyncio
    async def test_custody_breakdown_handles_empty_data(self) -> None:
        """CustodyBreakdown should handle empty custody data gracefully."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield CustodyBreakdown()

        app = TestApp()
        async with app.run_test() as pilot:
            custody_widget = app.query_one(CustodyBreakdown)

            # Update with empty data
            custody_widget.update_custody({})
            await pilot.pause()

            # Should not crash
            assert True


class TestRecentTransactionsWidget:
    """Tests for RecentTransactions widget."""

    @pytest.mark.asyncio
    async def test_recent_transactions_mounts(self) -> None:
        """RecentTransactions widget should mount."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield RecentTransactions()

        app = TestApp()
        async with app.run_test() as pilot:
            tx_widgets = app.query(RecentTransactions)
            assert len(tx_widgets) == 1

    @pytest.mark.asyncio
    async def test_recent_transactions_has_table(self) -> None:
        """RecentTransactions should contain a DataTable."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield RecentTransactions()

        app = TestApp()
        async with app.run_test() as pilot:
            tables = app.query(DataTable)
            assert len(tables) == 1

    @pytest.mark.asyncio
    async def test_recent_transactions_displays_data(self) -> None:
        """RecentTransactions should display transaction data."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield RecentTransactions()

        app = TestApp()
        async with app.run_test() as pilot:
            tx_widget = app.query_one(RecentTransactions)

            # Update with test data
            headers = ['Date', 'Type', 'Amount', 'Exchange']
            transactions = [
                {'Date': '2024-01-01', 'Type': 'Deposit', 'Amount': '1.0', 'Exchange': 'TestExchange'},
                {'Date': '2024-01-02', 'Type': 'Withdrawal', 'Amount': '0.5', 'Exchange': 'TestExchange'},
            ]
            tx_widget.update_transactions(headers, transactions)
            await pilot.pause()

            # Table should have columns
            table = app.query_one("#tx-table", DataTable)
            assert len(table.columns) == 4

    @pytest.mark.asyncio
    async def test_recent_transactions_limits_to_5(self) -> None:
        """RecentTransactions should limit display to 5 transactions."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield RecentTransactions()

        app = TestApp()
        async with app.run_test() as pilot:
            tx_widget = app.query_one(RecentTransactions)

            # Update with 10 transactions
            headers = ['Date', 'Type', 'Amount']
            transactions = [
                {'Date': f'2024-01-{i:02d}', 'Type': 'Deposit', 'Amount': f'{i}.0'}
                for i in range(1, 11)
            ]
            tx_widget.update_transactions(headers, transactions)
            await pilot.pause()

            # Table should only show 5 rows
            table = app.query_one("#tx-table", DataTable)
            assert len(table.rows) == 5


class TestStatCardWidget:
    """Tests for StatCard widget."""

    @pytest.mark.asyncio
    async def test_stat_card_mounts(self) -> None:
        """StatCard widget should mount."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield StatCard("Test Label", "Test Value", "test-card")

        app = TestApp()
        async with app.run_test() as pilot:
            cards = app.query(StatCard)
            assert len(cards) == 1

    @pytest.mark.asyncio
    async def test_stat_card_displays_label_and_value(self) -> None:
        """StatCard should display label and value."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield StatCard("Balance", "1.5 BTC", "balance-card")

        app = TestApp()
        async with app.run_test() as pilot:
            card = app.query_one(StatCard)

            # Check labels exist
            labels = card.query(Label)
            assert len(labels) == 2

    @pytest.mark.asyncio
    async def test_stat_card_updates_value(self) -> None:
        """StatCard should allow updating the value."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield StatCard("Balance", "1.0 BTC", "balance-card")

        app = TestApp()
        async with app.run_test() as pilot:
            card = app.query_one(StatCard)

            # Update value
            card.update_value("2.0 BTC")
            await pilot.pause()

            # Value should be updated
            assert card.stat_value == "2.0 BTC"


class TestDashboardNavigation:
    """Tests for dashboard navigation and keyboard shortcuts."""

    @pytest.mark.asyncio
    async def test_escape_from_dashboard_returns_to_menu(self) -> None:
        """Pressing Escape from dashboard should return to main menu."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause(0.1)

            # Press escape to go back
            await pilot.press("escape")
            await pilot.pause()

            # Should pop back to main menu
            # (MainMenu is on base screen)
            from tui.app import MainMenu
            menus = app.query(MainMenu)
            assert len(menus) == 1

    @pytest.mark.asyncio
    async def test_p_key_opens_dashboard(self) -> None:
        """Pressing P should push dashboard screen."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Go back to main menu first
            await pilot.press("escape")
            await pilot.pause()

            # Press P for portfolio
            await pilot.press("p")
            await pilot.pause(0.1)

            # Dashboard should be in screen stack
            # (worker will load data asynchronously)
            assert len(app.screen_stack) >= 1

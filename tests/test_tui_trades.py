"""Tests for TUI trades and exchange liquidity screen."""

import pytest
from datetime import datetime

from textual.widgets import DataTable, Label, Select, Button
from tui.screens.trades import TradesScreen
from tui.app import CryptoApp

from db.sqlite import SqliteBackend


class TestTradesScreenMount:
    """Test that the trades screen mounts and renders properly."""

    @pytest.mark.asyncio
    async def test_trades_screen_mounts(self):
        """Test that trades screen mounts successfully."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Push trades screen
            app.push_screen(TradesScreen())
            await pilot.pause(0.1)

            # Verify screen is active
            assert isinstance(app.screen, TradesScreen)

    @pytest.mark.asyncio
    async def test_trades_screen_has_header_footer(self):
        """Test that trades screen has header and footer."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.1)

            # Should have header and footer
            from textual.widgets import Header, Footer
            assert app.screen.query_one(Header)
            assert app.screen.query_one(Footer)

    @pytest.mark.asyncio
    async def test_trades_screen_title(self):
        """Test that trades screen has correct title."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.1)

            # Check for screen title label
            title_labels = app.screen.query(".screen-title")
            assert len(title_labels) > 0
            title = title_labels[0]
            assert isinstance(title, Label)
            # Use .content instead of .renderable (Textual 7.5+)
            assert "Trades" in str(title.content)


class TestTradesFilterControls:
    """Test trades screen filter controls."""

    @pytest.mark.asyncio
    async def test_coin_selector_present(self):
        """Test that coin selector is present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.1)

            # Should have coin selector
            coin_select = app.screen.query_one("#coin-select", Select)
            assert coin_select is not None

    @pytest.mark.asyncio
    async def test_view_buttons_present(self):
        """Test that view toggle buttons are present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.1)

            # Should have both view buttons
            trades_btn = app.screen.query_one("#view-trades-btn", Button)
            liquidity_btn = app.screen.query_one("#view-liquidity-btn", Button)
            assert trades_btn is not None
            assert liquidity_btn is not None


class TestTradesView:
    """Test trades history view."""

    @pytest.mark.asyncio
    async def test_trades_view_default(self):
        """Test that trades view is shown by default."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)  # Give time for data loading

            # Should have trades table
            try:
                table = app.screen.query_one("#trades-table", DataTable)
                assert table is not None
            except Exception:
                # Table might not exist if no data - check for status instead
                status = app.screen.query_one("#trades-status", Label)
                assert status is not None

    @pytest.mark.asyncio
    async def test_trades_view_with_data(self):
        """Test trades view with sample data."""
        # Create in-memory database with test data
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        from cryptoAccounts import CryptoAccounts
        crypto = CryptoAccounts(backend=backend)

        # Import a trade
        crypto.import_transactions([{
            'trans_type': 'Trade',
            'created_date': '2024-01-15 10:00:00',
            'buy': 0.1,
            'buy_curr': 'BTC',
            'sell': 5000.0,
            'sell_curr': 'USD',
            'fee': 0.0,
            'fee_curr': '',
            'exchange': 'Strike',
            'wallet': 'Strike',
            'group': '',
            'comment': 'Test trade'
        }])

        # Create app with this database
        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.5)  # Give time for async data loading

            # Should have trades table with data
            table = app.screen.query_one("#trades-table", DataTable)
            assert table is not None
            # Table should have columns
            assert len(table.columns) > 0

        crypto.close()

    @pytest.mark.asyncio
    async def test_trades_empty_state(self):
        """Test trades view with no data shows appropriate message."""
        # Create in-memory database with no trades
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        from cryptoAccounts import CryptoAccounts
        crypto = CryptoAccounts(backend=backend)

        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.5)

            # Status should indicate no trades
            status = app.screen.query_one("#trades-status", Label)
            assert "No trades" in str(status.content)

        crypto.close()


class TestLiquidityView:
    """Test exchange liquidity view."""

    @pytest.mark.asyncio
    async def test_switch_to_liquidity_view(self):
        """Test switching to liquidity view."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Click liquidity button
            liquidity_btn = app.screen.query_one("#view-liquidity-btn", Button)
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.3)

            # Should now have liquidity table
            try:
                table = app.screen.query_one("#liquidity-table", DataTable)
                assert table is not None
            except Exception:
                # Table might not exist if no data - check for status
                status = app.screen.query_one("#liquidity-status", Label)
                assert status is not None

    @pytest.mark.asyncio
    async def test_liquidity_view_with_data(self):
        """Test liquidity view with sample purchase data."""
        # Create in-memory database with test data
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        from cryptoAccounts import CryptoAccounts
        crypto = CryptoAccounts(backend=backend)

        # Import purchases (buys) at different exchanges
        crypto.import_transactions([
            {
                'trans_type': 'Trade',
                'created_date': '2024-01-15 10:00:00',
                'buy': 0.5,
                'buy_curr': 'BTC',
                'sell': 25000.0,
                'sell_curr': 'USD',
                'fee': 0.0,
                'fee_curr': '',
                'exchange': 'Strike',
                'wallet': 'Strike',
                'group': '',
                'comment': 'Test purchase'
            },
            {
                'trans_type': 'Trade',
                'created_date': '2024-02-01 12:00:00',
                'buy': 0.3,
                'buy_curr': 'BTC',
                'sell': 18000.0,
                'sell_curr': 'USD',
                'fee': 0.0,
                'fee_curr': '',
                'exchange': 'Kraken',
                'wallet': 'Kraken',
                'group': '',
                'comment': 'Test purchase 2'
            }
        ])

        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Switch to liquidity view
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.5)

            # Should have liquidity table with data
            table = app.screen.query_one("#liquidity-table", DataTable)
            assert table is not None
            assert len(table.columns) > 0

            # Should have summary panel
            summary = app.screen.query_one("#liquidity-summary")
            assert summary is not None

        crypto.close()

    @pytest.mark.asyncio
    async def test_liquidity_empty_state(self):
        """Test liquidity view with no purchases shows appropriate message."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        from cryptoAccounts import CryptoAccounts
        crypto = CryptoAccounts(backend=backend)

        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Switch to liquidity view
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.5)

            # Status should indicate no purchase history
            status = app.screen.query_one("#liquidity-status", Label)
            assert "No purchase history" in str(status.content)

        crypto.close()


class TestTradesNavigation:
    """Test trades screen navigation."""

    @pytest.mark.asyncio
    async def test_escape_key_returns(self):
        """Test that escape key returns to previous screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Should start on dashboard
            from tui.screens import DashboardScreen
            assert isinstance(app.screen, DashboardScreen)

            # Push trades screen
            app.push_screen(TradesScreen())
            await pilot.pause(0.1)
            assert isinstance(app.screen, TradesScreen)

            # Press escape
            await pilot.press("escape")
            await pilot.pause(0.1)

            # Should be back on dashboard
            assert isinstance(app.screen, DashboardScreen)

    @pytest.mark.asyncio
    async def test_x_key_opens_trades(self):
        """Test that X key opens trades screen from dashboard."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Press X to open trades
            await pilot.press("x")
            await pilot.pause(0.3)

            # Should be on trades screen
            assert isinstance(app.screen, TradesScreen)


class TestTradesKeyboardShortcuts:
    """Test trades screen keyboard shortcuts."""

    @pytest.mark.asyncio
    async def test_t_key_switches_to_trades(self):
        """Test that T key switches to trades view."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Switch to liquidity first
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.3)

            # Press T to go back to trades
            await pilot.press("t")
            await pilot.pause(0.3)

            # Should be on trades view (has trades-table)
            try:
                table = app.screen.query_one("#trades-table", DataTable)
                assert table is not None
            except Exception:
                status = app.screen.query_one("#trades-status", Label)
                assert status is not None

    @pytest.mark.asyncio
    async def test_e_key_switches_to_liquidity(self):
        """Test that E key switches to liquidity view."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Press E to go to liquidity
            await pilot.press("e")
            await pilot.pause(0.3)

            # Should be on liquidity view (has liquidity-table)
            try:
                table = app.screen.query_one("#liquidity-table", DataTable)
                assert table is not None
            except Exception:
                status = app.screen.query_one("#liquidity-status", Label)
                assert status is not None

    @pytest.mark.asyncio
    async def test_r_key_reloads_view(self):
        """Test that R key reloads current view."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.3)

            # Press R to reload
            await pilot.press("r")
            await pilot.pause(0.3)

            # Screen should still be TradesScreen (reload doesn't navigate away)
            assert isinstance(app.screen, TradesScreen)

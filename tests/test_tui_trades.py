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
        """Test trades view populates table with trade data."""
        app = CryptoApp()

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.2)
            # Cancel real DB workers to avoid race conditions
            app.workers.cancel_all()

            screen = app.screen
            assert isinstance(screen, TradesScreen)

            # Directly call update method (call_from_thread unreliable in test runner)
            screen._update_trades_table([{
                'date': '2024-01-15 10:00:00',
                'quantity': 0.1,
                'trade_curr': 'USD',
                'unit_cost': 50000.0,
                'total_cost': 5000.0,
                'exchange': 'Strike',
            }])
            await pilot.pause(0.1)

            table = screen.query_one("#trades-table", DataTable)
            assert len(table.columns) > 0
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_trades_empty_state(self):
        """Test trades view with no data shows appropriate message."""
        app = CryptoApp()

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.2)
            app.workers.cancel_all()

            screen = app.screen
            assert isinstance(screen, TradesScreen)

            # Directly call update with empty list
            screen._update_trades_table([])
            await pilot.pause(0.1)

            status = screen.query_one("#trades-status", Label)
            assert "No trades" in str(status.content)


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
            app.workers.cancel_all()

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
        """Test liquidity view populates table with exchange data."""
        app = CryptoApp()

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.2)
            app.workers.cancel_all()

            screen = app.screen
            assert isinstance(screen, TradesScreen)

            # Switch to liquidity view
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.2)
            app.workers.cancel_all()

            # Directly call update method
            screen._update_liquidity_table(
                [
                    {'exchange': 'Strike', 'purchased': 0.5, 'balance': 0.0, 'avg_cost': 50000.0},
                    {'exchange': 'Kraken', 'purchased': 0.3, 'balance': 0.0, 'avg_cost': 60000.0},
                ],
                {
                    'total_purchased': 0.8,
                    'total_usd_spent': 43000.0,
                    'total_avg_cost': 53750.0,
                    'still_at_exchanges': 0.0,
                    'in_cold_storage': 0.8,
                    'total_holdings': 0.8,
                }
            )
            await pilot.pause(0.1)

            table = screen.query_one("#liquidity-table", DataTable)
            assert len(table.columns) > 0

            summary = screen.query_one("#liquidity-summary")
            assert summary is not None

    @pytest.mark.asyncio
    async def test_liquidity_empty_state(self):
        """Test liquidity view with no purchases shows appropriate message."""
        app = CryptoApp()

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(TradesScreen())
            await pilot.pause(0.2)
            app.workers.cancel_all()

            screen = app.screen
            assert isinstance(screen, TradesScreen)

            # Switch to liquidity view
            await pilot.click("#view-liquidity-btn")
            await pilot.pause(0.2)
            app.workers.cancel_all()

            # Directly call update with empty list
            screen._update_liquidity_table([], {})
            await pilot.pause(0.1)

            status = screen.query_one("#liquidity-status", Label)
            assert "No purchase history" in str(status.content)


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

            # Cancel background workers before switching views to avoid race conditions
            app.workers.cancel_all()
            await pilot.pause(0.1)

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

            # Cancel background workers before switching views to avoid race conditions
            app.workers.cancel_all()
            await pilot.pause(0.1)

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

            # Cancel background workers to avoid race conditions
            app.workers.cancel_all()
            await pilot.pause(0.1)

            # Press R to reload
            await pilot.press("r")
            await pilot.pause(0.3)

            # Screen should still be TradesScreen (reload doesn't navigate away)
            assert isinstance(app.screen, TradesScreen)

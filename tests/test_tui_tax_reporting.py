"""Tests for TUI Tax Reporting screen (TUI-010)."""

from __future__ import annotations

import pytest
from datetime import datetime

from db import SqliteBackend
from cryptoAccounts import CryptoAccounts
from tui.app import CryptoApp
from tui.screens import TaxReportingScreen


@pytest.fixture
def crypto_with_trades() -> CryptoAccounts:
    """Create in-memory CryptoAccounts with trade data for tax testing."""
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    crypto = CryptoAccounts(backend=backend)

    # Import purchase transactions
    transactions = [
        {
            "trans_type": "Deposit",
            "created_date": "2024-01-10 10:00:00",
            "exchange": "Strike",
            "buy": 10000.0,
            "buy_curr": "USD",
            "group": "",
            "comment": "USD deposit",
        },
        {
            "trans_type": "Trade",
            "created_date": "2024-01-10 10:30:00",
            "exchange": "Strike",
            "buy": 0.25,
            "buy_curr": "BTC",
            "sell": 10000.0,
            "sell_curr": "USD",
            "fee": 10.0,
            "fee_curr": "USD",
            "group": "",
            "comment": "Buy BTC @ $40k",
        },
        # Sell some for a gain
        {
            "trans_type": "Deposit",
            "created_date": "2024-06-15 10:00:00",
            "exchange": "Strike",
            "buy": 0.1,
            "buy_curr": "BTC",
            "group": "",
            "comment": "Transfer in",
        },
        {
            "trans_type": "Trade",
            "created_date": "2024-06-15 11:00:00",
            "exchange": "Strike",
            "buy": 9500.0,
            "buy_curr": "USD",
            "sell": 0.1,
            "sell_curr": "BTC",
            "fee": 10.0,
            "fee_curr": "USD",
            "group": "",
            "comment": "Sell BTC @ $95k",
        },
    ]
    crypto.import_transactions(transactions)

    return crypto


class TestTaxReportingScreenMount:
    """Test TaxReportingScreen mounting and UI."""

    @pytest.mark.asyncio
    async def test_screen_mounts_via_keypress(self) -> None:
        """Test screen mounts when pressing T from main menu."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Press T to open tax reporting
            await pilot.press("t")
            await pilot.pause(0.1)

            # Verify TaxReportingScreen is on top
            assert isinstance(app.screen, TaxReportingScreen)

    @pytest.mark.asyncio
    async def test_screen_has_tabbed_content(self) -> None:
        """Test screen has TabbedContent with three tabs."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import TabbedContent

            tabbed = app.screen.query_one(TabbedContent)
            assert tabbed is not None

            # Check for all three tabs
            tab_gains = app.screen.query_one("#tab-gains")
            tab_1099b = app.screen.query_one("#tab-1099b")
            tab_forecast = app.screen.query_one("#tab-forecast")

            assert tab_gains is not None
            assert tab_1099b is not None
            assert tab_forecast is not None

    @pytest.mark.asyncio
    async def test_escape_returns_to_dashboard(self) -> None:
        """Test escape key returns to previous screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)
            assert isinstance(app.screen, TaxReportingScreen)

            await pilot.press("escape")
            await pilot.pause(0.1)
            # Should be back at dashboard (not TaxReportingScreen)
            assert not isinstance(app.screen, TaxReportingScreen)


class TestGainsTrackerTab:
    """Test Gains Tracker tab functionality."""

    @pytest.mark.asyncio
    async def test_gains_tab_has_controls(self) -> None:
        """Test gains tab has year, coin, wallet inputs and load button."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, Select, Button, DataTable

            year_input = app.screen.query_one("#gains-year", Input)
            coin_select = app.screen.query_one("#gains-coin", Select)
            wallet_input = app.screen.query_one("#gains-wallet", Input)
            load_btn = app.screen.query_one("#btn-load-gains", Button)
            table = app.screen.query_one("#gains-table", DataTable)

            assert year_input is not None
            assert coin_select is not None
            assert wallet_input is not None
            assert load_btn is not None
            assert table is not None

    @pytest.mark.asyncio
    async def test_gains_table_has_columns(self) -> None:
        """Test gains DataTable has the correct columns."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import DataTable

            table = app.screen.query_one("#gains-table", DataTable)
            columns = [col.label.plain for col in table.columns.values()]

            assert "Sale Date" in columns
            assert "Quantity" in columns
            assert "Acquire Date" in columns
            assert "Term" in columns
            assert "Proceeds" in columns
            assert "Cost Basis" in columns
            assert "Gain/Loss" in columns

    @pytest.mark.asyncio
    async def test_gains_summary_labels_exist(self) -> None:
        """Test gains summary labels are present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Label

            short_count = app.screen.query_one("#gains-short-count", Label)
            long_count = app.screen.query_one("#gains-long-count", Label)
            proceeds = app.screen.query_one("#gains-proceeds", Label)
            cost_basis = app.screen.query_one("#gains-cost-basis", Label)
            net_gain = app.screen.query_one("#gains-net", Label)

            assert short_count is not None
            assert long_count is not None
            assert proceeds is not None
            assert cost_basis is not None
            assert net_gain is not None


class TestExport1099bTab:
    """Test 1099-B Export tab functionality."""

    @pytest.mark.asyncio
    async def test_1099b_tab_has_controls(self) -> None:
        """Test 1099-B tab has export controls."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, Select, Button, DataTable, TabbedContent

            # Switch to 1099-B tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-1099b"
            await pilot.pause(0.1)

            year_input = app.screen.query_one("#export-year", Input)
            coin_select = app.screen.query_one("#export-coin", Select)
            wallet_input = app.screen.query_one("#export-wallet", Input)
            file_input = app.screen.query_one("#export-file", Input)
            preview_btn = app.screen.query_one("#btn-preview-1099b", Button)
            export_btn = app.screen.query_one("#btn-export-1099b", Button)
            table = app.screen.query_one("#export-table", DataTable)

            assert year_input is not None
            assert coin_select is not None
            assert wallet_input is not None
            assert file_input is not None
            assert preview_btn is not None
            assert export_btn is not None
            assert table is not None

    @pytest.mark.asyncio
    async def test_irs_warning_hidden_for_pre_2025(self) -> None:
        """Test IRS 2025+ warning is hidden for pre-2025 tax years."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, TabbedContent

            # Switch to 1099-B tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-1099b"
            await pilot.pause(0.1)

            # Set year to 2024
            year_input = app.screen.query_one("#export-year", Input)
            year_input.value = "2024"
            await pilot.pause(0.1)

            # Warning should be hidden
            warning = app.screen.query_one("#irs-warning")
            assert warning.display is False

    @pytest.mark.asyncio
    async def test_irs_warning_shown_for_2025_plus(self) -> None:
        """Test IRS 2025+ warning is shown for 2025+ tax years."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, TabbedContent

            # Switch to 1099-B tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-1099b"
            await pilot.pause(0.1)

            # Set year to 2025
            year_input = app.screen.query_one("#export-year", Input)
            year_input.value = "2025"
            await pilot.pause(0.1)

            # Warning should be visible
            warning = app.screen.query_one("#irs-warning")
            assert warning.display is True

    @pytest.mark.asyncio
    async def test_export_table_has_columns(self) -> None:
        """Test export preview DataTable has the correct columns."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import DataTable, TabbedContent

            # Switch to 1099-B tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-1099b"
            await pilot.pause(0.1)

            table = app.screen.query_one("#export-table", DataTable)
            columns = [col.label.plain for col in table.columns.values()]

            assert "Description" in columns
            assert "Date Acquired" in columns
            assert "Date Sold" in columns
            assert "Proceeds" in columns
            assert "Cost Basis" in columns
            assert "Term" in columns


class TestForecastTab:
    """Test Forecast Sale tab functionality."""

    @pytest.mark.asyncio
    async def test_forecast_tab_has_controls(self) -> None:
        """Test forecast tab has input controls."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, Select, Button, DataTable, TabbedContent

            # Switch to Forecast tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-forecast"
            await pilot.pause(0.1)

            coin_select = app.screen.query_one("#forecast-coin", Select)
            qty_input = app.screen.query_one("#forecast-quantity", Input)
            price_input = app.screen.query_one("#forecast-price", Input)
            wallet_input = app.screen.query_one("#forecast-wallet", Input)
            forecast_btn = app.screen.query_one("#btn-forecast", Button)
            table = app.screen.query_one("#forecast-table", DataTable)

            assert coin_select is not None
            assert qty_input is not None
            assert price_input is not None
            assert wallet_input is not None
            assert forecast_btn is not None
            assert table is not None

    @pytest.mark.asyncio
    async def test_forecast_summary_labels_exist(self) -> None:
        """Test forecast summary labels are present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Label, TabbedContent

            # Switch to Forecast tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-forecast"
            await pilot.pause(0.1)

            balance = app.screen.query_one("#forecast-balance", Label)
            proceeds = app.screen.query_one("#forecast-proceeds", Label)
            cost_basis = app.screen.query_one("#forecast-cost-basis", Label)
            short_gain = app.screen.query_one("#forecast-short-gain", Label)
            long_gain = app.screen.query_one("#forecast-long-gain", Label)
            total_gain = app.screen.query_one("#forecast-total-gain", Label)

            assert balance is not None
            assert proceeds is not None
            assert cost_basis is not None
            assert short_gain is not None
            assert long_gain is not None
            assert total_gain is not None

    @pytest.mark.asyncio
    async def test_forecast_table_has_columns(self) -> None:
        """Test forecast DataTable has the correct columns."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import DataTable, TabbedContent

            # Switch to Forecast tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-forecast"
            await pilot.pause(0.1)

            table = app.screen.query_one("#forecast-table", DataTable)
            columns = [col.label.plain for col in table.columns.values()]

            assert "Acquire Date" in columns
            assert "Quantity" in columns
            assert "Unit Cost" in columns
            assert "Total Cost" in columns
            assert "Days Held" in columns
            assert "Term" in columns


class TestTaxReportingIntegration:
    """Integration tests with real data."""

    @pytest.mark.asyncio
    async def test_load_gains_with_data(self, crypto_with_trades: CryptoAccounts) -> None:
        """Test loading gains data with actual transactions."""
        app = CryptoApp()
        app.crypto = crypto_with_trades

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input

            # Set year to 2024
            year_input = app.screen.query_one("#gains-year", Input)
            year_input.value = "2024"
            await pilot.pause(0.1)

            # Load gains
            screen = app.screen
            assert isinstance(screen, TaxReportingScreen)
            screen.load_gains_data()
            await pilot.pause(0.3)

            # Check that we got some data
            from textual.widgets import DataTable

            table = app.screen.query_one("#gains-table", DataTable)
            # Should have at least 1 row (we sold 0.1 BTC)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    async def test_forecast_with_data(self, crypto_with_trades: CryptoAccounts) -> None:
        """Test forecast with actual transactions."""
        app = CryptoApp()
        app.crypto = crypto_with_trades

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("t")
            await pilot.pause(0.1)

            from textual.widgets import Input, TabbedContent

            # Switch to Forecast tab
            tabbed = app.screen.query_one(TabbedContent)
            tabbed.active = "tab-forecast"
            await pilot.pause(0.1)

            # Set quantity and price
            qty_input = app.screen.query_one("#forecast-quantity", Input)
            price_input = app.screen.query_one("#forecast-price", Input)
            qty_input.value = "0.1"
            price_input.value = "100000"
            await pilot.pause(0.1)

            # Calculate forecast
            screen = app.screen
            assert isinstance(screen, TaxReportingScreen)
            screen.calculate_forecast()
            await pilot.pause(0.3)

            # Check that we got some data
            from textual.widgets import DataTable

            table = app.screen.query_one("#forecast-table", DataTable)
            # Should have at least 1 lot
            assert table.row_count >= 1

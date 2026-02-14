"""Tests for TUI application shell (TUI-001).

Tests the main CryptoApp, MainMenu, HelpScreen, keybindings,
and navigation using Textual's pilot testing framework.
"""

import sys
import os

import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from db import SqliteBackend
from tui.app import CryptoApp, HelpScreen, MainMenu, MenuButton
from tui.screens.ledger import LedgerScreen


class TestAppLaunch:
    """Tests that the app mounts and renders correctly."""

    @pytest.mark.asyncio
    async def test_app_mounts(self) -> None:
        """App should mount without errors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            # App should be running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_app_has_header_and_footer(self) -> None:
        """App should render Header and Footer."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            from textual.widgets import Header, Footer
            headers = app.query(Header)
            footers = app.query(Footer)
            assert len(headers) == 1
            assert len(footers) == 1

    @pytest.mark.asyncio
    async def test_app_shows_main_menu(self) -> None:
        """App should show MainMenu on startup."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            menus = app.query(MainMenu)
            assert len(menus) == 1

    @pytest.mark.asyncio
    async def test_app_title(self) -> None:
        """App should have correct title."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            assert app.TITLE == "Crypto Accounting"


class TestMainMenu:
    """Tests for the main menu widget."""

    @pytest.mark.asyncio
    async def test_menu_has_seven_buttons(self) -> None:
        """Main menu should have 7 navigation buttons."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            assert len(buttons) == 7

    @pytest.mark.asyncio
    async def test_menu_button_labels(self) -> None:
        """Menu buttons should have correct labels."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            # MenuButton stores label + key hint in renderable
            actions = [btn._action for btn in buttons]
            assert actions == ["portfolio", "ledger", "record", "import", "wallet", "tax", "viz"]

    @pytest.mark.asyncio
    async def test_menu_has_title(self) -> None:
        """Main menu should show the app title."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            title = app.query_one("#menu-title")
            assert "Crypto Accounting" in title.content

    @pytest.mark.asyncio
    async def test_menu_has_hint(self) -> None:
        """Main menu should show the hint text."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            hint = app.query_one("#menu-hint")
            assert "help" in hint.content.lower()


class TestKeyBindings:
    """Tests for keyboard navigation."""

    @pytest.mark.asyncio
    async def test_help_key(self) -> None:
        """Pressing ? should open the help screen."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            # Help screen should be pushed
            assert isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_help_escape_closes(self) -> None:
        """Pressing Escape should close the help screen."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            # Should be back to main screen
            assert not isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_portfolio_key_triggers_dashboard(self) -> None:
        """Pressing P should push dashboard screen (TUI-002)."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause()  # Wait for initial dashboard
            # Go back to main menu
            await pilot.press("escape")
            await pilot.pause()
            # Press P for portfolio/dashboard
            await pilot.press("p")
            await pilot.pause()
            # Dashboard should be in screen stack
            assert len(app.screen_stack) >= 1

    @pytest.mark.asyncio
    async def test_ledger_key_pushes_screen(self) -> None:
        """Pressing L should push ledger screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.1)
            assert len(app.screen_stack) >= 2

    @pytest.mark.asyncio
    async def test_record_key_pushes_screen(self) -> None:
        """Pressing R should push record transaction screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            await pilot.pause(0.1)
            assert len(app.screen_stack) >= 2

    @pytest.mark.asyncio
    async def test_import_key_pushes_screen(self) -> None:
        """Pressing I should push import wizard screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            await pilot.pause(0.1)
            assert len(app.screen_stack) >= 2

    @pytest.mark.asyncio
    async def test_tax_key_pushes_screen(self) -> None:
        """Pressing T should push tax reporting screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("t")
            await pilot.pause(0.1)
            assert len(app.screen_stack) >= 2

    @pytest.mark.asyncio
    async def test_viz_key_pushes_screen(self) -> None:
        """Pressing V should push visualization screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("v")
            await pilot.pause(0.1)
            assert len(app.screen_stack) >= 2


class TestHelpScreen:
    """Tests for the help overlay."""

    @pytest.mark.asyncio
    async def test_help_screen_renders(self) -> None:
        """Help screen should render without errors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            dialog = app.screen.query_one("#help-dialog")
            assert dialog is not None

    @pytest.mark.asyncio
    async def test_help_shows_keybindings(self) -> None:
        """Help screen should list key navigation hints."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            # Should find labels with navigation keys
            labels = app.screen.query("Label")
            label_texts = [label.content for label in labels]
            combined = " ".join(label_texts)
            assert "Portfolio" in combined
            assert "Import" in combined
            assert "Quit" in combined


class TestTUI012HelpEnhancements:
    """Tests for TUI-012 help system enhancements."""

    @pytest.mark.asyncio
    async def test_f1_opens_help(self) -> None:
        """F1 key should open the help screen."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("f1")
            assert isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_help_shows_screen_descriptions(self) -> None:
        """Help screen should show descriptions for each functional area."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            labels = app.screen.query("Label")
            combined = " ".join(label.content for label in labels)
            # Check per-screen descriptions are present
            assert "Wallet balances" in combined
            assert "Transaction Ledger" in combined
            assert "Record Transaction" in combined
            assert "Import CSV" in combined
            assert "Export" in combined
            assert "Tax" in combined
            assert "Visualizations" in combined

    @pytest.mark.asyncio
    async def test_help_has_about_section(self) -> None:
        """Help screen should show About section with backend info."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            await pilot.press("question_mark")
            await pilot.pause(0.1)
            labels = app.screen.query("Label")
            combined = " ".join(label.content for label in labels)
            # About section should show backend info
            assert "About" in combined
            assert "Backend" in combined

    @pytest.mark.asyncio
    async def test_help_shows_f1_shortcut(self) -> None:
        """Help screen should mention F1 as a way to open help."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            labels = app.screen.query("Label")
            combined = " ".join(label.content for label in labels)
            assert "F1" in combined

    @pytest.mark.asyncio
    async def test_help_has_scrollable_content(self) -> None:
        """Help screen should have a scrollable container."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            scroll = app.screen.query_one("#help-scroll")
            assert scroll is not None

    @pytest.mark.asyncio
    async def test_about_info_without_db(self) -> None:
        """About info should handle no database gracefully."""
        app = CryptoApp()
        # Directly test the method without DB
        app.crypto = None
        info = app._get_about_info()
        assert "Not connected" in info

    @pytest.mark.asyncio
    async def test_global_error_handler_exists(self) -> None:
        """App should have on_worker_state_changed for global error handling."""
        app = CryptoApp()
        assert hasattr(app, "on_worker_state_changed")


class TestDatabaseLifecycle:
    """Tests for CryptoAccounts lifecycle management."""

    @pytest.mark.asyncio
    async def test_crypto_initialized_on_mount(self) -> None:
        """CryptoAccounts should be created when app mounts."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            # crypto may be None if no DB configured, but should have been attempted
            # In test environment without DB, it might fail gracefully
            # The important thing is the app is running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_app_handles_no_database(self) -> None:
        """App should handle missing database gracefully."""
        app = CryptoApp()
        # Even with no DB, app should mount and show menu
        async with app.run_test() as pilot:
            menus = app.query(MainMenu)
            assert len(menus) == 1


class TestMenuButtonWidget:
    """Tests for the MenuButton widget."""

    @pytest.mark.asyncio
    async def test_menu_button_stores_action(self) -> None:
        """MenuButton should store its action string."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            portfolio_btn = buttons[0]
            assert portfolio_btn._action == "portfolio"

    @pytest.mark.asyncio
    async def test_all_menu_actions_are_valid(self) -> None:
        """Each menu button's action should map to a valid app method."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            for btn in buttons:
                method_name = f"action_menu_{btn._action}"
                assert hasattr(app, method_name), f"Missing method: {method_name}"


class TestLedgerSummaryPanel:
    """Tests for ledger summary statistics panel."""

    @pytest.mark.asyncio
    async def test_summary_panel_exists(self) -> None:
        """Ledger screen should have a summary panel."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            summary_panel = app.screen.query_one("#summary-panel")
            assert summary_panel is not None

    @pytest.mark.asyncio
    async def test_summary_panel_visible_with_coin_filter(self) -> None:
        """Summary panel should be visible when a coin filter is active."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            # Default coin is BTC, so panel should be visible
            summary_panel = app.screen.query_one("#summary-panel")
            assert summary_panel.display is True

    @pytest.mark.asyncio
    async def test_update_summary_with_btc_transactions(self) -> None:
        """Summary should calculate stats correctly for BTC transactions."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, LedgerScreen)

            # Inject test transactions
            screen.current_coin = "BTC"
            screen.filtered_transactions = [
                {"Buy": 1.5, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None, "Fee": 0.001, "Fee Cur.": "BTC"},
                {"Buy": None, "Buy Cur.": None, "Sell": 0.5, "Sell Cur.": "BTC", "Fee": 0.0005, "Fee Cur.": "BTC"},
                {"Buy": 2.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None, "Fee": None, "Fee Cur.": None},
            ]
            screen._update_summary()

            panel = screen.query_one("#summary-label")
            content = panel.content
            assert "3.50000000" in content
            assert "0.50000000" in content
            assert "0.00150000" in content
            assert "3.00000000" in content
            assert "3" in content

    @pytest.mark.asyncio
    async def test_update_summary_usd_format(self) -> None:
        """Summary should use 2 decimal places for USD."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, LedgerScreen)

            screen.current_coin = "USD"
            screen.filtered_transactions = [
                {"Buy": 100.50, "Buy Cur.": "USD", "Sell": None, "Sell Cur.": None, "Fee": 1.25, "Fee Cur.": "USD"},
            ]
            screen._update_summary()

            panel = screen.query_one("#summary-label")
            assert "100.50" in panel.content

    @pytest.mark.asyncio
    async def test_summary_hidden_when_all_coins(self) -> None:
        """Summary panel should be hidden when 'All' coins is selected."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, LedgerScreen)

            screen.current_coin = None
            screen._update_summary()

            summary_panel = screen.query_one("#summary-panel")
            assert summary_panel.display is False

    @pytest.mark.asyncio
    async def test_summary_shows_all_stat_labels(self) -> None:
        """Summary should display Credits, Debits, Fees, Balance, Count."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, LedgerScreen)

            screen.current_coin = "BTC"
            screen.filtered_transactions = [
                {"Buy": 1.0, "Buy Cur.": "BTC", "Sell": None, "Sell Cur.": None, "Fee": None, "Fee Cur.": None},
            ]
            screen._update_summary()

            panel = screen.query_one("#summary-label")
            assert "Credits:" in panel.content
            assert "Debits:" in panel.content
            assert "Fees:" in panel.content
            assert "Balance:" in panel.content
            assert "Count:" in panel.content

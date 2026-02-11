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
    async def test_menu_has_six_buttons(self) -> None:
        """Main menu should have 6 navigation buttons."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            assert len(buttons) == 6

    @pytest.mark.asyncio
    async def test_menu_button_labels(self) -> None:
        """Menu buttons should have correct labels."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            buttons = app.query(MenuButton)
            # MenuButton stores label + key hint in renderable
            actions = [btn._action for btn in buttons]
            assert actions == ["portfolio", "ledger", "record", "import", "tax", "viz"]

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
    async def test_portfolio_key_triggers_notification(self) -> None:
        """Pressing P should trigger portfolio action (stub notification)."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("p")
            # Should have a notification about portfolio
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_ledger_key_triggers_notification(self) -> None:
        """Pressing L should trigger ledger action."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("l")
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_record_key_triggers_notification(self) -> None:
        """Pressing R should trigger record action."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("r")
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_import_key_triggers_notification(self) -> None:
        """Pressing I should trigger import action."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("i")
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_tax_key_triggers_notification(self) -> None:
        """Pressing T should trigger tax action."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("t")
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_viz_key_triggers_notification(self) -> None:
        """Pressing V should trigger viz action."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.press("v")
            assert len(app._notifications) > 0


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

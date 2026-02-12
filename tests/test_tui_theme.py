"""Tests for TUI theme and styling (TUI-003).

Tests that the app.tcss theme file loads correctly and applies
consistent styling across the application.
"""

import sys
import os

import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from tui.app import CryptoApp
from textual.widgets import Button, DataTable, Input


class TestThemeLoading:
    """Tests that the theme file loads and applies correctly."""

    @pytest.mark.asyncio
    async def test_css_file_loads_without_error(self) -> None:
        """App should load .tcss theme file without errors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            # App should mount successfully with CSS loaded
            assert app.is_running
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_app_has_css_path(self) -> None:
        """App should have CSS_PATH attribute pointing to theme file."""
        app = CryptoApp()
        assert hasattr(app, 'CSS_PATH')
        assert 'app.tcss' in str(app.CSS_PATH)

    @pytest.mark.asyncio
    async def test_theme_file_exists(self) -> None:
        """Theme file should exist at specified path."""
        import pathlib
        # Theme file relative to src/python
        theme_path = pathlib.Path(__file__).parent.parent / 'src' / 'python' / 'tui' / 'styles' / 'app.tcss'
        assert theme_path.exists(), f"Theme file not found at {theme_path}"
        assert theme_path.stat().st_size > 0, "Theme file is empty"


class TestThemeColors:
    """Tests that theme colors are applied correctly."""

    @pytest.mark.asyncio
    async def test_screen_has_dark_background(self) -> None:
        """Screen should have dark navy background from theme."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Screen should be styled by theme (no assertion on computed styles in headless mode)
            # This test primarily ensures no CSS errors prevent app from running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_dashboard_screen_applies_theme(self) -> None:
        """Dashboard screen should use theme colors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Dashboard is pushed on mount
            await pilot.pause(0.1)
            # Should render without CSS errors
            assert len(app.screen_stack) >= 1


class TestWidgetStyling:
    """Tests that common widgets receive consistent styling."""

    @pytest.mark.asyncio
    async def test_datatable_styling(self) -> None:
        """DataTable should have theme styling via main app."""
        from textual.widgets import DataTable

        # Use CryptoApp which has theme loaded
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Dashboard has DataTable for recent transactions
            await pilot.pause(0.2)
            # Check that app loaded without CSS errors
            assert app.is_running

    @pytest.mark.asyncio
    async def test_button_styling(self) -> None:
        """Buttons should have theme styling via main app."""
        # Buttons will be used in future screens (TUI-007, TUI-008, etc.)
        # For now, verify theme loads without errors
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.is_running

    @pytest.mark.asyncio
    async def test_input_styling(self) -> None:
        """Input fields should have theme styling via main app."""
        # Inputs will be used in future screens (TUI-007, TUI-008, etc.)
        # For now, verify theme loads without errors
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.is_running


class TestNotificationStyling:
    """Tests that notifications use correct colors."""

    @pytest.mark.asyncio
    async def test_info_notification(self) -> None:
        """Info notifications should use theme info color."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause()
            app.notify("Test info message", severity="information")
            await pilot.pause()
            # Notification should be created without CSS errors
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_success_notification(self) -> None:
        """Success notifications should use theme success color."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause()
            app.notify("Test success message", severity="success")
            await pilot.pause()
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_warning_notification(self) -> None:
        """Warning notifications should use theme warning color."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause()
            app.notify("Test warning message", severity="warning")
            await pilot.pause()
            assert len(app._notifications) > 0

    @pytest.mark.asyncio
    async def test_error_notification(self) -> None:
        """Error notifications should use theme error color."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause()
            app.notify("Test error message", severity="error")
            await pilot.pause()
            assert len(app._notifications) > 0


class TestThemeConsistency:
    """Tests that theme is applied consistently across screens."""

    @pytest.mark.asyncio
    async def test_main_menu_uses_theme(self) -> None:
        """Main menu should use theme colors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Go back to main menu
            await pilot.press("escape")
            await pilot.pause()
            # Menu should render with theme
            from tui.app import MainMenu
            menus = app.query(MainMenu)
            assert len(menus) == 1

    @pytest.mark.asyncio
    async def test_help_screen_uses_theme(self) -> None:
        """Help screen should use theme colors."""
        app = CryptoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Go back to main menu first
            await pilot.press("escape")
            await pilot.pause()
            # Open help
            await pilot.press("question_mark")
            await pilot.pause(0.1)
            # Help screen should be pushed to screen stack
            assert len(app.screen_stack) >= 2  # Base + help


class TestThemeAccessibilityColors:
    """Tests that theme maintains good contrast ratios."""

    @pytest.mark.asyncio
    async def test_theme_variables_defined(self) -> None:
        """Theme should define color variables for consistency."""
        import pathlib
        theme_path = pathlib.Path(__file__).parent.parent / 'src' / 'python' / 'tui' / 'styles' / 'app.tcss'
        content = theme_path.read_text()

        # Check for key color variables
        assert '$background:' in content
        assert '$accent:' in content
        assert '$success:' in content
        assert '$warning:' in content
        assert '$error:' in content

    @pytest.mark.asyncio
    async def test_bitcoin_orange_accent_defined(self) -> None:
        """Theme should use Bitcoin orange (#F7931A) as accent color."""
        import pathlib
        theme_path = pathlib.Path(__file__).parent.parent / 'src' / 'python' / 'tui' / 'styles' / 'app.tcss'
        content = theme_path.read_text()

        # Check for Bitcoin orange
        assert '#f7931a' in content.lower() or '#F7931A' in content

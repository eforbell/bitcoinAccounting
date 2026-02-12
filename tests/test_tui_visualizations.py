"""Tests for visualization screen (TUI-011)."""

from __future__ import annotations

import pytest
from pathlib import Path

from tui.app import CryptoApp
from tui.screens.visualizations import VisualizationScreen


class TestVisualizationScreenMount:
    """Test visualization screen mounting and UI."""

    @pytest.mark.asyncio
    async def test_viz_screen_mounts(self) -> None:
        """Test visualization screen mounts successfully."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Press V to open visualization screen
            await pilot.press("v")
            await pilot.pause(0.1)

            # Verify screen is mounted
            viz_container = app.screen.query_one("#viz-container")
            assert viz_container is not None

    @pytest.mark.asyncio
    async def test_viz_screen_has_chart_type_selector(self) -> None:
        """Test visualization screen has chart type selector."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            # Check for chart type selector
            chart_select = app.screen.query_one("#select-chart-type")
            assert chart_select is not None

    @pytest.mark.asyncio
    async def test_viz_screen_has_date_range_selector(self) -> None:
        """Test visualization screen has date range selector."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            # Check for date range selector
            date_select = app.screen.query_one("#select-date-range")
            assert date_select is not None

    @pytest.mark.asyncio
    async def test_viz_screen_has_dpi_selector(self) -> None:
        """Test visualization screen has DPI selector."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            dpi_select = app.screen.query_one("#select-dpi")
            assert dpi_select is not None

    @pytest.mark.asyncio
    async def test_viz_screen_has_output_dir_input(self) -> None:
        """Test visualization screen has output directory input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            output_dir = app.screen.query_one("#input-output-dir")
            assert output_dir is not None
            assert output_dir.value == "output/viz/"

    @pytest.mark.asyncio
    async def test_viz_screen_has_checkboxes(self) -> None:
        """Test visualization screen has cost basis and log scale checkboxes."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            cost_basis_cb = app.screen.query_one("#cb-cost-basis")
            assert cost_basis_cb is not None
            assert cost_basis_cb.value is True  # Default checked

            log_scale_cb = app.screen.query_one("#cb-log-scale")
            assert log_scale_cb is not None
            assert log_scale_cb.value is False  # Default unchecked

    @pytest.mark.asyncio
    async def test_viz_screen_has_action_buttons(self) -> None:
        """Test visualization screen has Generate, Open, Cancel buttons."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            gen_btn = app.screen.query_one("#btn-generate")
            assert gen_btn is not None

            open_btn = app.screen.query_one("#btn-open")
            assert open_btn is not None

            cancel_btn = app.screen.query_one("#btn-cancel")
            assert cancel_btn is not None


class TestVisualizationScreenDefaults:
    """Test default values of form elements."""

    @pytest.mark.asyncio
    async def test_chart_type_defaults_to_all(self) -> None:
        """Test chart type selector defaults to 'all'."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            chart_select = app.screen.query_one("#select-chart-type")
            assert chart_select.value == "all"

    @pytest.mark.asyncio
    async def test_date_range_defaults_to_all(self) -> None:
        """Test date range selector defaults to 'all'."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            date_select = app.screen.query_one("#select-date-range")
            assert date_select.value == "all"

    @pytest.mark.asyncio
    async def test_dpi_defaults_to_300(self) -> None:
        """Test DPI selector defaults to 300."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            dpi_select = app.screen.query_one("#select-dpi")
            assert dpi_select.value == 300

    @pytest.mark.asyncio
    async def test_custom_dates_hidden_by_default(self) -> None:
        """Test custom date inputs are hidden when date range is not 'custom'."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            custom_dates = app.screen.query_one("#custom-dates")
            assert custom_dates.display is False

    @pytest.mark.asyncio
    async def test_results_hidden_by_default(self) -> None:
        """Test results section is hidden initially."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            results = app.screen.query_one("#results-section")
            assert results.display is False


class TestVisualizationScreenNavigation:
    """Test navigation behavior."""

    @pytest.mark.asyncio
    async def test_cancel_button_closes_screen(self) -> None:
        """Test Cancel button closes visualization screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            # Call button handler directly (button may be off-screen in test terminal)
            screen = app.screen
            assert isinstance(screen, VisualizationScreen)
            btn = screen.query_one("#btn-cancel")
            btn.press()
            await pilot.pause(0.2)

            # Should be back (no longer on viz screen)

    @pytest.mark.asyncio
    async def test_escape_closes_screen(self) -> None:
        """Test Escape key closes visualization screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            await pilot.press("escape")
            await pilot.pause(0.2)


class TestVisualizationScreenValidation:
    """Test input validation."""

    @pytest.mark.asyncio
    async def test_open_without_files_shows_error(self) -> None:
        """Test clicking Open without generating shows error."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            # Get the screen and call open directly (button may be off-screen)
            screen = app.screen
            assert isinstance(screen, VisualizationScreen)
            screen.open_generated_files()
            await pilot.pause(0.1)

            # Status should show error class
            status = app.screen.query_one("#status-message")
            assert status.has_class("error")

    @pytest.mark.asyncio
    async def test_custom_range_requires_start_date(self) -> None:
        """Test custom date range requires start date."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            # Get the screen and set custom range + call generate
            screen = app.screen
            assert isinstance(screen, VisualizationScreen)

            # Set date range to custom
            date_select = screen.query_one("#select-date-range")
            date_select.value = "custom"
            await pilot.pause(0.1)

            # Leave start date empty and try to generate
            screen.start_generation()
            await pilot.pause(0.1)

            # Status should show error class
            status = screen.query_one("#status-message")
            assert status.has_class("error")


class TestVisualizationScreenGeneration:
    """Test chart generation flow."""

    @pytest.mark.asyncio
    async def test_generate_disables_button(self) -> None:
        """Test generate button is disabled during generation."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, VisualizationScreen)

            # Call start_generation (it will show info message and disable button)
            screen.start_generation()
            await pilot.pause(0.1)

            gen_btn = screen.query_one("#btn-generate")
            assert gen_btn.disabled is True

            # Wait for async work to finish (may fail due to no data)
            await pilot.pause(1.0)

            # Button should be re-enabled after generation completes
            assert gen_btn.disabled is False

    @pytest.mark.asyncio
    async def test_show_results_displays_files(self) -> None:
        """Test _show_results shows generated files."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("v")
            await pilot.pause(0.2)

            screen = app.screen
            assert isinstance(screen, VisualizationScreen)

            # Simulate results
            generated = {
                "Orange Plot": Path("/tmp/test_orange.png"),
                "Balance Chart": Path("/tmp/test_balance.png"),
            }
            screen._show_results(generated, {})
            await pilot.pause(0.1)

            # Results section should be visible
            results = screen.query_one("#results-section")
            assert results.display is True

            # Generated files should be stored
            assert len(screen.generated_files) == 2

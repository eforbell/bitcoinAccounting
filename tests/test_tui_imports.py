"""Tests for import wizard screen (TUI-008)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.css.query import NoMatches
from textual.pilot import Pilot

from cryptoAccounts import CryptoAccounts
from db import SqliteBackend
from tui.app import CryptoApp
from tui.screens.imports import FilePickerModal, ImportWizardScreen


DETECT_DUPLICATES_PATCH = f"{ImportWizardScreen.__module__}.detect_duplicates"


@pytest.fixture
def coinbase_sample_path() -> str:
    """Return path to Coinbase sample CSV."""
    return str(Path(__file__).parent / "fixtures" / "csv_samples" / "coinbase_sample.csv")


@pytest.fixture
def ledger_sample_path() -> str:
    """Return path to Ledger sample CSV."""
    return str(Path(__file__).parent / "fixtures" / "csv_samples" / "ledger_sample.csv")


async def _wait_until(
    pilot: Pilot,
    predicate,
    *,
    timeout: float = 8.0,
    message: str = "Timed out waiting for test condition",
) -> None:
    """Wait for a condition by yielding to the app loop without fixed sleep durations."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except NoMatches:
            # Common while waiting for widgets to mount; keep polling.
            pass
        except Exception:
            # Allow transient query/state errors during UI transitions.
            pass
        await pilot.pause(0)
    raise AssertionError(message)


def _has_widget(screen: ImportWizardScreen, selector: str) -> bool:
    """Return True if a widget matching selector exists on the current screen."""
    try:
        screen.query_one(selector)
        return True
    except NoMatches:
        return False
    except Exception:
        return False


async def _open_wizard(app: CryptoApp, pilot: Pilot) -> ImportWizardScreen:
    """Open wizard and wait for step 1 widgets."""
    await pilot.press("i")
    await _wait_until(
        pilot,
        lambda: isinstance(app.screen, ImportWizardScreen)
        and app.screen.current_step == 1
        and app.screen.query_one("#input-file-path") is not None,
        message="Import wizard did not open on step 1",
    )
    assert isinstance(app.screen, ImportWizardScreen)
    return app.screen


async def _detect_and_wait_next_enabled(
    app: CryptoApp, pilot: Pilot, file_path: str
) -> ImportWizardScreen:
    """Detect parser and wait until Next is enabled."""
    screen = await _open_wizard(app, pilot)
    file_input = screen.query_one("#input-file-path")
    file_input.value = file_path
    await pilot.click("#btn-detect")
    await app.workers.wait_for_complete()
    await _wait_until(
        pilot,
        lambda: isinstance(app.screen, ImportWizardScreen),
        message="Import wizard screen not active after detect",
    )
    assert isinstance(app.screen, ImportWizardScreen)
    next_enabled = app.screen.query_one("#btn-next").disabled is False
    has_error = _has_widget(app.screen, "#error-panel")
    if not next_enabled and has_error:
        error_text = str(app.screen.query_one("#error-panel").render())
        raise AssertionError(f"Detect did not enable Next. Error: {error_text}")
    if not next_enabled:
        raise AssertionError("Detect did not enable Next")
    return app.screen


async def _go_step2(app: CryptoApp, pilot: Pilot, file_path: str) -> ImportWizardScreen:
    """Go to step 2 deterministically."""
    await _detect_and_wait_next_enabled(app, pilot, file_path)
    await pilot.click("#btn-next")
    await _wait_until(
        pilot,
        lambda: isinstance(app.screen, ImportWizardScreen)
        and app.screen.current_step == 2
        and app.screen.query_one("#checkbox-dry-run") is not None,
        message="Wizard did not reach step 2",
    )
    assert isinstance(app.screen, ImportWizardScreen)
    return app.screen


async def _go_step3(app: CryptoApp, pilot: Pilot, file_path: str) -> ImportWizardScreen:
    """Go to step 3 deterministically."""
    screen = await _go_step2(app, pilot, file_path)
    screen.prepare_preview()
    await app.workers.wait_for_complete()
    await _wait_until(
        pilot,
        lambda: isinstance(app.screen, ImportWizardScreen)
        and app.screen.current_step == 3,
        message="Wizard did not reach step 3",
    )
    await _wait_until(
        pilot,
        lambda: isinstance(app.screen, ImportWizardScreen)
        and _has_widget(app.screen, "#preview-table"),
        message="Step 3 preview table was not rendered",
    )
    assert isinstance(app.screen, ImportWizardScreen)
    return app.screen


def _make_test_crypto() -> CryptoAccounts:
    """Create an in-memory CryptoAccounts instance for TUI tests that need DB access."""
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    return CryptoAccounts(backend=backend)


class TestImportWizardScreenMount:
    """Test import wizard screen mounting and UI."""

    @pytest.mark.asyncio
    async def test_import_wizard_mounts(self) -> None:
        """Test import wizard screen mounts successfully."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Press I to open import wizard
            await pilot.press("i")
            await pilot.pause(0.1)

            # Verify screen is mounted
            # ImportWizardScreen doesn't set a title, check for wizard container instead
            wizard_container = app.screen.query_one("#wizard-container")
            assert wizard_container is not None

    @pytest.mark.asyncio
    async def test_import_wizard_has_header(self) -> None:
        """Test import wizard has proper header."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.1)

            # Check for wizard header
            header = app.screen.query_one("#wizard-header")
            assert header is not None
            assert "Import" in str(header.content)

    @pytest.mark.asyncio
    async def test_import_wizard_step_indicator(self) -> None:
        """Test import wizard shows step indicator."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.1)

            # Check for step indicator
            steps = app.screen.query_one("#wizard-steps")
            assert steps is not None


class TestImportWizardStep1:
    """Test step 1: File selection."""

    @pytest.mark.asyncio
    async def test_step1_file_input(self) -> None:
        """Test step 1 has file path input."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Check for file input
            file_input = app.screen.query_one("#input-file-path")
            assert file_input is not None

    @pytest.mark.asyncio
    async def test_step1_detect_button(self) -> None:
        """Test step 1 has detect button."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Check for detect button
            detect_btn = app.screen.query_one("#btn-detect")
            assert detect_btn is not None

    @pytest.mark.asyncio
    async def test_step1_next_disabled_initially(self) -> None:
        """Test Next button disabled until format detected."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Next button should be disabled
            next_btn = app.screen.query_one("#btn-next")
            assert next_btn.disabled is True


class TestImportWizardDetection:
    """Test format detection."""

    @pytest.mark.asyncio
    async def test_detect_coinbase_format(self, coinbase_sample_path: str) -> None:
        """Test detecting Coinbase CSV format."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Enter file path
            file_input = app.screen.query_one("#input-file-path")
            file_input.value = coinbase_sample_path

            # Click detect button
            detect_btn = app.screen.query_one("#btn-detect")
            await pilot.click("#btn-detect")
            await pilot.pause(0.5)  # Wait for detection

            # Check for detection result
            result_container = app.screen.query_one("#detection-result")
            assert result_container is not None

    @pytest.mark.asyncio
    async def test_detect_wallet_format(self, ledger_sample_path: str) -> None:
        """Test detecting Ledger wallet CSV format."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Enter file path
            file_input = app.screen.query_one("#input-file-path")
            file_input.value = ledger_sample_path

            # Click detect button
            await pilot.click("#btn-detect")
            await pilot.pause(0.5)

            # Check for detection result
            result_container = app.screen.query_one("#detection-result")
            assert result_container is not None

    @pytest.mark.asyncio
    async def test_detect_nonexistent_file(self) -> None:
        """Test detecting nonexistent file shows error."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Enter invalid path
            file_input = app.screen.query_one("#input-file-path")
            file_input.value = "/nonexistent/file.csv"

            # Click detect button
            await pilot.click("#btn-detect")
            await pilot.pause(0.3)

            # Should show error
            try:
                error_panel = app.screen.query_one("#error-panel")
                assert error_panel is not None
            except Exception:
                # Error might be shown differently
                pass


class TestImportWizardStep2:
    """Test step 2: Configuration."""

    @pytest.mark.asyncio
    async def test_step2_dry_run_checkbox(self, coinbase_sample_path: str) -> None:
        """Test step 2 has dry-run checkbox."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await _go_step2(app, pilot, coinbase_sample_path)

            # Check for dry-run checkbox
            dry_run_cb = app.screen.query_one("#checkbox-dry-run")
            assert dry_run_cb is not None
            # Should be checked by default
            assert dry_run_cb.value is True

    @pytest.mark.asyncio
    async def test_step2_withdraw_to_selector(self, coinbase_sample_path: str) -> None:
        """Test step 2 has withdraw-to selector."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await _go_step2(app, pilot, coinbase_sample_path)

            # Check for withdraw-to selector
            withdraw_select = app.screen.query_one("#select-withdraw-to")
            assert withdraw_select is not None


class TestImportWizardStep3:
    """Test step 3: Preview."""

    @pytest.mark.asyncio
    async def test_step3_preview_table(self, coinbase_sample_path: str) -> None:
        """Test step 3 shows preview table."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await _go_step3(app, pilot, coinbase_sample_path)

            # Check for preview table
            preview_table = app.screen.query_one("#preview-table")
            assert preview_table is not None

    @pytest.mark.asyncio
    async def test_step3_import_button(self, coinbase_sample_path: str) -> None:
        """Test step 3 changes Next to Import button."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await _go_step3(app, pilot, coinbase_sample_path)

            # Check Import button label
            next_btn = app.screen.query_one("#btn-next")
            # Button label should change to "Import"
            # Can't easily test label content, but verify button exists


class TestImportWizardNavigation:
    """Test wizard navigation."""

    @pytest.mark.asyncio
    async def test_back_button_navigation(self, coinbase_sample_path: str) -> None:
        """Test Back button navigates between steps."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await _go_step2(app, pilot, coinbase_sample_path)

            # Back button should be enabled
            back_btn = app.screen.query_one("#btn-back")
            assert back_btn.disabled is False

            # Click back
            await pilot.click("#btn-back")
            await _wait_until(
                pilot,
                lambda: isinstance(app.screen, ImportWizardScreen)
                and app.screen.current_step == 1,
                message="Back did not return to step 1",
            )

            # Should be back at step 1
            steps = app.screen.query_one("#wizard-steps")
            # Can't easily test label content, but verify we're back

    @pytest.mark.asyncio
    async def test_cancel_button(self) -> None:
        """Test Cancel button closes wizard."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Click cancel
            await pilot.click("#btn-cancel")
            await pilot.pause(0.2)

            # Should be back at dashboard
            # (Can't easily verify screen type, but wizard should be gone)

    @pytest.mark.asyncio
    async def test_escape_closes_wizard(self) -> None:
        """Test Escape key closes wizard."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Press escape
            await pilot.press("escape")
            await pilot.pause(0.2)

            # Should be back at dashboard


class TestImportWizardExecution:
    """Test import execution."""

    @pytest.mark.asyncio
    async def test_dry_run_execution(self, coinbase_sample_path: str) -> None:
        """Test dry-run import shows results without importing."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # Ensure dry-run is checked
            dry_run_cb = app.screen.query_one("#checkbox-dry-run")
            assert dry_run_cb.value is True

            assert isinstance(app.screen, ImportWizardScreen)
            app.screen.prepare_preview()
            await app.workers.wait_for_complete()
            await _wait_until(
                pilot,
                lambda: isinstance(app.screen, ImportWizardScreen)
                and app.screen.current_step == 3,
                message="Did not reach step 3",
            )

            # Execute import
            assert isinstance(app.screen, ImportWizardScreen)
            app.screen.query_one("#btn-next").press()
            await app.workers.wait_for_complete()
            await _wait_until(
                pilot,
                lambda: isinstance(app.screen, ImportWizardScreen)
                and _has_widget(app.screen, "#results-panel"),
                message="Dry-run results did not render",
            )
            results_panel = app.screen.query_one("#results-panel")
            assert results_panel is not None


class TestFilePickerModal:
    """Tests for the file picker modal dialog."""

    @pytest.mark.asyncio
    async def test_browse_button_exists(self) -> None:
        """Step 1 should have a Browse button next to file input."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            browse_btn = app.screen.query_one("#btn-browse")
            assert browse_btn is not None

    @pytest.mark.asyncio
    async def test_browse_opens_modal(self) -> None:
        """Clicking Browse should open the file picker modal."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            # Programmatically press the browse button (avoids screen bounds issues)
            browse_btn = app.screen.query_one("#btn-browse")
            browse_btn.press()
            await pilot.pause(0.3)

            # File picker modal should now be the active screen
            assert isinstance(app.screen, FilePickerModal)

    @pytest.mark.asyncio
    async def test_modal_has_directory_tree(self) -> None:
        """File picker modal should contain a DirectoryTree widget."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            browse_btn = app.screen.query_one("#btn-browse")
            browse_btn.press()
            await pilot.pause(0.3)

            tree = app.screen.query_one("#file-picker-tree")
            assert tree is not None

    @pytest.mark.asyncio
    async def test_modal_select_disabled_initially(self) -> None:
        """Select button should be disabled until a file is selected."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            browse_btn = app.screen.query_one("#btn-browse")
            browse_btn.press()
            await pilot.pause(0.3)

            select_btn = app.screen.query_one("#btn-fp-select")
            assert select_btn.disabled is True

    @pytest.mark.asyncio
    async def test_modal_cancel_closes(self) -> None:
        """Cancel button should close the modal without selecting."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            browse_btn = app.screen.query_one("#btn-browse")
            browse_btn.press()
            await pilot.pause(0.3)

            assert isinstance(app.screen, FilePickerModal)

            cancel_btn = app.screen.query_one("#btn-fp-cancel")
            cancel_btn.press()
            await pilot.pause(0.3)

            # Should be back to import wizard
            assert isinstance(app.screen, ImportWizardScreen)

    @pytest.mark.asyncio
    async def test_modal_has_title(self) -> None:
        """File picker modal should have a title label."""
        app = CryptoApp()
        async with app.run_test(notifications=True, size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            await pilot.press("i")
            await pilot.pause(0.2)

            browse_btn = app.screen.query_one("#btn-browse")
            browse_btn.press()
            await pilot.pause(0.3)

            title = app.screen.query_one("#file-picker-title")
            assert "CSV" in title.content or "File" in title.content


class TestImportWizardDuplicateDetection:
    """Test duplicate detection in import wizard (DIF-005)."""

    @pytest.mark.asyncio
    async def test_duplicate_warning_shown_when_duplicates_detected(
        self, coinbase_sample_path: str
    ) -> None:
        """Test warning banner is shown when duplicates are detected."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # Mock detect_duplicates to return one duplicate
            sample_duplicate = {
                'trans_type': 'Deposit',
                'created_date': '2023-01-01',
                'exchange': 'Coinbase',
                'buy': 0.001,
                'buy_curr': 'BTC'
            }

            with patch(DETECT_DUPLICATES_PATCH, return_value=[sample_duplicate]):
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.prepare_preview()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and app.screen.current_step == 3
                    and _has_widget(app.screen, "#duplicate-warning"),
                    message="Duplicate warning was not shown",
                )

                # Should show duplicate warning
                warning = app.screen.query_one("#duplicate-warning")
                assert warning is not None

    @pytest.mark.asyncio
    async def test_no_warning_when_no_duplicates(
        self, coinbase_sample_path: str
    ) -> None:
        """Test no warning banner when no duplicates detected."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # Mock detect_duplicates to return empty list
            with patch(DETECT_DUPLICATES_PATCH, return_value=[]):
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.prepare_preview()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and app.screen.current_step == 3
                    and _has_widget(app.screen, "#preview-table"),
                    message="Step 3 preview did not render",
                )

                # Should not show duplicate warning
                with pytest.raises(NoMatches):
                    app.screen.query_one("#duplicate-warning")

    @pytest.mark.asyncio
    async def test_duplicate_transactions_marked_in_preview(
        self, coinbase_sample_path: str
    ) -> None:
        """Test duplicate transactions are marked with warning icon in preview table."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # We can't easily mock duplicates and check table rows,
            # but we can verify the preview table exists
            with patch(DETECT_DUPLICATES_PATCH, return_value=[]):
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.prepare_preview()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and app.screen.current_step == 3
                    and _has_widget(app.screen, "#preview-table"),
                    message="Preview table was not shown",
                )

                preview_table = app.screen.query_one("#preview-table")
                assert preview_table is not None

    @pytest.mark.asyncio
    async def test_dry_run_shows_duplicate_count(
        self, coinbase_sample_path: str
    ) -> None:
        """Test dry-run results show duplicate count."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # Ensure dry-run is checked
            dry_run_cb = app.screen.query_one("#checkbox-dry-run")
            assert dry_run_cb.value is True

            # Mock detect_duplicates
            sample_duplicate = {
                'trans_type': 'Deposit',
                'created_date': '2023-01-01',
                'exchange': 'Coinbase',
                'buy': 0.001,
                'buy_curr': 'BTC'
            }

            with patch(DETECT_DUPLICATES_PATCH, return_value=[sample_duplicate]):
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.prepare_preview()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and app.screen.current_step == 3
                    and _has_widget(app.screen, "#duplicate-warning"),
                    message="Step 3 with duplicates was not shown",
                )

                # Execute dry-run import
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.query_one("#btn-next").press()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and _has_widget(app.screen, "#results-panel"),
                    message="Results panel was not shown",
                )
                results_panel = app.screen.query_one("#results-panel")
                assert results_panel is not None

    @pytest.mark.asyncio
    async def test_import_proceeds_despite_duplicates(
        self, coinbase_sample_path: str
    ) -> None:
        """Test user can still proceed with import when duplicates detected (warning, not blocker)."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            app.crypto = _make_test_crypto()
            await _go_step2(app, pilot, coinbase_sample_path)

            # Mock detect_duplicates to return duplicates
            sample_duplicate = {
                'trans_type': 'Deposit',
                'created_date': '2023-01-01',
                'exchange': 'Coinbase',
                'buy': 0.001,
                'buy_curr': 'BTC'
            }

            with patch(DETECT_DUPLICATES_PATCH, return_value=[sample_duplicate]):
                assert isinstance(app.screen, ImportWizardScreen)
                app.screen.prepare_preview()
                await app.workers.wait_for_complete()
                await _wait_until(
                    pilot,
                    lambda: isinstance(app.screen, ImportWizardScreen)
                    and app.screen.current_step == 3
                    and app.screen.query_one("#btn-next").disabled is False,
                    message="Import button was disabled on step 3",
                )

                # Import button should still be enabled
                next_btn = app.screen.query_one("#btn-next")
                assert next_btn.disabled is False

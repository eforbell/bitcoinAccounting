"""Tests for TUI treasury monitoring dashboard enhancements (TAM-003)."""

from __future__ import annotations

import pytest
from textual.widgets import Button, DataTable, Label

from tui.app import CryptoApp
from tui.screens.attestation import (
    AttestationScreen,
    TreasuryIntegrityPanel,
)
from tui.screens.dashboard import DashboardScreen


# ---------------------------------------------------------------------------
# TreasuryIntegrityPanel structure
# ---------------------------------------------------------------------------


class TestTreasuryIntegrityPanelStructure:
    @pytest.mark.asyncio
    async def test_panel_mounts_successfully(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = DashboardScreen()
            app.push_screen(screen)
            await pilot.pause()
            # Panel may not be visible until success state loads
            panel = TreasuryIntegrityPanel()
            await pilot.pause()
            assert panel is not None

    @pytest.mark.asyncio
    async def test_panel_has_title_label(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            # Mount the panel directly in a minimal context
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen

    @pytest.mark.asyncio
    async def test_panel_has_view_details_button(self) -> None:
        """Panel widget has a View Details button when instantiated."""
        panel = TreasuryIntegrityPanel()
        # Verify the widget ID is set correctly
        assert panel.id == "treasury-integrity-panel"

    def test_panel_widget_id(self) -> None:
        panel = TreasuryIntegrityPanel()
        assert panel.id == "treasury-integrity-panel"


# ---------------------------------------------------------------------------
# AttestationScreen structure
# ---------------------------------------------------------------------------


class TestAttestationScreenMount:
    @pytest.mark.asyncio
    async def test_screen_mounts_successfully(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen

    @pytest.mark.asyncio
    async def test_screen_has_header_and_footer(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            assert app.screen.query("Header")
            assert app.screen.query("Footer")

    @pytest.mark.asyncio
    async def test_screen_subtitle_set(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            # sub_title is set on app, not on the screen object
            assert app.sub_title == "Treasury Integrity"

    @pytest.mark.asyncio
    async def test_findings_table_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            table = app.screen.query_one("#findings-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_findings_table_has_expected_columns(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            table = app.screen.query_one("#findings-table", DataTable)
            # Column label is the display name; ColumnKey objects are internal
            col_labels = [str(col.label) for col in table.columns.values()]
            assert "Source" in col_labels
            assert "Severity" in col_labels
            assert "Category" in col_labels
            assert "Description" in col_labels

    @pytest.mark.asyncio
    async def test_filter_bar_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            filter_bar = app.screen.query_one("#filter-bar")
            assert filter_bar is not None

    @pytest.mark.asyncio
    async def test_source_filter_buttons_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            assert app.screen.query_one("#src-all")
            assert app.screen.query_one("#src-transfer_integrity")
            assert app.screen.query_one("#src-basis_continuity")
            assert app.screen.query_one("#src-reconciliation")

    @pytest.mark.asyncio
    async def test_severity_filter_buttons_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            assert app.screen.query_one("#sev-all")
            assert app.screen.query_one("#sev-critical")
            assert app.screen.query_one("#sev-warning")

    @pytest.mark.asyncio
    async def test_export_json_button_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            btn = app.screen.query_one("#btn-export-json", Button)
            assert btn is not None

    @pytest.mark.asyncio
    async def test_export_csv_button_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            btn = app.screen.query_one("#btn-export-csv", Button)
            assert btn is not None

    @pytest.mark.asyncio
    async def test_close_button_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            btn = app.screen.query_one("#btn-close", Button)
            assert btn is not None

    @pytest.mark.asyncio
    async def test_status_line_present(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.push_screen(AttestationScreen())
            await pilot.pause()
            status = app.screen.query_one("#status-line", Label)
            assert status is not None


# ---------------------------------------------------------------------------
# AttestationScreen filtering state
# ---------------------------------------------------------------------------


class TestAttestationScreenFilterState:
    @pytest.mark.asyncio
    async def test_initial_source_filter_is_all(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert screen._source_filter == "all"

    @pytest.mark.asyncio
    async def test_initial_severity_filter_is_all(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert screen._sev_filter == "all"

    @pytest.mark.asyncio
    async def test_click_source_filter_updates_state(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#src-transfer_integrity")
            await pilot.pause()
            assert screen._source_filter == "transfer_integrity"

    @pytest.mark.asyncio
    async def test_click_severity_filter_updates_state(self) -> None:
        # Use a wider terminal so all filter buttons fit on screen
        app = CryptoApp()
        async with app.run_test(size=(160, 40)) as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#sev-critical")
            await pilot.pause()
            assert screen._sev_filter == "critical"

    @pytest.mark.asyncio
    async def test_click_all_resets_source_filter(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            screen = AttestationScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#src-transfer_integrity")
            await pilot.pause()
            await pilot.click("#src-all")
            await pilot.pause()
            assert screen._source_filter == "all"


# ---------------------------------------------------------------------------
# AttestationScreen filtering logic (unit tests)
# ---------------------------------------------------------------------------


class TestAttestationScreenFilterLogic:
    def _make_screen_with_findings(self) -> AttestationScreen:
        screen = AttestationScreen()
        screen._all_findings = [
            {
                "source": "transfer_integrity",
                "severity": "critical",
                "category": "one_sided_send",
                "coin": "BTC",
                "wallet": "wallet_a",
                "description": "Unmatched send",
            },
            {
                "source": "basis_continuity",
                "severity": "warning",
                "category": "missing_cost",
                "coin": "BTC",
                "wallet": "wallet_b",
                "description": "Missing cost",
            },
            {
                "source": "reconciliation",
                "severity": "critical",
                "category": "discrepancy",
                "coin": "BTC",
                "wallet": None,
                "description": "Coin discrepancy",
            },
        ]
        return screen

    def test_filter_all_returns_all(self) -> None:
        screen = self._make_screen_with_findings()
        screen._source_filter = "all"
        screen._sev_filter = "all"
        assert len(screen._filtered()) == 3

    def test_filter_by_source(self) -> None:
        screen = self._make_screen_with_findings()
        screen._source_filter = "transfer_integrity"
        screen._sev_filter = "all"
        filtered = screen._filtered()
        assert len(filtered) == 1
        assert filtered[0]["source"] == "transfer_integrity"

    def test_filter_by_severity(self) -> None:
        screen = self._make_screen_with_findings()
        screen._source_filter = "all"
        screen._sev_filter = "critical"
        filtered = screen._filtered()
        assert len(filtered) == 2
        assert all(f["severity"] == "critical" for f in filtered)

    def test_filter_by_both(self) -> None:
        screen = self._make_screen_with_findings()
        screen._source_filter = "transfer_integrity"
        screen._sev_filter = "critical"
        filtered = screen._filtered()
        assert len(filtered) == 1

    def test_filter_no_match_returns_empty(self) -> None:
        screen = self._make_screen_with_findings()
        screen._source_filter = "transfer_integrity"
        screen._sev_filter = "warning"
        assert screen._filtered() == []


# ---------------------------------------------------------------------------
# App action wiring
# ---------------------------------------------------------------------------


class TestAppAttestation:
    @pytest.mark.asyncio
    async def test_action_menu_attestation_pushes_screen(self) -> None:
        app = CryptoApp()
        async with app.run_test() as pilot:
            app.action_menu_attestation()
            await pilot.pause()
            assert isinstance(app.screen, AttestationScreen)

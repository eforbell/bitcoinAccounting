"""Tax reporting screen with gains tracker, 1099-B export, and forecast.

TabbedContent with three tabs for tax planning and reporting functionality.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

if TYPE_CHECKING:
    pass


class TaxReportingScreen(Screen[None]):
    """Screen for tax reporting, gains tracking, and sale forecasting."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
    ]

    CSS = """
    TaxReportingScreen {
        align: center top;
        padding: 1 2;
    }

    #tax-container {
        width: 100%;
        height: 100%;
    }

    /* TabbedContent and Tab styling - override defaults */
    TabbedContent {
        height: 1fr;
    }

    TabbedContent > ContentTabs {
        background: #16213e;
        dock: top;
        height: 3;
    }

    TabbedContent > ContentTabs Tab {
        background: #16213e;
        color: #aaaaaa;
        padding: 0 3;
        min-width: 16;
        height: 2;
        content-align: center middle;
    }

    TabbedContent > ContentTabs Tab:hover {
        background: #0f3460;
        color: #e0e0e0;
    }

    TabbedContent > ContentTabs Tab.-active {
        background: #1a1a2e;
        color: #f7931a;
        text-style: bold;
    }

    TabbedContent > ContentTabs:focus Tab.-active {
        color: #f7931a;
        background: #0f3460;
    }

    TabbedContent > ContentTabs .underline--bar {
        background: #f7931a;
    }

    TabbedContent ContentSwitcher {
        height: 1fr;
    }

    TabbedContent TabPane {
        padding: 0;
        height: 1fr;
    }

    /* Scrollable tab content */
    .tab-scroll {
        height: 1fr;
        padding: 1;
    }

    .section-header {
        height: auto;
        margin-bottom: 1;
        color: #f7931a;
        text-style: bold;
    }

    .form-section {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: #16213e;
        border: solid #444444;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-label {
        width: 18;
        height: auto;
        content-align: right middle;
        margin-right: 2;
    }

    .form-input {
        width: 1fr;
    }

    .summary-section {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: #16213e;
        border: solid #444444;
    }

    .summary-row {
        height: auto;
    }

    .summary-label {
        width: 20;
        color: #888888;
    }

    .summary-value {
        width: 1fr;
        text-style: bold;
    }

    .summary-value-positive {
        color: #00d26a;
    }

    .summary-value-negative {
        color: #e74c3c;
    }

    .data-section {
        height: auto;
        min-height: 8;
        margin-bottom: 1;
    }

    DataTable {
        height: auto;
        min-height: 6;
        max-height: 15;
    }

    #status-message {
        height: auto;
        margin-top: 1;
        padding: 1;
        background: #16213e;
    }

    .success {
        border: solid #00d26a;
        color: #00d26a;
    }

    .error {
        border: solid #e74c3c;
        color: #e74c3c;
    }

    .warning {
        border: solid #f39c12;
        color: #f39c12;
    }

    .warning-section {
        height: auto;
        padding: 1;
        margin-bottom: 1;
        background: #3d2a00;
        border: solid #f39c12;
        color: #f39c12;
    }

    #actions-section {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        """Initialize tax reporting screen."""
        super().__init__()
        self.wallet_names: list[str] = []
        self.gains_data: list[dict[str, str]] = []
        self.worksheet_data: list[dict[str, str]] = []
        self.forecast_lots: list[dict[str, Any]] = []
        self.forecast_summary: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        """Compose the tax reporting screen UI."""
        with Vertical(id="tax-container"):
            yield Label("Tax Reporting", classes="section-header")

            with TabbedContent():
                # Tab 1: Gains Tracker
                with TabPane("Gains Tracker", id="tab-gains"):
                    yield from self._compose_gains_tab()

                # Tab 2: 1099-B Export
                with TabPane("1099-B Export", id="tab-1099b"):
                    yield from self._compose_1099b_tab()

                # Tab 3: Forecast Sale
                with TabPane("Forecast Sale", id="tab-forecast"):
                    yield from self._compose_forecast_tab()

    def _compose_gains_tab(self) -> ComposeResult:
        """Compose the gains tracker tab."""
        with VerticalScroll(classes="tab-scroll"):
            # Controls
            with Container(classes="form-section"):
                yield Label("Filters", classes="section-header")

                with Horizontal(classes="form-row"):
                    yield Label("Tax Year:", classes="form-label")
                    yield Input(
                        value=str(datetime.now().year - 1),
                        placeholder="YYYY",
                        id="gains-year",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Coin:", classes="form-label")
                    yield Select(
                        options=[("BTC", "BTC")],
                        value="BTC",
                        id="gains-coin",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Wallet:", classes="form-label")
                    yield Input(
                        placeholder="All wallets (or specific wallet ID)",
                        id="gains-wallet",
                        classes="form-input",
                    )

                with Horizontal(id="actions-section"):
                    yield Button("Load Gains", id="btn-load-gains", variant="primary")

            # Summary section
            with Container(classes="summary-section", id="gains-summary"):
                yield Label("Summary", classes="section-header")
                with Horizontal(classes="summary-row"):
                    yield Label("Short-term sales:", classes="summary-label")
                    yield Label("-", id="gains-short-count", classes="summary-value")
                with Horizontal(classes="summary-row"):
                    yield Label("Long-term sales:", classes="summary-label")
                    yield Label("-", id="gains-long-count", classes="summary-value")
                with Horizontal(classes="summary-row"):
                    yield Label("Total proceeds:", classes="summary-label")
                    yield Label("-", id="gains-proceeds", classes="summary-value")
                with Horizontal(classes="summary-row"):
                    yield Label("Total cost basis:", classes="summary-label")
                    yield Label("-", id="gains-cost-basis", classes="summary-value")
                with Horizontal(classes="summary-row"):
                    yield Label("Net gain/(loss):", classes="summary-label")
                    yield Label("-", id="gains-net", classes="summary-value")

            # Data table
            with Container(classes="data-section"):
                yield Label("Lot-by-lot Breakdown", classes="section-header")
                yield DataTable[str](id="gains-table")

            yield Static("", id="gains-status")

    def _compose_1099b_tab(self) -> ComposeResult:
        """Compose the 1099-B export tab."""
        with VerticalScroll(classes="tab-scroll"):
            # Warning section (shown for 2025+)
            yield Container(
                Label(
                    "[bold]⚠ IRS 2025+ Per-Wallet Requirement[/bold]\n"
                    "Starting in 2025, the IRS requires per-wallet cost basis tracking.\n"
                    "If no wallet is selected, global FIFO will be used (may not be compliant).",
                ),
                id="irs-warning",
                classes="warning-section",
            )

            # Controls
            with Container(classes="form-section"):
                yield Label("Export Options", classes="section-header")

                with Horizontal(classes="form-row"):
                    yield Label("Tax Year:", classes="form-label")
                    yield Input(
                        value=str(datetime.now().year - 1),
                        placeholder="YYYY",
                        id="export-year",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Coin:", classes="form-label")
                    yield Select(
                        options=[("BTC", "BTC")],
                        value="BTC",
                        id="export-coin",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Wallet:", classes="form-label")
                    yield Input(
                        placeholder="All wallets (or specific wallet ID)",
                        id="export-wallet",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Output File:", classes="form-label")
                    yield Input(
                        value="",
                        placeholder="1099b_YEAR.csv (auto-generated if empty)",
                        id="export-file",
                        classes="form-input",
                    )

                with Horizontal(id="actions-section"):
                    yield Button("Preview", id="btn-preview-1099b", variant="default")
                    yield Button("Export", id="btn-export-1099b", variant="primary")

            # Preview table
            with Container(classes="data-section"):
                yield Label("Preview (first 10 rows)", classes="section-header")
                yield DataTable[str](id="export-table")

            yield Static("", id="export-status")

    def _compose_forecast_tab(self) -> ComposeResult:
        """Compose the forecast sale tab."""
        with VerticalScroll(classes="tab-scroll"):
            # Controls
            with Container(classes="form-section"):
                yield Label("Sale Parameters", classes="section-header")

                with Horizontal(classes="form-row"):
                    yield Label("Coin:", classes="form-label")
                    yield Select(
                        options=[("BTC", "BTC")],
                        value="BTC",
                        id="forecast-coin",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Quantity:", classes="form-label")
                    yield Input(
                        placeholder="Amount to sell (e.g., 0.5)",
                        id="forecast-quantity",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Sale Price (USD):", classes="form-label")
                    yield Input(
                        placeholder="Price per unit (e.g., 95000)",
                        id="forecast-price",
                        classes="form-input",
                    )

                with Horizontal(classes="form-row"):
                    yield Label("Wallet:", classes="form-label")
                    yield Input(
                        placeholder="All wallets (or specific wallet ID)",
                        id="forecast-wallet",
                        classes="form-input",
                    )

                with Horizontal(id="actions-section"):
                    yield Button("Calculate Forecast", id="btn-forecast", variant="primary")

            # Summary section
            with Container(classes="summary-section", id="forecast-summary"):
                yield Label("Tax Implications", classes="section-header")

                with Horizontal(classes="summary-row"):
                    yield Label("Current balance:", classes="summary-label")
                    yield Label("-", id="forecast-balance", classes="summary-value")

                with Horizontal(classes="summary-row"):
                    yield Label("Total proceeds:", classes="summary-label")
                    yield Label("-", id="forecast-proceeds", classes="summary-value")

                with Horizontal(classes="summary-row"):
                    yield Label("Total cost basis:", classes="summary-label")
                    yield Label("-", id="forecast-cost-basis", classes="summary-value")

                with Horizontal(classes="summary-row"):
                    yield Label("Short-term gain:", classes="summary-label")
                    yield Label("-", id="forecast-short-gain", classes="summary-value")

                with Horizontal(classes="summary-row"):
                    yield Label("Long-term gain:", classes="summary-label")
                    yield Label("-", id="forecast-long-gain", classes="summary-value")

                with Horizontal(classes="summary-row"):
                    yield Label("Total gain/(loss):", classes="summary-label")
                    yield Label("-", id="forecast-total-gain", classes="summary-value")

            # Lots table
            with Container(classes="data-section"):
                yield Label("Lots to be Sold (FIFO Order)", classes="section-header")
                yield DataTable[str](id="forecast-table")

            yield Static("", id="forecast-status")

    def on_mount(self) -> None:
        """Load wallets and setup UI after mounting."""
        self.load_wallets()
        self._setup_tables()
        self._update_irs_warning()

    def _setup_tables(self) -> None:
        """Setup DataTable columns."""
        # Gains table
        gains_table = self.query_one("#gains-table", DataTable)
        gains_table.add_column("Sale Date", key="sale_date")
        gains_table.add_column("Quantity", key="quantity")
        gains_table.add_column("Acquire Date", key="acquire_date")
        gains_table.add_column("Term", key="term")
        gains_table.add_column("Proceeds", key="proceeds")
        gains_table.add_column("Cost Basis", key="cost_basis")
        gains_table.add_column("Gain/Loss", key="gain_loss")

        # Export preview table
        export_table = self.query_one("#export-table", DataTable)
        export_table.add_column("Description", key="description")
        export_table.add_column("Date Acquired", key="date_acquired")
        export_table.add_column("Date Sold", key="date_sold")
        export_table.add_column("Proceeds", key="proceeds")
        export_table.add_column("Cost Basis", key="cost_basis")
        export_table.add_column("Term", key="term")

        # Forecast table
        forecast_table = self.query_one("#forecast-table", DataTable)
        forecast_table.add_column("Acquire Date", key="acquire_date")
        forecast_table.add_column("Quantity", key="quantity")
        forecast_table.add_column("Unit Cost", key="unit_cost")
        forecast_table.add_column("Total Cost", key="total_cost")
        forecast_table.add_column("Days Held", key="days_held")
        forecast_table.add_column("Term", key="term")

    def _update_irs_warning(self) -> None:
        """Update IRS warning visibility based on tax year."""
        try:
            year_input = self.query_one("#export-year", Input)
            year = int(year_input.value)
            warning = self.query_one("#irs-warning", Container)

            if year >= 2025:
                warning.display = True
            else:
                warning.display = False
        except (ValueError, Exception):
            pass

    @work(thread=True)
    def load_wallets(self) -> None:
        """Load wallet names from database in background."""
        try:
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                return

            wallets = app.crypto.get_wallets(active_only=False)
            wallet_names = [w["wallet_id"] for w in wallets if w.get("wallet_id")]

            app.call_from_thread(self._update_wallet_list, wallet_names)
        except Exception as e:
            self.log.error(f"Failed to load wallets: {e}")

    def _update_wallet_list(self, wallet_names: list[str]) -> None:
        """Update wallet list (called from thread)."""
        self.wallet_names = wallet_names

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        if button_id == "btn-load-gains":
            self.load_gains_data()
        elif button_id == "btn-preview-1099b":
            self.preview_1099b()
        elif button_id == "btn-export-1099b":
            self.export_1099b()
        elif button_id == "btn-forecast":
            self.calculate_forecast()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "export-year":
            self._update_irs_warning()

    # -------------------------------------------------------------------------
    # Gains Tracker Tab
    # -------------------------------------------------------------------------

    def load_gains_data(self) -> None:
        """Load capital gains data."""
        # Validate year
        year_input = self.query_one("#gains-year", Input)
        try:
            year = int(year_input.value)
            if year < 2009 or year > datetime.now().year:
                self._show_gains_error(f"Invalid year. Must be 2009-{datetime.now().year}")
                return
        except ValueError:
            self._show_gains_error("Invalid year format. Use YYYY")
            return

        coin_select = self.query_one("#gains-coin", Select)
        coin = str(coin_select.value) if coin_select.value else "BTC"

        wallet_input = self.query_one("#gains-wallet", Input)
        wallet = wallet_input.value.strip() or None

        self._load_gains_async(year, coin, wallet)

    @work(thread=True)
    def _load_gains_async(
        self, year: int, coin: str, wallet: str | None
    ) -> None:
        """Load gains data in background."""
        try:
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self._show_gains_error, "Database not connected"
                )
                return

            sales, worksheet = app.crypto.get_sales_for_1099b(coin, year, wallet=wallet)

            app.call_from_thread(self._update_gains_display, sales, worksheet)

        except Exception as e:
            self.log.error(f"Failed to load gains: {e}")
            self.app.call_from_thread(
                self._show_gains_error, f"Failed to load gains: {str(e)}"
            )

    def _update_gains_display(
        self,
        sales: list[dict[str, str]],
        worksheet: list[dict[str, str]],
    ) -> None:
        """Update gains display with data."""
        self.gains_data = sales
        self.worksheet_data = worksheet

        # Calculate summary statistics
        total_proceeds = 0.0
        total_cost_basis = 0.0
        short_term_count = 0
        long_term_count = 0

        for sale in sales:
            total_proceeds += float(sale["Proceeds"])
            total_cost_basis += float(sale["Cost Basis"])
            if sale["Term"] == "Short":
                short_term_count += 1
            else:
                long_term_count += 1

        net_gain = total_proceeds - total_cost_basis

        # Update summary labels
        self.query_one("#gains-short-count", Label).update(str(short_term_count))
        self.query_one("#gains-long-count", Label).update(str(long_term_count))
        self.query_one("#gains-proceeds", Label).update(f"${total_proceeds:,.2f}")
        self.query_one("#gains-cost-basis", Label).update(f"${total_cost_basis:,.2f}")

        net_label = self.query_one("#gains-net", Label)
        net_label.update(f"${net_gain:,.2f}")
        net_label.remove_class("summary-value-positive", "summary-value-negative")
        if net_gain > 0:
            net_label.add_class("summary-value-positive")
        elif net_gain < 0:
            net_label.add_class("summary-value-negative")

        # Update table
        table = self.query_one("#gains-table", DataTable)
        table.clear()

        if not worksheet:
            self._show_gains_status("No sales found for the specified year", "warning")
            return

        for entry in worksheet:
            table.add_row(
                entry["Sale Date"],
                entry["Lot Quantity"],
                entry["Acquire Date"],
                entry["Term"],
                f"${float(entry['Proceeds']):,.2f}",
                f"${float(entry['Total Cost Basis']):,.2f}",
                f"${float(entry['Gain/Loss']):,.2f}",
            )

        self._show_gains_status(
            f"Loaded {len(worksheet)} lot entries from {short_term_count + long_term_count} sales",
            "success",
        )

    def _show_gains_error(self, message: str) -> None:
        """Show error in gains tab."""
        self._show_gains_status(f"[bold]Error:[/bold] {message}", "error")

    def _show_gains_status(self, message: str, status_type: str = "") -> None:
        """Show status message in gains tab."""
        status = self.query_one("#gains-status", Static)
        status.update(message)
        status.remove_class("success", "error", "warning")
        if status_type:
            status.add_class(status_type)

    # -------------------------------------------------------------------------
    # 1099-B Export Tab
    # -------------------------------------------------------------------------

    def preview_1099b(self) -> None:
        """Preview 1099-B export data."""
        # Validate year
        year_input = self.query_one("#export-year", Input)
        try:
            year = int(year_input.value)
            if year < 2009 or year > datetime.now().year:
                self._show_export_error(f"Invalid year. Must be 2009-{datetime.now().year}")
                return
        except ValueError:
            self._show_export_error("Invalid year format. Use YYYY")
            return

        coin_select = self.query_one("#export-coin", Select)
        coin = str(coin_select.value) if coin_select.value else "BTC"

        wallet_input = self.query_one("#export-wallet", Input)
        wallet = wallet_input.value.strip() or None

        self._preview_1099b_async(year, coin, wallet)

    @work(thread=True)
    def _preview_1099b_async(
        self, year: int, coin: str, wallet: str | None
    ) -> None:
        """Preview 1099-B data in background."""
        try:
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self._show_export_error, "Database not connected"
                )
                return

            sales, _ = app.crypto.get_sales_for_1099b(coin, year, wallet=wallet)

            app.call_from_thread(self._update_export_preview, sales)

        except Exception as e:
            self.log.error(f"Failed to preview 1099-B: {e}")
            self.app.call_from_thread(
                self._show_export_error, f"Failed to preview: {str(e)}"
            )

    def _update_export_preview(self, sales: list[dict[str, str]]) -> None:
        """Update export preview table."""
        self.gains_data = sales

        table = self.query_one("#export-table", DataTable)
        table.clear()

        if not sales:
            self._show_export_status("No sales found for the specified year", "warning")
            return

        # Show first 10 rows
        for sale in sales[:10]:
            table.add_row(
                sale["Description"],
                sale["Date Acquired"],
                sale["Date Sold"],
                f"${float(sale['Proceeds']):,.2f}",
                f"${float(sale['Cost Basis']):,.2f}",
                sale["Term"],
            )

        if len(sales) > 10:
            msg = f"Showing first 10 of {len(sales)} entries. Ready to export."
        else:
            msg = f"{len(sales)} entries ready to export."

        self._show_export_status(msg, "success")

    def export_1099b(self) -> None:
        """Export 1099-B data to CSV files."""
        # Validate year
        year_input = self.query_one("#export-year", Input)
        try:
            year = int(year_input.value)
            if year < 2009 or year > datetime.now().year:
                self._show_export_error(f"Invalid year. Must be 2009-{datetime.now().year}")
                return
        except ValueError:
            self._show_export_error("Invalid year format. Use YYYY")
            return

        coin_select = self.query_one("#export-coin", Select)
        coin = str(coin_select.value) if coin_select.value else "BTC"

        wallet_input = self.query_one("#export-wallet", Input)
        wallet = wallet_input.value.strip() or None

        file_input = self.query_one("#export-file", Input)
        output_file = file_input.value.strip()

        # Auto-generate filename if empty
        if not output_file:
            wallet_suffix = f"_{wallet}" if wallet else ""
            output_file = f"1099b_{year}{wallet_suffix}.csv"

        # Expand ~ to home directory
        output_path = Path(output_file).expanduser()

        self._export_1099b_async(year, coin, wallet, str(output_path))

    @work(thread=True)
    def _export_1099b_async(
        self, year: int, coin: str, wallet: str | None, output_file: str
    ) -> None:
        """Export 1099-B data in background."""
        try:
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self._show_export_error, "Database not connected"
                )
                return

            sales, worksheet = app.crypto.get_sales_for_1099b(coin, year, wallet=wallet)

            if not sales:
                self.app.call_from_thread(
                    self._show_export_error, "No sales found. Nothing to export."
                )
                return

            # Write TaxAct CSV format
            fieldnames = [
                "Description",
                "Date Acquired",
                "Date Sold",
                "Proceeds",
                "Cost Basis",
                "Adjustment Code",
                "Adjustment Amount",
                "Wash Sale Loss",
                "Form",
                "Term",
            ]

            with open(output_file, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sales)

            # Write worksheet
            worksheet_file = output_file.replace(".csv", "_worksheet.csv")
            worksheet_fields = [
                "Sale Date",
                "Sale Quantity",
                "Proceeds",
                "Acquire Date",
                "Lot Quantity",
                "Unit Cost Basis",
                "Total Cost Basis",
                "Holding Days",
                "Term",
                "Gain/Loss",
            ]

            with open(worksheet_file, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=worksheet_fields)
                writer.writeheader()
                writer.writerows(worksheet)

            # Calculate totals for notification
            total_proceeds = sum(float(s["Proceeds"]) for s in sales)
            total_cost = sum(float(s["Cost Basis"]) for s in sales)
            net_gain = total_proceeds - total_cost

            self.app.call_from_thread(
                self._show_export_success,
                output_file,
                worksheet_file,
                len(sales),
                net_gain,
            )

            self.app.call_from_thread(
                lambda: app.notify(
                    f"Exported {len(sales)} entries to {output_file}",
                    severity="information",
                )
            )

        except Exception as e:
            self.log.error(f"Failed to export 1099-B: {e}")
            self.app.call_from_thread(
                self._show_export_error, f"Export failed: {str(e)}"
            )

    def _show_export_success(
        self, file1: str, file2: str, count: int, net_gain: float
    ) -> None:
        """Show export success message."""
        gain_str = f"${net_gain:,.2f}" if net_gain >= 0 else f"-${abs(net_gain):,.2f}"
        status = self.query_one("#export-status", Static)
        status.update(
            f"[bold]Success![/bold] Exported {count} entries\n"
            f"1099-B form: {file1}\n"
            f"Worksheet: {file2}\n"
            f"Net gain/(loss): {gain_str}"
        )
        status.remove_class("error", "warning")
        status.add_class("success")

    def _show_export_error(self, message: str) -> None:
        """Show error in export tab."""
        self._show_export_status(f"[bold]Error:[/bold] {message}", "error")

    def _show_export_status(self, message: str, status_type: str = "") -> None:
        """Show status message in export tab."""
        status = self.query_one("#export-status", Static)
        status.update(message)
        status.remove_class("success", "error", "warning")
        if status_type:
            status.add_class(status_type)

    # -------------------------------------------------------------------------
    # Forecast Tab
    # -------------------------------------------------------------------------

    def calculate_forecast(self) -> None:
        """Calculate sale forecast."""
        coin_select = self.query_one("#forecast-coin", Select)
        coin = str(coin_select.value) if coin_select.value else "BTC"

        # Validate quantity
        qty_input = self.query_one("#forecast-quantity", Input)
        try:
            quantity = float(qty_input.value)
            if quantity <= 0:
                self._show_forecast_error("Quantity must be positive")
                return
        except ValueError:
            self._show_forecast_error("Invalid quantity. Enter a number.")
            return

        # Validate price
        price_input = self.query_one("#forecast-price", Input)
        try:
            sale_price = float(price_input.value)
            if sale_price <= 0:
                self._show_forecast_error("Sale price must be positive")
                return
        except ValueError:
            self._show_forecast_error("Invalid sale price. Enter a number.")
            return

        wallet_input = self.query_one("#forecast-wallet", Input)
        wallet = wallet_input.value.strip() or None

        self._calculate_forecast_async(coin, quantity, sale_price, wallet)

    @work(thread=True)
    def _calculate_forecast_async(
        self, coin: str, quantity: float, sale_price: float, wallet: str | None
    ) -> None:
        """Calculate forecast in background."""
        try:
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self._show_forecast_error, "Database not connected"
                )
                return

            # Get current balance
            if wallet:
                current_balance = float(app.crypto.get_wallet_balance(coin, wallet))
            else:
                current_balance = float(app.crypto.get_balance(coin))

            # Get forecast
            lots, summary = app.crypto.forecast_capital_gains_fifo(
                coin, quantity, sale_price, wallet=wallet
            )

            app.call_from_thread(
                self._update_forecast_display,
                lots,
                summary,
                current_balance,
                quantity,
                sale_price,
                coin,
            )

        except Exception as e:
            self.log.error(f"Failed to calculate forecast: {e}")
            self.app.call_from_thread(
                self._show_forecast_error, f"Forecast failed: {str(e)}"
            )

    def _update_forecast_display(
        self,
        lots: list[dict[str, Any]],
        summary: dict[str, Any],
        current_balance: float,
        quantity: float,
        sale_price: float,
        coin: str,
    ) -> None:
        """Update forecast display with data."""
        self.forecast_lots = lots
        self.forecast_summary = summary

        total_proceeds = quantity * sale_price

        # Update summary labels
        self.query_one("#forecast-balance", Label).update(
            f"{current_balance:.8f} {coin}"
        )
        self.query_one("#forecast-proceeds", Label).update(f"${total_proceeds:,.2f}")

        if summary:
            total_cost_basis = summary.get("total_cost_basis", 0)
            short_term_gain = summary.get("short_term_proceeds", 0) - summary.get(
                "short_term_cost", 0
            )
            long_term_gain = summary.get("long_term_proceeds", 0) - summary.get(
                "long_term_cost", 0
            )
            total_gain = total_proceeds - total_cost_basis

            self.query_one("#forecast-cost-basis", Label).update(
                f"${total_cost_basis:,.2f}"
            )

            # Short-term gain with color
            short_label = self.query_one("#forecast-short-gain", Label)
            short_label.update(f"${short_term_gain:,.2f}")
            short_label.remove_class("summary-value-positive", "summary-value-negative")
            if short_term_gain > 0:
                short_label.add_class("summary-value-positive")
            elif short_term_gain < 0:
                short_label.add_class("summary-value-negative")

            # Long-term gain with color
            long_label = self.query_one("#forecast-long-gain", Label)
            long_label.update(f"${long_term_gain:,.2f}")
            long_label.remove_class("summary-value-positive", "summary-value-negative")
            if long_term_gain > 0:
                long_label.add_class("summary-value-positive")
            elif long_term_gain < 0:
                long_label.add_class("summary-value-negative")

            # Total gain with color
            total_label = self.query_one("#forecast-total-gain", Label)
            total_label.update(f"${total_gain:,.2f}")
            total_label.remove_class("summary-value-positive", "summary-value-negative")
            if total_gain > 0:
                total_label.add_class("summary-value-positive")
            elif total_gain < 0:
                total_label.add_class("summary-value-negative")

        # Update table
        table = self.query_one("#forecast-table", DataTable)
        table.clear()

        if not lots:
            self._show_forecast_status(
                "No purchase history found. Unable to calculate cost basis.", "warning"
            )
            return

        for lot in lots:
            acquire_date = (
                lot["acquire_date"].strftime("%m/%d/%Y")
                if lot["acquire_date"]
                else "UNKNOWN"
            )
            table.add_row(
                acquire_date,
                f"{lot['quantity']:.8f}",
                f"${lot['unit_cost']:,.2f}",
                f"${lot['cost_basis']:,.2f}",
                str(lot["holding_days"]),
                lot["term"],
            )

        # Build status message
        status_msg = f"Forecast: Selling {quantity:.8f} {coin} @ ${sale_price:,.2f}"
        if quantity > current_balance:
            status_msg += f"\n⚠ Warning: Selling more than current balance ({current_balance:.8f} {coin})"

        if summary and summary.get("missing_basis_count", 0) > 0:
            status_msg += (
                f"\n⚠ Warning: {summary['missing_basis_count']} lot(s) with missing cost basis"
            )

        self._show_forecast_status(status_msg, "success" if quantity <= current_balance else "warning")

    def _show_forecast_error(self, message: str) -> None:
        """Show error in forecast tab."""
        self._show_forecast_status(f"[bold]Error:[/bold] {message}", "error")

    def _show_forecast_status(self, message: str, status_type: str = "") -> None:
        """Show status message in forecast tab."""
        status = self.query_one("#forecast-status", Static)
        status.update(message)
        status.remove_class("success", "error", "warning")
        if status_type:
            status.add_class(status_type)

"""Export transactions screen for exporting ledger to CSV.

Single-screen form with filters, preview, and export functionality.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static

if TYPE_CHECKING:
    from textual.worker import Worker


class ExportScreen(Screen[None]):
    """Screen for exporting transactions to CSV with filtering."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "reload_preview", "Reload Preview", show=False),
    ]

    CSS = """
    ExportScreen {
        align: center top;
        padding: 1 2;
    }

    #export-container {
        width: 100%;
        height: auto;
    }

    .section-header {
        height: auto;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .form-section {
        height: auto;
        margin-bottom: 2;
        padding: 1;
        background: $surface;
        border: solid $primary;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-label {
        width: 20;
        height: auto;
        content-align: right middle;
        margin-right: 2;
    }

    .form-input {
        width: 1fr;
    }

    #preview-section {
        height: auto;
        max-height: 25;
        margin-bottom: 2;
    }

    #preview-table {
        height: auto;
        min-height: 10;
        max-height: 20;
    }

    #preview-info {
        height: auto;
        margin-top: 1;
        color: $text-muted;
    }

    #actions-section {
        height: auto;
        align: center middle;
    }

    #status-message {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: $surface-darken-1;
    }

    .success {
        border: solid $success;
        color: $success;
    }

    .error {
        border: solid $error;
        color: $error;
    }
    """

    def __init__(self) -> None:
        """Initialize export screen."""
        super().__init__()
        self.wallet_names: list[str] = []
        self.preview_transactions: list[dict[str, Any]] = []
        self.preview_columns: list[str] = []

    def compose(self) -> ComposeResult:
        """Compose the export screen UI."""
        with Vertical(id="export-container"):
            yield Label("Export Transactions", classes="section-header")

            # Filters form
            with Container(classes="form-section"):
                yield Label("Filters", classes="section-header")

                # Coin selector
                row = Horizontal(classes="form-row")
                yield row

                # Wallet selector (will be populated on mount)
                row2 = Horizontal(classes="form-row")
                yield row2

                # Start date
                row3 = Horizontal(classes="form-row")
                yield row3

                # End date
                row4 = Horizontal(classes="form-row")
                yield row4

                # Output file path
                row5 = Horizontal(classes="form-row")
                yield row5

            # Preview section
            with Container(id="preview-section"):
                yield Label("Preview", classes="section-header")
                yield DataTable[str](id="preview-table")
                yield Label("", id="preview-info")

            # Status message (initially hidden)
            yield Static("", id="status-message")

            # Action buttons
            with Horizontal(id="actions-section"):
                yield Button("Preview", id="btn-preview", variant="default")
                yield Button("Export", id="btn-export", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        """Load wallets and build form after mounting."""
        self.load_wallets()
        self.build_form()

    def build_form(self) -> None:
        """Build form fields."""
        # Find the form rows
        rows = list(self.query(".form-row").results())
        if len(rows) < 5:
            return

        # Row 1: Coin selector
        rows[0].mount(Label("Coin:", classes="form-label"))
        rows[0].mount(Select(
            options=[("BTC", "BTC"), ("All Coins", "")],
            value="BTC",
            id="select-coin",
            classes="form-input"
        ))

        # Row 2: Wallet selector (multi-select via comma-separated input)
        rows[1].mount(Label("Wallets:", classes="form-label"))
        rows[1].mount(Input(
            placeholder="All wallets (or comma-separated: Strike,Coldcard,Vault)",
            id="input-wallets",
            classes="form-input"
        ))

        # Row 3: Start date
        rows[2].mount(Label("Start Date:", classes="form-label"))
        rows[2].mount(Input(
            placeholder="YYYY-MM-DD (optional)",
            id="input-start-date",
            classes="form-input"
        ))

        # Row 4: End date
        rows[3].mount(Label("End Date:", classes="form-label"))
        rows[3].mount(Input(
            placeholder="YYYY-MM-DD (optional)",
            id="input-end-date",
            classes="form-input"
        ))

        # Row 5: Output file path
        rows[4].mount(Label("Output File:", classes="form-label"))
        rows[4].mount(Input(
            value="ledger_export.csv",
            id="input-output-file",
            classes="form-input"
        ))

    @work(thread=True)
    def load_wallets(self) -> None:
        """Load wallet names from database in background."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                return

            # Get wallet names
            wallets = app.crypto.get_wallets(active_only=False)
            wallet_names = [w['wallet_id'] for w in wallets if w.get('wallet_id')]

            # Update UI from thread
            app.call_from_thread(self._update_wallet_list, wallet_names)
        except Exception as e:
            self.log.error(f"Failed to load wallets: {e}")

    def _update_wallet_list(self, wallet_names: list[str]) -> None:
        """Update wallet list (called from thread)."""
        self.wallet_names = wallet_names

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-cancel":
            self.app.pop_screen()
        elif button_id == "btn-preview":
            self.load_preview()
        elif button_id == "btn-export":
            self.execute_export()

    def load_preview(self) -> None:
        """Load preview of transactions to be exported."""
        # Validate dates
        start_date_input = self.query_one("#input-start-date", Input)
        end_date_input = self.query_one("#input-end-date", Input)

        start_date = start_date_input.value.strip() or None
        end_date = end_date_input.value.strip() or None

        # Validate date formats
        if start_date:
            if not self._validate_date(start_date):
                self.show_error("Invalid start date format. Use YYYY-MM-DD")
                return

        if end_date:
            if not self._validate_date(end_date):
                self.show_error("Invalid end date format. Use YYYY-MM-DD")
                return

        # Load preview async
        self.load_preview_async(start_date, end_date)

    def _validate_date(self, date_str: str) -> bool:
        """Validate date format (YYYY-MM-DD)."""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    @work(thread=True)
    def load_preview_async(self, start_date: str | None, end_date: str | None) -> None:
        """Load preview data in background."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self.show_error,
                    "Database not connected"
                )
                return

            # Get filter values
            coin_select = self.query_one("#select-coin", Select)
            coin = str(coin_select.value) if coin_select.value else None
            if coin == "":
                coin = None

            wallets_input = self.query_one("#input-wallets", Input)
            wallets_str = wallets_input.value.strip()
            wallet: str | list[str] | None = None
            if wallets_str:
                # Parse comma-separated wallets
                wallet = [w.strip() for w in wallets_str.split(',') if w.strip()]
                if len(wallet) == 1:
                    wallet = wallet[0]  # Single wallet as string
                elif len(wallet) == 0:
                    wallet = None

            # Get transactions
            colnames, transactions = app.crypto.get_transactions(
                coin=coin,
                wallet=wallet,
                start_date=start_date,
                end_date=end_date
            )

            # Update UI from thread
            self.app.call_from_thread(
                self._show_preview,
                colnames,
                transactions
            )

        except Exception as e:
            self.log.error(f"Preview failed: {e}")
            self.app.call_from_thread(
                self.show_error,
                f"Failed to load preview: {str(e)}"
            )

    def _show_preview(self, colnames: list[str], transactions: list[dict[str, Any]]) -> None:
        """Show preview in UI (called from thread)."""
        self.preview_columns = colnames
        self.preview_transactions = transactions

        # Clear and rebuild table
        table: DataTable[str] = self.query_one("#preview-table", DataTable)
        table.clear(columns=True)

        if not transactions:
            # Show empty message
            preview_info = self.query_one("#preview-info", Label)
            preview_info.update("No transactions match the specified filters")
            return

        # Add columns
        for col in colnames:
            table.add_column(col, key=col)

        # Add first 10 rows
        preview_txs = transactions[:10]
        for tx in preview_txs:
            row_data = [str(tx.get(col, '')) for col in colnames]
            table.add_row(*row_data)

        # Update info
        preview_info = self.query_one("#preview-info", Label)
        if len(transactions) > 10:
            preview_info.update(f"Showing first 10 of {len(transactions)} transactions")
        else:
            preview_info.update(f"{len(transactions)} transactions ready to export")

        # Hide status message
        status = self.query_one("#status-message", Static)
        status.update("")
        status.remove_class("success", "error")

    def execute_export(self) -> None:
        """Execute the export to CSV file."""
        # Validate we have preview data
        if not self.preview_transactions:
            self.show_error("Please preview first before exporting")
            return

        # Validate output file path
        output_file_input = self.query_one("#input-output-file", Input)
        output_file = output_file_input.value.strip()

        if not output_file:
            self.show_error("Please specify an output file path")
            return

        # Expand ~ to home directory
        output_path = Path(output_file).expanduser()

        # Export async
        self.execute_export_async(str(output_path))

    @work(thread=True)
    def execute_export_async(self, output_file: str) -> None:
        """Execute export in background."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self.show_error,
                    "Database not connected"
                )
                return

            # Get filter values (same as preview)
            coin_select = self.query_one("#select-coin", Select)
            coin = str(coin_select.value) if coin_select.value else None
            if coin == "":
                coin = None

            wallets_input = self.query_one("#input-wallets", Input)
            wallets_str = wallets_input.value.strip()
            wallet: str | list[str] | None = None
            if wallets_str:
                wallet = [w.strip() for w in wallets_str.split(',') if w.strip()]
                if len(wallet) == 1:
                    wallet = wallet[0]
                elif len(wallet) == 0:
                    wallet = None

            start_date_input = self.query_one("#input-start-date", Input)
            end_date_input = self.query_one("#input-end-date", Input)
            start_date = start_date_input.value.strip() or None
            end_date = end_date_input.value.strip() or None

            # Export to CSV
            app.crypto.export_transactions_csv(
                output_file,
                coin=coin,
                wallet=wallet,
                start_date=start_date,
                end_date=end_date
            )

            # Show success
            self.app.call_from_thread(
                self.show_success,
                output_file,
                len(self.preview_transactions)
            )

            # Notify
            self.app.call_from_thread(
                lambda: app.notify(
                    f"Exported {len(self.preview_transactions)} transactions to {output_file}",
                    severity="information"
                )
            )

        except Exception as e:
            self.log.error(f"Export failed: {e}")
            self.app.call_from_thread(
                self.show_error,
                f"Export failed: {str(e)}"
            )

    def show_error(self, message: str) -> None:
        """Show error message."""
        status = self.query_one("#status-message", Static)
        status.update(f"[bold]Error:[/bold] {message}")
        status.remove_class("success")
        status.add_class("error")

    def show_success(self, file_path: str, count: int) -> None:
        """Show success message."""
        status = self.query_one("#status-message", Static)
        status.update(
            f"[bold]Success![/bold] Exported {count} transactions to:\n{file_path}"
        )
        status.remove_class("error")
        status.add_class("success")

    def action_reload_preview(self) -> None:
        """Reload the preview."""
        self.load_preview()

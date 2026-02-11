"""Transaction ledger screen with filtering and sorting capabilities."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

if TYPE_CHECKING:
    from tui.app import CryptoApp


class LedgerScreen(Screen[None]):
    """Screen displaying transaction ledger with filtering capabilities."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "reload_transactions", "Reload", show=True),
    ]

    DEFAULT_CSS = """
    LedgerScreen {
        layout: vertical;
    }

    LedgerScreen Container {
        layout: vertical;
        height: auto;
    }

    LedgerScreen .filter-panel {
        layout: horizontal;
        height: 7;
        padding: 1 2;
        background: #16213e;
        border: solid #444444;
    }

    LedgerScreen .filter-group {
        layout: vertical;
        width: 1fr;
        height: auto;
        padding: 0 1;
    }

    LedgerScreen .filter-label {
        color: #888888;
        text-style: bold;
        height: 1;
    }

    LedgerScreen Input {
        height: 3;
        margin: 0 0 1 0;
    }

    LedgerScreen Select {
        height: auto;
        min-height: 3;
        margin: 0 0 1 0;
    }

    LedgerScreen .status-bar {
        layout: horizontal;
        height: 3;
        padding: 1 2;
        background: #0f3460;
    }

    LedgerScreen .status-label {
        color: #e0e0e0;
    }

    LedgerScreen DataTable {
        height: 1fr;
        min-height: 15;
    }

    LedgerScreen Button {
        height: 3;
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.all_transactions: list[dict[str, Any]] = []
        self.filtered_transactions: list[dict[str, Any]] = []
        self.column_names: list[str] = []
        self.current_coin: str | None = "BTC"  # Default to BTC, can be None (All), "BTC", or "USD"
        self.current_wallet: str | None = None
        self.start_date: str | None = None
        self.end_date: str | None = None
        self.sort_column: str | None = None
        self.sort_reverse = False

    def compose(self) -> ComposeResult:
        """Compose the ledger screen layout."""
        yield Header()

        # Filter panel
        with Container(classes="filter-panel"):
            with Horizontal():
                with Vertical(classes="filter-group"):
                    yield Label("Coin:", classes="filter-label")
                    yield Select(
                        options=[("All", None), ("BTC", "BTC"), ("USD", "USD")],
                        value="BTC",
                        id="coin-select",
                        allow_blank=False,
                    )

                with Vertical(classes="filter-group"):
                    yield Label("Wallet (optional):", classes="filter-label")
                    yield Select(
                        options=[("All Wallets", None)],
                        prompt="All Wallets",
                        id="wallet-select",
                        allow_blank=True,
                    )

                with Vertical(classes="filter-group"):
                    yield Label("Start Date (YYYY-MM-DD):", classes="filter-label")
                    yield Input(
                        placeholder="e.g., 2024-01-01",
                        id="start-date-input",
                    )

                with Vertical(classes="filter-group"):
                    yield Label("End Date (YYYY-MM-DD):", classes="filter-label")
                    yield Input(
                        placeholder="e.g., 2024-12-31",
                        id="end-date-input",
                    )

                with Vertical(classes="filter-group"):
                    yield Label(" ", classes="filter-label")  # Spacing
                    yield Button("Apply Filters", id="apply-filters-btn", variant="primary")

        # Status bar
        with Container(classes="status-bar"):
            yield Label("", id="status-label", classes="status-label")

        # Transaction table
        yield DataTable(id="transactions-table", cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        """Load initial data and populate wallet selector."""
        self.sub_title = "Transaction Ledger"
        self.load_wallets()
        self.load_transactions()

    @work(thread=True)
    def load_wallets(self) -> None:
        """Load wallet list for filter selector."""
        try:
            # Import inside worker to avoid threading issues
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                return

            wallets = app.crypto.wallet_query.get_wallets(active_only=False)  # type: ignore[attr-defined]

            # Build wallet options
            # Note: get_wallets() returns dicts with 'wallet_id' key, not 'wallet_name'
            wallet_options = [("All Wallets", None)]
            for wallet in wallets:
                wallet_id = wallet.get("wallet_id", "Unknown")
                wallet_options.append((wallet_id, wallet_id))

            # Update wallet selector from main thread
            def update_wallet_select() -> None:
                select = self.query_one("#wallet-select", Select)
                select.set_options(wallet_options)

            self.app.call_from_thread(update_wallet_select)

        except Exception as e:
            error_msg = f"Error loading wallets: {e}"

            def show_error() -> None:
                self.app.notify(error_msg, severity="error")

            self.app.call_from_thread(show_error)

    @work(thread=True)
    def load_transactions(self) -> None:
        """Load and display transactions with current filters."""
        try:
            # Import inside worker to avoid threading issues
            from tui.app import CryptoApp

            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                def show_empty() -> None:
                    self._show_empty_state()

                self.app.call_from_thread(show_empty)
                return

            # Show loading state
            def show_loading() -> None:
                status = self.query_one("#status-label", Label)
                status.update("[yellow]Loading transactions...[/yellow]")

            self.app.call_from_thread(show_loading)

            # Get transactions with filters
            kwargs: dict[str, Any] = {}
            if self.current_coin:  # Only filter by coin if specified (None = All)
                kwargs["coin"] = self.current_coin
            if self.current_wallet:
                kwargs["wallet"] = self.current_wallet
            if self.start_date:
                kwargs["start_date"] = self.start_date
            if self.end_date:
                kwargs["end_date"] = self.end_date

            headers, transactions = app.crypto.get_transactions(**kwargs)  # type: ignore[no-untyped-call]

            # Store data
            self.column_names = list(headers)
            self.all_transactions = list(transactions)
            self.filtered_transactions = list(transactions)

            # Apply sorting if set
            if self.sort_column and self.sort_column in self.column_names:
                self.filtered_transactions.sort(
                    key=lambda row: row.get(self.sort_column, "") or "",
                    reverse=self.sort_reverse,
                )

            # Update UI from main thread
            def update_ui() -> None:
                self._populate_table()
                self._update_status()

            self.app.call_from_thread(update_ui)

        except Exception as e:
            error_msg = f"Error loading transactions: {e}"

            def show_error() -> None:
                self.app.notify(error_msg, severity="error")
                status = self.query_one("#status-label", Label)
                status.update(f"[red]Error: {e}[/red]")

            self.app.call_from_thread(show_error)

    def _populate_table(self) -> None:
        """Populate the DataTable with transaction data."""
        table = self.query_one("#transactions-table", DataTable)
        table.clear(columns=True)

        if not self.column_names:
            return

        # Add columns
        for col_name in self.column_names:
            table.add_column(col_name, key=col_name)

        # Add rows
        # Note: get_transactions() returns list of dicts, not tuples
        for row_dict in self.filtered_transactions:
            # Extract values in the same order as column_names
            display_row = [str(row_dict.get(col, "")) if row_dict.get(col) is not None else ""
                          for col in self.column_names]
            table.add_row(*display_row)

    def _update_status(self) -> None:
        """Update the status bar with row counts."""
        status = self.query_one("#status-label", Label)
        total = len(self.all_transactions)
        filtered = len(self.filtered_transactions)

        if total == filtered:
            status.update(f"Showing [cyan]{total}[/cyan] transactions")
        else:
            status.update(
                f"Showing [cyan]{filtered}[/cyan] of [cyan]{total}[/cyan] transactions"
            )

    def _show_empty_state(self) -> None:
        """Show empty state when no transactions exist."""
        status = self.query_one("#status-label", Label)
        status.update("[yellow]No transactions found. Import data to get started.[/yellow]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "apply-filters-btn":
            self._apply_filters()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header clicks for sorting."""
        column_key = str(event.column_key)

        # Toggle sort direction if same column clicked
        if self.sort_column == column_key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column_key
            self.sort_reverse = False

        # Re-sort and update display
        if self.sort_column and self.sort_column in self.column_names:
            self.filtered_transactions.sort(
                key=lambda row: row.get(self.sort_column, "") or "",
                reverse=self.sort_reverse,
            )

            self._populate_table()

            # Update status to show sort indicator
            sort_dir = "↓" if self.sort_reverse else "↑"
            status = self.query_one("#status-label", Label)
            current_status = status.content
            status.update(f"{current_status} | Sorted by {self.sort_column} {sort_dir}")

    def _apply_filters(self) -> None:
        """Apply current filter values and reload transactions."""
        # Get filter values
        coin_select = self.query_one("#coin-select", Select)
        wallet_select = self.query_one("#wallet-select", Select)
        start_input = self.query_one("#start-date-input", Input)
        end_input = self.query_one("#end-date-input", Input)

        # coin_select.value can be None (All), "BTC", or "USD"
        self.current_coin = str(coin_select.value) if coin_select.value else None
        self.current_wallet = str(wallet_select.value) if wallet_select.value else None
        self.start_date = start_input.value.strip() if start_input.value else None
        self.end_date = end_input.value.strip() if end_input.value else None

        # Validate date formats
        if self.start_date and not self._is_valid_date(self.start_date):
            self.app.notify("Invalid start date format. Use YYYY-MM-DD", severity="error")
            return

        if self.end_date and not self._is_valid_date(self.end_date):
            self.app.notify("Invalid end date format. Use YYYY-MM-DD", severity="error")
            return

        # Reload with new filters
        self.load_transactions()

    def _is_valid_date(self, date_str: str) -> bool:
        """Validate date string format (YYYY-MM-DD)."""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def action_reload_transactions(self) -> None:
        """Reload transactions with current filters."""
        self.load_transactions()

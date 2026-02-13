"""Transaction ledger screen with filtering and sorting capabilities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

if TYPE_CHECKING:
    from tui.app import CryptoApp


# Fields to display in detail modal, in order: (label, dict_key)
_DETAIL_FIELDS = [
    ("Transaction ID", "ID"),
    ("Date", "Date"),
    ("Type", "Type"),
    ("Buy Amount", "Buy"),
    ("Buy Currency", "Buy Cur."),
    ("Sell Amount", "Sell"),
    ("Sell Currency", "Sell Cur."),
    ("Fee", "Fee"),
    ("Fee Currency", "Fee Cur."),
    ("Wallet / Exchange", "Exchange"),
    ("Group", "Group"),
    ("Comment", "Comment"),
]


class TransactionDetailModal(ModalScreen[str | None]):
    """Modal showing full transaction details with Edit/Delete/Close actions."""

    CSS = """
    TransactionDetailModal {
        align: center middle;
    }

    #detail-container {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #detail-title {
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    .detail-row {
        height: auto;
        layout: horizontal;
        margin-bottom: 0;
    }

    .detail-field-name {
        width: 22;
        color: #888888;
        text-style: bold;
    }

    .detail-field-value {
        width: 1fr;
        color: #e0e0e0;
    }

    #detail-button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #detail-button-row Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
    ]

    def __init__(self, transaction: dict[str, Any]) -> None:
        super().__init__()
        self.transaction = transaction

    def compose(self) -> ComposeResult:
        with Container(id="detail-container"):
            yield Label("Transaction Details", id="detail-title")

            for label, key in _DETAIL_FIELDS:
                value = self.transaction.get(key, "")
                display_val = str(value) if value is not None and value != "" else "—"
                with Horizontal(classes="detail-row"):
                    yield Label(f"{label}:", classes="detail-field-name")
                    yield Label(display_val, classes="detail-field-value")

            with Horizontal(id="detail-button-row"):
                yield Button("Edit", variant="primary", id="detail-edit-btn")
                yield Button("Delete", variant="warning", id="detail-delete-btn")
                yield Button("Close", variant="default", id="detail-close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detail-edit-btn":
            self.dismiss("edit")
        elif event.button.id == "detail-delete-btn":
            self.dismiss("delete")
        elif event.button.id == "detail-close-btn":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


# Mapping: (display label, transaction dict key, DB column name)
_EDIT_FIELDS = [
    ("Date", "Date", "createddate"),
    ("Buy Amount", "Buy", "buy"),
    ("Buy Currency", "Buy Cur.", "buy_curr"),
    ("Sell Amount", "Sell", "sell"),
    ("Sell Currency", "Sell Cur.", "sell_curr"),
    ("Fee", "Fee", "fee"),
    ("Fee Currency", "Fee Cur.", "fee_curr"),
    ("Group", "Group", "group"),
    ("Comment", "Comment", "comment"),
]

_TRANSACTION_TYPES = [
    ("Deposit", "Deposit"),
    ("Withdrawal", "Withdrawal"),
    ("Trade", "Trade"),
    ("Spend", "Spend"),
    ("Mining", "Mining"),
    ("Interest Income", "Interest Income"),
]


class EditTransactionModal(ModalScreen[bool]):
    """Modal for editing a transaction with pre-populated fields and diff preview."""

    CSS = """
    EditTransactionModal {
        align: center middle;
    }

    #edit-tx-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        overflow-y: auto;
    }

    #edit-tx-title {
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    .edit-form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 0;
    }

    .edit-form-label {
        width: 18;
        padding-right: 1;
        color: $text-muted;
    }

    EditTransactionModal Input {
        width: 50;
    }

    EditTransactionModal Select {
        width: 50;
    }

    #edit-tx-diff {
        margin-top: 1;
        padding: 1;
        color: #f7931a;
        text-style: italic;
    }

    #edit-tx-error {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }

    #edit-tx-button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #edit-tx-button-row Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        transaction: dict[str, Any],
        wallet_options: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.transaction = transaction
        self.wallet_options = wallet_options

    def compose(self) -> ComposeResult:
        tx = self.transaction
        with Container(id="edit-tx-container"):
            yield Label(
                f"Edit Transaction #{tx.get('ID', '?')}",
                id="edit-tx-title",
            )
            yield Label("", id="edit-tx-error")

            # Transaction type (Select)
            with Horizontal(classes="edit-form-row"):
                yield Label("Type:", classes="edit-form-label")
                yield Select(
                    options=_TRANSACTION_TYPES,
                    value=tx.get("Type", "Deposit"),
                    id="edit-type",
                    allow_blank=False,
                )

            # Wallet / Exchange (Select)
            with Horizontal(classes="edit-form-row"):
                yield Label("Wallet:", classes="edit-form-label")
                current_exchange = tx.get("Exchange", "")
                # Ensure current value is in options
                opts = list(self.wallet_options)
                existing_values = {v for _, v in opts}
                if current_exchange and current_exchange not in existing_values:
                    opts.append((current_exchange, current_exchange))
                yield Select(
                    options=opts,
                    value=current_exchange,
                    id="edit-exchange",
                    allow_blank=False,
                )

            # Text/numeric input fields
            for label, tx_key, db_col in _EDIT_FIELDS:
                val = tx.get(tx_key)
                display_val = str(val) if val is not None else ""
                input_id = f"edit-{db_col.replace('_', '-')}"
                with Horizontal(classes="edit-form-row"):
                    yield Label(f"{label}:", classes="edit-form-label")
                    yield Input(
                        value=display_val,
                        placeholder=label,
                        id=input_id,
                    )

            # Diff preview
            yield Label("", id="edit-tx-diff")

            # Buttons
            with Horizontal(id="edit-tx-button-row"):
                yield Button("Save", variant="primary", id="edit-save-btn")
                yield Button("Cancel", variant="default", id="edit-cancel-btn")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update diff preview when any input changes."""
        self._update_diff()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Update diff preview when a select changes."""
        self._update_diff()

    def _get_changes(self) -> dict[str, tuple[Any, Any]]:
        """Build dict of {db_col: (old_value, new_value)} for changed fields."""
        tx = self.transaction
        changes: dict[str, tuple[Any, Any]] = {}

        # Check type
        new_type = str(self.query_one("#edit-type", Select).value)
        old_type = tx.get("Type", "")
        if new_type != old_type:
            changes["trans_type"] = (old_type, new_type)

        # Check exchange
        new_exchange = str(self.query_one("#edit-exchange", Select).value)
        old_exchange = tx.get("Exchange", "")
        if new_exchange != old_exchange:
            changes["exchange"] = (old_exchange, new_exchange)

        # Check text/numeric fields
        for _label, tx_key, db_col in _EDIT_FIELDS:
            input_id = f"edit-{db_col.replace('_', '-')}"
            new_val = self.query_one(f"#{input_id}", Input).value.strip()
            old_val = tx.get(tx_key)
            old_str = str(old_val) if old_val is not None else ""

            if new_val != old_str:
                changes[db_col] = (old_str, new_val)

        return changes

    def _update_diff(self) -> None:
        """Update the diff preview label."""
        changes = self._get_changes()
        diff_label = self.query_one("#edit-tx-diff", Label)

        if not changes:
            diff_label.update("")
            return

        parts = []
        for col, (old, new) in changes.items():
            old_display = old if old else '(empty)'
            new_display = new if new else '(empty)'
            parts.append(f"{col}: {old_display} → {new_display}")

        diff_label.update(f"Changes: {', '.join(parts)}")

    def _validate_and_save(self) -> None:
        """Validate inputs and save changes."""
        error_label = self.query_one("#edit-tx-error", Label)
        changes = self._get_changes()

        if not changes:
            self.dismiss(False)
            return

        # Validate date format if changed
        if "createddate" in changes:
            new_date = changes["createddate"][1]
            try:
                datetime.strptime(new_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                error_label.update("Invalid date format. Use YYYY-MM-DD HH:MM:SS")
                return

        # Validate numeric fields
        for num_field in ("buy", "sell", "fee"):
            if num_field in changes:
                new_val = changes[num_field][1]
                if new_val:  # allow empty (will become None/0)
                    try:
                        float(new_val)
                    except ValueError:
                        error_label.update(f"Invalid number for {num_field}: {new_val}")
                        return

        # Build kwargs for update_transaction
        kwargs: dict[str, Any] = {}
        for col, (_old, new) in changes.items():
            if col in ("buy", "sell", "fee"):
                kwargs[col] = float(new) if new else 0.0
            else:
                kwargs[col] = new

        # Save via LedgerWriter
        from tui.app import CryptoApp
        app = self.app
        assert isinstance(app, CryptoApp)

        try:
            tx_id = self.transaction.get("ID")
            app.crypto.ledger_writer.update_transaction(tx_id, **kwargs)  # type: ignore[union-attr]
            self.dismiss(True)
        except Exception as e:
            error_label.update(f"Error: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edit-save-btn":
            self._validate_and_save()
        elif event.button.id == "edit-cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(False)


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
        height: 11;
        padding: 1 2;
        background: #16213e;
        border: solid #444444;
    }

    LedgerScreen .filter-group {
        layout: vertical;
        width: 1fr;
        height: auto;
        padding: 0 1;
        align-vertical: top;
    }

    LedgerScreen .filter-label {
        color: #888888;
        text-style: bold;
        height: 1;
    }

    LedgerScreen Input {
        height: 3;
        margin: 0;
        padding: 1 2;
    }

    LedgerScreen Select {
        height: 5;
        margin: 0;
    }

    LedgerScreen Select > SelectCurrent {
        color: #e0e0e0;
        background: #0f3460;
    }

    LedgerScreen Select:focus > SelectCurrent {
        background: #16213e;
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

    LedgerScreen .summary-bar {
        layout: horizontal;
        height: 4;
        padding: 1 2;
        background: #0f3460;
        border-top: solid #1a4a8a;
    }

    LedgerScreen #summary-label {
        color: #e0e0e0;
        text-align: center;
        width: 1fr;
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
                        value=None,
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

        # Summary statistics panel (hidden by default, shown when coin filter is active)
        with Container(id="summary-panel", classes="summary-bar"):
            yield Label("", id="summary-label")

        # Transaction table
        yield DataTable(id="transactions-table", cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        """Load initial data and populate wallet selector."""
        self.sub_title = "Transaction Ledger"
        summary_panel = self.query_one("#summary-panel")
        summary_panel.display = self.current_coin is not None
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

            # Reverse to show most recent first (more natural)
            self.filtered_transactions = list(reversed(transactions))

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

        self._update_summary()

    def _update_summary(self) -> None:
        """Update the summary statistics panel based on filtered transactions."""
        summary_panel = self.query_one("#summary-panel")

        if self.current_coin is None:
            summary_panel.display = False
            return

        summary_panel.display = True
        coin = self.current_coin

        total_credits = Decimal("0")
        total_debits = Decimal("0")
        total_fees = Decimal("0")

        for tx in self.filtered_transactions:
            if tx.get("Buy Cur.") == coin:
                try:
                    total_credits += Decimal(str(tx.get("Buy") or 0))
                except Exception:
                    pass
            if tx.get("Sell Cur.") == coin:
                try:
                    total_debits += Decimal(str(tx.get("Sell") or 0))
                except Exception:
                    pass
            if tx.get("Fee Cur.") == coin:
                try:
                    total_fees += Decimal(str(tx.get("Fee") or 0))
                except Exception:
                    pass

        net_balance = total_credits - total_debits

        # Format: 8 decimal places for BTC, 2 for USD
        decimals = 2 if coin == "USD" else 8
        fmt = f",.{decimals}f"

        balance_color = "green" if net_balance >= 0 else "red"
        count = len(self.filtered_transactions)

        self.query_one("#summary-label", Label).update(
            f"Credits: [green]{total_credits:{fmt}}[/green]  |  "
            f"Debits: [red]{total_debits:{fmt}}[/red]  |  "
            f"Fees: [yellow]{total_fees:{fmt}}[/yellow]  |  "
            f"Balance: [{balance_color}]{net_balance:{fmt}}[/{balance_color}]  |  "
            f"Count: [cyan]{count}[/cyan]"
        )

    def _show_empty_state(self) -> None:
        """Show empty state when no transactions exist."""
        status = self.query_one("#status-label", Label)
        status.update("[yellow]No transactions found. Import data to get started.[/yellow]")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a row to show transaction detail modal."""
        table = self.query_one("#transactions-table", DataTable)
        if table.cursor_row is None or not self.filtered_transactions:
            return

        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self.filtered_transactions):
            return

        tx = self.filtered_transactions[row_idx]

        def handle_detail_result(action: str | None) -> None:
            if action == "edit":
                self._open_edit_modal(tx)
            elif action == "delete":
                # TXE-005 will implement delete flow
                self.notify("Delete not yet implemented", severity="warning")

        self.app.push_screen(TransactionDetailModal(tx), handle_detail_result)

    def _open_edit_modal(self, tx: dict[str, Any]) -> None:
        """Open the edit transaction modal with wallet options."""
        # Build wallet options from the wallet selector
        wallet_opts: list[tuple[str, str]] = []
        try:
            select = self.query_one("#wallet-select", Select)
            for prompt, value in select._options:
                if value is not None:
                    wallet_opts.append((str(prompt), str(value)))
        except Exception:
            pass

        def handle_edit_result(saved: bool) -> None:
            if saved:
                self.notify("Transaction updated", severity="information")
                self.load_transactions()

        self.app.push_screen(
            EditTransactionModal(tx, wallet_opts),
            handle_edit_result,
        )

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
        self.current_coin = str(coin_select.value) if coin_select.value is not None else None
        # wallet_select.value is None for "All Wallets", or a wallet name string
        self.current_wallet = str(wallet_select.value) if wallet_select.value is not None else None
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

"""Dashboard screen showing portfolio summary, custody breakdown, and recent activity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from tui.screens.record_transaction import RecordTransactionScreen
    from cryptoAccounts import CryptoAccounts


class StatCard(Static):
    """A single statistic card widget."""

    DEFAULT_CSS = """
    StatCard {
        width: 1fr;
        height: auto;
        min-height: 6;
        border: solid #444444;
        background: #16213e;
        padding: 0 1;
        layout: vertical;
    }
    StatCard .stat-label {
        color: #888888;
        text-style: bold;
        padding-top: 1;
    }
    StatCard .stat-value {
        color: #f7931a;
        text-style: bold;
        padding-bottom: 1;
    }
    """

    def __init__(self, label: str, value: str, stat_id: str) -> None:
        super().__init__(id=stat_id)
        self.stat_label = label
        self.stat_value = value

    def compose(self) -> ComposeResult:
        yield Label(self.stat_label, classes="stat-label")
        yield Label(self.stat_value, classes="stat-value")

    def update_value(self, value: str) -> None:
        """Update the displayed value."""
        self.stat_value = value
        value_label = self.query_one(".stat-value", Label)
        value_label.update(value)


class WalletsCard(StatCard):
    """Wallets stat card with Manage button."""

    DEFAULT_CSS = """
    WalletsCard {
        width: 1fr;
        height: auto;
        min-height: 6;
        border: solid #444444;
        background: #16213e;
        padding: 0 1;
        layout: vertical;
    }
    WalletsCard .stat-label {
        color: #888888;
        text-style: bold;
        padding-top: 1;
    }
    WalletsCard .stat-value {
        color: #f7931a;
        text-style: bold;
    }
    WalletsCard .manage-link {
        color: #888888;
        text-style: italic;
        padding-bottom: 1;
    }
    WalletsCard .manage-link:hover {
        color: #f7931a;
        text-style: bold italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(self.stat_label, classes="stat-label")
        yield Label(self.stat_value, classes="stat-value")
        yield Label("→ Manage", classes="manage-link", id="wallet-manage-link")

    def on_click(self) -> None:
        """Handle click on the card - open wallet management screen."""
        self.app.action_menu_wallet()


class CustodyBreakdown(Static):
    """Widget showing custody type breakdown as percentages."""

    DEFAULT_CSS = """
    CustodyBreakdown {
        width: 100%;
        height: auto;
        max-height: 12;
        border: solid #444444;
        background: #16213e;
        padding: 1;
        margin-top: 1;
    }
    CustodyBreakdown .section-title {
        color: #f7931a;
        text-style: bold;
    }
    CustodyBreakdown .custody-item {
        color: #aaaaaa;
    }
    """

    def __init__(self, custody_data: dict[str, float] | None = None) -> None:
        super().__init__(id="custody-breakdown")
        self._pending_data = custody_data

    def compose(self) -> ComposeResult:
        yield Label("Custody Breakdown", classes="section-title")
        yield Container(id="custody-content")

    def on_mount(self) -> None:
        """Populate with initial data once children are mounted."""
        if self._pending_data is not None:
            self.update_custody(self._pending_data)
            self._pending_data = None

    def update_custody(self, custody_data: dict[str, float]) -> None:
        """Update custody breakdown display."""
        container = self.query_one("#custody-content", Container)
        container.remove_children()

        total = sum(custody_data.values())
        if total == 0:
            container.mount(Label("[dim]No custody data available[/dim]"))
            return

        # Sort custody types: self-custodied, multisig, custodial, unknown
        order = ["self-custodied", "multisig", "custodial", "unknown"]
        sorted_items = sorted(
            custody_data.items(),
            key=lambda x: order.index(x[0]) if x[0] in order else 999
        )

        for custody_type, balance in sorted_items:
            if balance > 0:
                pct = (balance / total) * 100
                label_text = f"{custody_type.title()}: {balance:.8f} BTC ({pct:.1f}%)"
                container.mount(Label(label_text, classes="custody-item"))


class RecentTransactions(Static):
    """Widget showing recent transaction history."""

    DEFAULT_CSS = """
    RecentTransactions {
        width: 100%;
        height: auto;
        max-height: 15;
        border: solid #444444;
        background: #16213e;
        padding: 1;
        margin-top: 1;
    }
    RecentTransactions .section-title {
        color: #f7931a;
        text-style: bold;
    }
    RecentTransactions DataTable {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(
        self,
        headers: list[str] | None = None,
        transactions: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(id="recent-transactions")
        self._pending_headers = headers
        self._pending_transactions = transactions

    def compose(self) -> ComposeResult:
        yield Label("Recent Transactions (Last 5)", classes="section-title")
        yield DataTable(id="tx-table")

    def on_mount(self) -> None:
        """Populate with initial data once children are mounted."""
        if self._pending_headers is not None and self._pending_transactions is not None:
            self.update_transactions(self._pending_headers, self._pending_transactions)
            self._pending_headers = None
            self._pending_transactions = None

    def update_transactions(self, headers: list[str], transactions: list[dict[str, Any]]) -> None:
        """Update transaction table with recent data."""
        table = self.query_one("#tx-table", DataTable)
        table.clear(columns=True)

        if not transactions:
            return

        # Add columns
        for header in headers:
            table.add_column(header, key=header)

        # Add rows (limit to 5 most recent)
        # Note: get_transactions() returns list of dicts, not tuples
        for tx_dict in transactions[:5]:
            # Extract values in the same order as headers
            row_data = [str(tx_dict.get(col, "")) if tx_dict.get(col) is not None else ""
                       for col in headers]
            table.add_row(*row_data)


class DashboardScreen(Screen[None]):
    """Dashboard screen showing portfolio summary and recent activity."""

    CSS = """
    DashboardScreen {
        background: #1a1a2e;
    }
    #dashboard-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #stats-row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #quick-actions {
        width: 100%;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }
    #quick-actions Button {
        width: 1fr;
        margin: 0 1;
        min-width: 15;
    }
    #loading-message {
        color: #f7931a;
        text-align: center;
        margin-top: 10;
    }
    #error-message {
        color: red;
        text-align: center;
        margin-top: 10;
    }
    #empty-message {
        color: #888888;
        text-align: center;
        margin-top: 10;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: str = "empty"  # empty | loading | success | error
        self._data: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="dashboard-container")
        yield Footer()

    def on_mount(self) -> None:
        """Load dashboard data when screen mounts."""
        self.app.sub_title = "Dashboard"
        self._show_loading()
        self.load_dashboard_data()

    def on_screen_resume(self) -> None:
        """Reload dashboard data when screen is resumed (returning from another screen)."""
        # Note: Dashboard refresh is now handled by app.refresh_dashboard_in_stack()
        # which is called directly from record transaction screen after recording.
        # This method is kept for potential future use.
        pass

    def refresh_dashboard(self) -> None:
        """Explicitly refresh dashboard data (called by app callbacks)."""
        # Reload data in background WITHOUT showing loading screen
        # This preserves focus and keyboard navigation
        self.load_dashboard_data(refresh_only=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle quick action button clicks."""
        button_id = event.button.id
        if button_id == "btn-portfolio":
            self.app.action_menu_portfolio()  # type: ignore[attr-defined]
        elif button_id == "btn-ledger":
            self.app.action_menu_ledger()  # type: ignore[attr-defined]
        elif button_id == "btn-trades":
            self.app.action_menu_trades()  # type: ignore[attr-defined]
        elif button_id == "btn-record":
            self.app.action_menu_record()  # type: ignore[attr-defined]
        elif button_id == "btn-import":
            self.app.action_menu_import()  # type: ignore[attr-defined]
        elif button_id == "btn-export":
            self.app.action_menu_export()  # type: ignore[attr-defined]
        elif button_id == "btn-tax":
            self.app.action_menu_tax()  # type: ignore[attr-defined]
        elif button_id == "btn-viz":
            self.app.action_menu_viz()  # type: ignore[attr-defined]

    def _show_loading(self) -> None:
        """Display loading state."""
        self._state = "loading"
        container = self.query_one("#dashboard-container", Container)
        container.remove_children()
        container.mount(Label("Loading portfolio data...", id="loading-message"))

    def _show_empty(self) -> None:
        """Display empty state with onboarding message."""
        self._state = "empty"
        container = self.query_one("#dashboard-container", Container)
        container.remove_children()

        empty_msg = """[bold]Welcome to Crypto Accounting![/bold]

Your database is empty. To get started:

1. Import transactions from an exchange or wallet
   Press [bold]I[/bold] to open the Import wizard

2. Or record a transaction manually
   Press [bold]R[/bold] to record a deposit, trade, or transfer

Once you have data, this dashboard will show:
• Your Bitcoin balance and cost basis
• Custody breakdown (self-custodied vs exchange-held)
• Recent transaction history

Press [bold]?[/bold] for help anytime."""

        container.mount(Label(empty_msg, id="empty-message"))

    def _show_error(self, error: str) -> None:
        """Display error state."""
        self._state = "error"
        container = self.query_one("#dashboard-container", Container)
        container.remove_children()
        container.mount(Label(f"[red]Error loading data:[/red]\n{error}", id="error-message"))

    def _update_widgets(self) -> None:
        """Update existing widgets with new data (for refresh without rebuild)."""
        balance = self._data.get("balance", 0.0)
        basis = self._data.get("basis", 0.0)
        active_wallets = self._data.get("active_wallets", 0)
        total_wallets = self._data.get("total_wallets", 0)

        # Update stat cards
        try:
            balance_card = self.query_one("#balance-card", StatCard)
            balance_card.update_value(f"{balance:.8f} BTC")
        except Exception:
            pass  # Widget doesn't exist yet

        try:
            basis_card = self.query_one("#basis-card", StatCard)
            basis_card.update_value(f"${basis:,.2f}" if basis > 0 else "N/A")
        except Exception:
            pass

        try:
            wallets_card = self.query_one("#wallets-card", StatCard)
            wallets_card.update_value(f"{active_wallets} active / {total_wallets} total")
        except Exception:
            pass

        # Update custody breakdown
        try:
            custody_widget = self.query_one("#custody-breakdown", CustodyBreakdown)
            custody_widget.update_custody(self._data.get("custody", {}))
        except Exception:
            pass

        # Update recent transactions
        try:
            tx_widget = self.query_one("#recent-transactions", RecentTransactions)
            headers = self._data.get("tx_headers", [])
            transactions = self._data.get("transactions", [])
            tx_widget.update_transactions(headers, transactions)
        except Exception:
            pass

    def _show_success(self) -> None:
        """Display loaded data."""
        self._state = "success"
        container = self.query_one("#dashboard-container", Container)
        container.remove_children()

        # Stats row
        balance = self._data.get("balance", 0.0)
        basis = self._data.get("basis", 0.0)
        active_wallets = self._data.get("active_wallets", 0)
        total_wallets = self._data.get("total_wallets", 0)

        # Mount stats row first, then add widgets to it
        stats_row = Horizontal(id="stats-row")
        container.mount(stats_row)

        # Now mount stat cards to the row
        stats_row.mount(
            StatCard(
                "Total Balance",
                f"{balance:.8f} BTC",
                "balance-card"
            )
        )
        stats_row.mount(
            StatCard(
                "Cost Basis per BTC",
                f"${basis:,.2f}" if basis > 0 else "N/A",
                "basis-card"
            )
        )
        stats_row.mount(
            WalletsCard(
                "Wallets",
                f"{active_wallets} active / {total_wallets} total",
                "wallets-card"
            )
        )

        # Quick action buttons
        actions_row = Horizontal(id="quick-actions")
        container.mount(actions_row)
        actions_row.mount(Button("Portfolio [P]", id="btn-portfolio"))
        actions_row.mount(Button("Ledger [L]", id="btn-ledger"))
        actions_row.mount(Button("Trades [X]", id="btn-trades"))
        actions_row.mount(Button("Record Tx [R]", id="btn-record"))
        actions_row.mount(Button("Import [I]", id="btn-import"))
        actions_row.mount(Button("Export [E]", id="btn-export"))
        actions_row.mount(Button("Tax/Report [T]", id="btn-tax"))
        actions_row.mount(Button("Visualize [V]", id="btn-viz"))

        # Custody breakdown - pass data to constructor, on_mount populates
        custody_widget = CustodyBreakdown(custody_data=self._data.get("custody", {}))
        container.mount(custody_widget)

        # Recent transactions - pass data to constructor, on_mount populates
        headers = self._data.get("tx_headers", [])
        transactions = self._data.get("transactions", [])
        tx_widget = RecentTransactions(headers=headers, transactions=transactions)
        container.mount(tx_widget)

    @work(thread=True)
    def load_dashboard_data(self, refresh_only: bool = False) -> None:
        """Load all dashboard data in background thread.

        Args:
            refresh_only: If True, update existing widgets instead of rebuilding UI
        """
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto: CryptoAccounts = app.crypto  # type: ignore[assignment]

        if crypto is None:
            self.app.call_from_thread(self._show_error, "Database connection not available")
            return

        try:
            # Fetch all data (CryptoAccounts methods are untyped legacy code)
            balance = crypto.get_balance('BTC')  # type: ignore[no-untyped-call]
            basis = crypto.get_basis('BTC')  # type: ignore[no-untyped-call]

            # Get wallet counts
            all_wallets = crypto.get_wallets(active_only=False)  # type: ignore[no-untyped-call]
            active_wallets = crypto.get_wallets(active_only=True)  # type: ignore[no-untyped-call]
            total_wallets = len(all_wallets)
            active_wallet_count = len(active_wallets)

            # Calculate custody breakdown
            wallet_balances = crypto.get_wallet_balance('BTC', None)  # type: ignore[no-untyped-call]
            custody_totals: dict[str, float] = {
                "self-custodied": 0.0,
                "custodial": 0.0,
                "multisig": 0.0,
                "unknown": 0.0,
            }

            # Sum balances by custody type
            for wallet_data in all_wallets:
                wallet_id = wallet_data.get('wallet_id', '')
                wallet_balance = wallet_balances.get(wallet_id, 0.0)
                custody_type = wallet_data.get('custody', 'unknown').lower()

                # Normalize custody type
                if custody_type in ["self-custodied", "self", "cold", "hardware", "hot"]:
                    custody_totals["self-custodied"] += wallet_balance
                elif custody_type in ["custodial", "exchange", "third-party"]:
                    custody_totals["custodial"] += wallet_balance
                elif custody_type in ["multisig", "multi-sig", "collaborative"]:
                    custody_totals["multisig"] += wallet_balance
                else:
                    custody_totals["unknown"] += wallet_balance

            # Get recent transactions (ordered oldest-first by default)
            headers, transactions = crypto.get_transactions(coin='BTC')  # type: ignore[no-untyped-call]

            # Check if database is empty
            if balance == 0 and len(transactions) == 0:
                self.app.call_from_thread(self._show_empty)
                return

            # Reverse to get most recent first (for dashboard display)
            recent_transactions = list(reversed(transactions))

            # Store data and update UI
            self._data = {
                "balance": balance,
                "basis": basis,
                "active_wallets": active_wallet_count,
                "total_wallets": total_wallets,
                "custody": custody_totals,
                "tx_headers": headers,
                "transactions": recent_transactions,
            }

            # Update UI: either rebuild from scratch or update existing widgets
            if refresh_only and self._state == "success":
                self.app.call_from_thread(self._update_widgets)
            else:
                self.app.call_from_thread(self._show_success)

        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))

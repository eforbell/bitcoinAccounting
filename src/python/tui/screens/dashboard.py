"""Dashboard screen showing portfolio summary, custody breakdown, and recent activity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from cryptoAccounts import CryptoAccounts


class StatCard(Static):
    """A single statistic card widget."""

    DEFAULT_CSS = """
    StatCard {
        width: 1fr;
        height: 5;
        border: solid #444444;
        background: #16213e;
        padding: 1;
    }
    StatCard .stat-label {
        color: #888888;
        text-style: bold;
    }
    StatCard .stat-value {
        color: #f7931a;
        text-style: bold;
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


class CustodyBreakdown(Static):
    """Widget showing custody type breakdown as percentages."""

    DEFAULT_CSS = """
    CustodyBreakdown {
        width: 100%;
        height: auto;
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
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="custody-breakdown")

    def compose(self) -> ComposeResult:
        yield Label("Custody Breakdown", classes="section-title")
        yield Container(id="custody-content")

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
        border: solid #444444;
        background: #16213e;
        padding: 1;
        margin-top: 1;
    }
    RecentTransactions .section-title {
        color: #f7931a;
        text-style: bold;
        margin-bottom: 1;
    }
    RecentTransactions DataTable {
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="recent-transactions")

    def compose(self) -> ComposeResult:
        yield Label("Recent Transactions (Last 5)", classes="section-title")
        yield DataTable(id="tx-table")

    def update_transactions(self, headers: list[str], transactions: list[tuple[Any, ...]]) -> None:
        """Update transaction table with recent data."""
        table = self.query_one("#tx-table", DataTable)
        table.clear(columns=True)

        if not transactions:
            return

        # Add columns
        for header in headers:
            table.add_column(header, key=header)

        # Add rows (limit to 5 most recent)
        for tx in transactions[:5]:
            # Convert tuple to list of strings for display
            row_data = [str(val) if val is not None else "" for val in tx]
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

        stats_row = Horizontal(id="stats-row")
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
            StatCard(
                "Wallets",
                f"{active_wallets} active / {total_wallets} total",
                "wallets-card"
            )
        )
        container.mount(stats_row)

        # Custody breakdown
        custody_widget = CustodyBreakdown()
        custody_widget.update_custody(self._data.get("custody", {}))
        container.mount(custody_widget)

        # Recent transactions
        tx_widget = RecentTransactions()
        headers = self._data.get("tx_headers", [])
        transactions = self._data.get("transactions", [])
        tx_widget.update_transactions(headers, transactions)
        container.mount(tx_widget)

    @work(thread=True)
    def load_dashboard_data(self) -> None:
        """Load all dashboard data in background thread."""
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

            # Get recent transactions
            headers, transactions = crypto.get_transactions(coin='BTC')  # type: ignore[no-untyped-call]

            # Check if database is empty
            if balance == 0 and len(transactions) == 0:
                self.app.call_from_thread(self._show_empty)
                return

            # Store data and update UI
            self._data = {
                "balance": balance,
                "basis": basis,
                "active_wallets": active_wallet_count,
                "total_wallets": total_wallets,
                "custody": custody_totals,
                "tx_headers": headers,
                "transactions": transactions,
            }

            self.app.call_from_thread(self._show_success)

        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))

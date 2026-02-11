"""Portfolio screen showing wallet balances, custody breakdown, and transaction history."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Select,
    Static,
    Switch,
)

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from cryptoAccounts import CryptoAccounts


class CustodyBar(Static):
    """Text-based custody breakdown bar widget."""

    DEFAULT_CSS = """
    CustodyBar {
        width: 100%;
        height: auto;
        padding: 1;
        margin-bottom: 1;
    }
    CustodyBar .custody-bar-title {
        color: #f7931a;
        text-style: bold;
        margin-bottom: 1;
    }
    CustodyBar .custody-bar-visual {
        color: #aaaaaa;
    }
    """

    def __init__(self, custody_data: dict[str, float] | None = None, total: float = 0.0) -> None:
        super().__init__(id="custody-bar")
        self._custody_data = custody_data or {}
        self._total = total

    def compose(self) -> ComposeResult:
        yield Label("Custody Breakdown", classes="custody-bar-title")
        yield Label("", id="custody-bar-visual", classes="custody-bar-visual")

    def on_mount(self) -> None:
        """Update custody data after mounting."""
        if self._custody_data or self._total > 0:
            self.update_custody(self._custody_data, self._total)

    def update_custody(self, custody_data: dict[str, float], total: float) -> None:
        """Update custody breakdown display."""
        bar_label = self.query_one("#custody-bar-visual", Label)

        if total == 0:
            bar_label.update("[dim]No balance data available[/dim]")
            return

        # Calculate percentages
        self_pct = (custody_data.get("self-custodied", 0.0) / total) * 100
        custodial_pct = (custody_data.get("custodial", 0.0) / total) * 100
        multisig_pct = (custody_data.get("multisig", 0.0) / total) * 100
        unknown_pct = (custody_data.get("unknown", 0.0) / total) * 100

        # Build text summary with color-coding
        parts = [
            f"[green]Self-custodied: {self_pct:.1f}%[/green]",
            f"[yellow]Custodial: {custodial_pct:.1f}%[/yellow]",
            f"[cyan]Multisig: {multisig_pct:.1f}%[/cyan]"
        ]
        if unknown_pct > 0:
            parts.append(f"[dim]Unknown: {unknown_pct:.1f}%[/dim]")

        bar_label.update("  |  ".join(parts))


class PortfolioScreen(Screen[None]):
    """Portfolio screen with wallet balances and transaction history."""

    CSS = """
    PortfolioScreen {
        background: #1a1a2e;
    }
    #portfolio-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #controls-bar {
        width: 100%;
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: #16213e;
        border: solid #444444;
    }
    #controls-bar Label {
        color: #aaaaaa;
        margin-right: 2;
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
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 1;
    }
    DataTable {
        height: 1fr;
    }
    #summary-row {
        width: 100%;
        height: auto;
        margin-top: 1;
        padding: 1;
        background: #16213e;
        border: solid #444444;
    }
    #summary-row Label {
        color: #f7931a;
        text-style: bold;
    }
    #wallet-detail-controls {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: str = "empty"  # empty | loading | success | error
        self._coin: str = "BTC"
        self._show_inactive: bool = False
        self._selected_wallet: str | None = None
        self._data: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="portfolio-container")
        yield Footer()

    def on_mount(self) -> None:
        """Load portfolio data when screen mounts."""
        self.app.sub_title = "Portfolio"
        self._show_loading()
        self.load_portfolio_data()

    def _show_loading(self) -> None:
        """Display loading state."""
        self._state = "loading"
        container = self.query_one("#portfolio-container", Container)
        container.remove_children()
        container.mount(Label("Loading portfolio data...", id="loading-message"))

    def _show_empty(self) -> None:
        """Display empty state."""
        self._state = "empty"
        container = self.query_one("#portfolio-container", Container)
        container.remove_children()

        empty_msg = """[bold]No Portfolio Data[/bold]

Your database has no transaction data yet.

Press [bold]I[/bold] to import transactions, or [bold]R[/bold] to record manually."""

        container.mount(Label(empty_msg, id="empty-message"))

    def _show_error(self, error: str) -> None:
        """Display error state."""
        self._state = "error"
        container = self.query_one("#portfolio-container", Container)
        container.remove_children()
        container.mount(Label(f"[red]Error loading data:[/red]\n{error}", id="error-message"))

    def _show_success(self) -> None:
        """Display loaded data."""
        self._state = "success"
        container = self.query_one("#portfolio-container", Container)
        container.remove_children()

        # Controls bar - mount first, then add children
        controls = Horizontal(id="controls-bar")
        container.mount(controls)
        controls.mount(Label("Show inactive wallets:"))
        controls.mount(Switch(value=self._show_inactive, id="show-inactive-switch"))

        # Show balances view (simplified - no tabs for now to avoid TabbedContent complexity)
        # TODO: Add back Wallet Detail tab using proper Textual compose patterns
        for widget in self._build_balances_tab():
            container.mount(widget)

    def _build_balances_tab(self) -> ComposeResult:
        """Build the Balances tab content."""
        # Custody bar - pass data to constructor, will update on mount
        total_balance = self._data.get("total_balance", 0.0)
        custody_data = self._data.get("custody", {})
        yield CustodyBar(custody_data, total_balance)

        # Wallet balances table
        table: DataTable = DataTable(id="balances-table")
        table.add_column("Wallet", key="wallet")
        table.add_column("Balance", key="balance")
        table.add_column("% of Total", key="percentage")
        table.add_column("Custody", key="custody")
        table.add_column("Status", key="status")

        wallet_balances = self._data.get("wallet_balances", [])
        for wallet_data in wallet_balances:
            wallet_id = wallet_data.get("wallet_id", "")
            balance = wallet_data.get("balance", 0.0)
            percentage = wallet_data.get("percentage", 0.0)
            custody = wallet_data.get("custody", "unknown")
            status = wallet_data.get("status", "active")

            table.add_row(
                wallet_id,
                f"{balance:.8f}",
                f"{percentage:.2f}%",
                custody,
                status
            )

        yield table

        # Summary row - yield as Static with formatted text
        wallet_count = len(wallet_balances)
        active_count = sum(1 for w in wallet_balances if w.get("status") == "active")
        summary_text = (
            f"Total Balance: {total_balance:.8f} {self._coin}  |  "
            f"Wallets: {active_count} active / {wallet_count} total"
        )
        yield Static(summary_text, id="summary-row")

    def _build_wallet_detail_tab(self) -> ComposeResult:
        """Build the Wallet Detail tab content."""
        # Wallet selector - yield label and select separately
        yield Label("Select wallet:")

        wallet_options = [
            (wallet["wallet_id"], wallet["wallet_id"])
            for wallet in self._data.get("wallet_balances", [])
        ]
        if not wallet_options:
            wallet_options = [("", "No wallets available")]

        yield Select(
            options=wallet_options,
            prompt="Choose a wallet",
            id="wallet-selector"
        )

        # Transaction table (initially empty)
        yield DataTable(id="wallet-transactions-table")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle show inactive toggle."""
        if event.switch.id == "show-inactive-switch":
            self._show_inactive = event.value
            self._show_loading()
            self.load_portfolio_data()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle wallet selection change."""
        if event.select.id == "wallet-selector":
            self._selected_wallet = str(event.value)
            self.load_wallet_transactions()

    @work(thread=True)
    def load_portfolio_data(self) -> None:
        """Load portfolio data in background thread."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto: CryptoAccounts = app.crypto

        if crypto is None:
            self.app.call_from_thread(self._show_error, "Database connection not available")
            return

        try:
            # Get wallet data
            all_wallets = crypto.get_wallets(active_only=False)

            # Filter by active status if needed
            if not self._show_inactive:
                wallets = [w for w in all_wallets if w.get("status", "active") == "active"]
            else:
                wallets = all_wallets

            # Get balance for each wallet
            wallet_balances_dict = crypto.get_wallet_balance(self._coin, None)

            # Calculate total balance
            total_balance = sum(wallet_balances_dict.values())

            # Calculate custody breakdown
            custody_totals: dict[str, float] = {
                "self-custodied": 0.0,
                "custodial": 0.0,
                "multisig": 0.0,
                "unknown": 0.0,
            }

            # Build wallet balance list with metadata
            wallet_balances: list[dict[str, Any]] = []
            for wallet_data in wallets:
                wallet_id = wallet_data.get('wallet_id', '')
                balance = wallet_balances_dict.get(wallet_id, 0.0)
                custody_type = wallet_data.get('custody', 'unknown').lower()
                status = wallet_data.get('status', 'active')

                # Only include wallets with non-zero balance or active status
                if balance > 0 or status == "active":
                    percentage = (balance / total_balance * 100) if total_balance > 0 else 0.0

                    wallet_balances.append({
                        "wallet_id": wallet_id,
                        "balance": balance,
                        "percentage": percentage,
                        "custody": custody_type,
                        "status": status,
                    })

                    # Accumulate custody totals
                    if custody_type in ["self-custodied", "self", "cold", "hardware", "hot"]:
                        custody_totals["self-custodied"] += balance
                    elif custody_type in ["custodial", "exchange", "third-party"]:
                        custody_totals["custodial"] += balance
                    elif custody_type in ["multisig", "multi-sig", "collaborative"]:
                        custody_totals["multisig"] += balance
                    else:
                        custody_totals["unknown"] += balance

            # Check if empty
            if total_balance == 0 and len(wallet_balances) == 0:
                self.app.call_from_thread(self._show_empty)
                return

            # Store data and update UI
            self._data = {
                "wallet_balances": wallet_balances,
                "total_balance": total_balance,
                "custody": custody_totals,
            }

            self.app.call_from_thread(self._show_success)

        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))

    @work(thread=True)
    def load_wallet_transactions(self) -> None:
        """Load transactions for selected wallet in background thread."""
        from tui.app import CryptoApp

        if not self._selected_wallet:
            return

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto: CryptoAccounts = app.crypto

        if crypto is None:
            return

        try:
            # Get transactions for selected wallet
            headers, transactions = crypto.get_transactions(
                coin=self._coin,
                wallet=self._selected_wallet
            )

            # Update table on main thread
            def update_table() -> None:
                table = self.query_one("#wallet-transactions-table", DataTable)
                table.clear(columns=True)

                if not transactions:
                    return

                # Add columns
                for header in headers:
                    table.add_column(header, key=header)

                # Add rows
                for tx in transactions:
                    row_data = [str(val) if val is not None else "" for val in tx]
                    table.add_row(*row_data)

            self.app.call_from_thread(update_table)

        except Exception as e:
            # Silently handle errors (table stays empty)
            pass

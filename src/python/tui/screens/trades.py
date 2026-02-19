"""Trades and exchange liquidity screen showing trade history and cost basis tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
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
)

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from bitcoinAccounts import BitcoinAccounts


class TradesScreen(Screen[None]):
    """Screen showing trade history and exchange liquidity information."""

    DEFAULT_CSS = """
    TradesScreen {
        background: $background;
    }

    TradesScreen Container {
        height: 100%;
        layout: vertical;
    }

    TradesScreen .screen-title {
        dock: top;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    TradesScreen .filter-panel {
        dock: top;
        height: auto;
        min-height: 5;
        max-height: 8;
        layout: vertical;
        background: $surface;
        padding: 1;
        margin-bottom: 1;
    }

    TradesScreen .filter-row {
        height: auto;
        layout: horizontal;
        align: left middle;
    }

    TradesScreen .filter-label {
        width: 12;
        padding-right: 1;
        color: $text-muted;
    }

    TradesScreen Select {
        width: 20;
        margin-right: 2;
    }

    TradesScreen .section-container {
        layout: vertical;
        height: 1fr;
    }

    TradesScreen .section-header {
        dock: top;
        height: 3;
        layout: horizontal;
        align: left middle;
        background: $surface;
        padding: 0 2;
    }

    TradesScreen .section-title {
        color: $accent;
        text-style: bold;
    }

    TradesScreen .section-status {
        color: $text-muted;
        margin-left: 2;
    }

    TradesScreen DataTable {
        height: 1fr;
    }

    TradesScreen .summary-panel {
        dock: bottom;
        height: auto;
        min-height: 8;
        max-height: 12;
        background: $surface;
        padding: 1;
        margin-top: 1;
        layout: vertical;
    }

    TradesScreen .summary-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    TradesScreen .summary-row {
        height: auto;
        layout: horizontal;
        padding: 0 1;
    }

    TradesScreen .summary-label {
        width: 35;
        color: $text-muted;
    }

    TradesScreen .summary-value {
        color: $text;
    }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("t", "switch_to_trades", "Trades", show=True),
        Binding("e", "switch_to_liquidity", "Liquidity", show=True),
        Binding("r", "reload", "Reload", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_view = "trades"  # "trades" or "liquidity"
        self._coin = "BTC"

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()
        with Container():
            yield Label("Trades & Exchange Liquidity", classes="screen-title")

            # Filter panel
            with Container(classes="filter-panel"):
                with Horizontal(classes="filter-row"):
                    yield Label("Coin:", classes="filter-label")
                    yield Select([("BTC", "BTC")], value="BTC", id="coin-select")
                    yield Button("View Trades [T]", id="view-trades-btn")
                    yield Button("View Liquidity [E]", id="view-liquidity-btn")

            # Content area
            yield Container(id="content-area")

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mount - load trades view by default."""
        self._show_trades_view()

    def action_switch_to_trades(self) -> None:
        """Switch to trades view."""
        self._show_trades_view()

    def action_switch_to_liquidity(self) -> None:
        """Switch to exchange liquidity view."""
        self._show_liquidity_view()

    def action_reload(self) -> None:
        """Reload the current view."""
        if self._current_view == "trades":
            self._show_trades_view()
        else:
            self._show_liquidity_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "view-trades-btn":
            self._show_trades_view()
        elif event.button.id == "view-liquidity-btn":
            self._show_liquidity_view()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle coin selection changes."""
        if event.select.id == "coin-select":
            self._coin = str(event.value)
            # Reload current view with new coin
            self.action_reload()

    def _show_trades_view(self) -> None:
        """Show the trades history view."""
        self._current_view = "trades"
        content_area = self.query_one("#content-area", Container)
        content_area.remove_children()

        # Create trades section
        section = Container(classes="section-container")
        content_area.mount(section)

        # Section header
        header = Container(classes="section-header")
        section.mount(header)
        header.mount(Label(f"Trade History - {self._coin}", classes="section-title"))
        header.mount(Label("Loading...", id="trades-status", classes="section-status"))

        # DataTable for trades
        table: DataTable[str] = DataTable(id="trades-table", zebra_stripes=True)
        section.mount(table)

        # Load data asynchronously
        self._load_trades_data()

    def _show_liquidity_view(self) -> None:
        """Show the exchange liquidity view."""
        self._current_view = "liquidity"
        content_area = self.query_one("#content-area", Container)
        content_area.remove_children()

        # Create liquidity section
        section = Container(classes="section-container")
        content_area.mount(section)

        # Section header
        header = Container(classes="section-header")
        section.mount(header)
        header.mount(Label(f"Exchange Liquidity - {self._coin}", classes="section-title"))
        header.mount(Label("Loading...", id="liquidity-status", classes="section-status"))

        # DataTable for liquidity
        table: DataTable[str] = DataTable(id="liquidity-table", zebra_stripes=True)
        section.mount(table)

        # Summary panel
        summary = Container(classes="summary-panel", id="liquidity-summary")
        section.mount(summary)

        # Load data asynchronously
        self._load_liquidity_data()

    @work(thread=True)
    def _load_trades_data(self) -> None:
        """Load trade history data in background thread."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(self._show_trades_error, "No database connection")
            return

        try:
            # Get trade data with cost basis
            trades = crypto.trade_query.get_trade_cost(self._coin, 'USD')

            # Sort by date descending (most recent first)
            trades_sorted = sorted(trades, key=lambda t: t['date'], reverse=True)

            self.app.call_from_thread(self._update_trades_table, trades_sorted)
        except Exception as e:
            self.app.call_from_thread(self._show_trades_error, str(e))

    @work(thread=True)
    def _load_liquidity_data(self) -> None:
        """Load exchange liquidity data in background thread."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(self._show_liquidity_error, "No database connection")
            return

        try:
            # Get all purchase data grouped by exchange
            all_trades = crypto.trade_query.get_trade_cost(self._coin, cost_currency='USD')

            # Group by exchange
            exchange_data: dict[str, dict[str, float]] = {}
            for t in all_trades:
                if t.get('quantity', 0) <= 0:  # Skip sales
                    continue

                exchange = t.get('exchange', 'Unknown')
                if exchange not in exchange_data:
                    exchange_data[exchange] = {'purchased': 0.0, 'usd_spent': 0.0}

                exchange_data[exchange]['purchased'] += t['quantity']
                if t.get('total_cost') is not None:
                    exchange_data[exchange]['usd_spent'] += t['total_cost']

            # Add current balances
            liquidity_rows = []
            total_purchased = 0.0
            total_balance = 0.0
            total_usd_spent = 0.0

            for exchange, data in exchange_data.items():
                purchased = data['purchased']
                usd_spent = data['usd_spent']

                if purchased > 0:
                    # Get current balance
                    balance = crypto.get_wallet_balance(self._coin, exchange)
                    avg_cost = usd_spent / purchased if purchased > 0 else 0

                    liquidity_rows.append({
                        'exchange': exchange,
                        'purchased': purchased,
                        'balance': balance,
                        'usd_spent': usd_spent,
                        'avg_cost': avg_cost
                    })

                    total_purchased += purchased
                    total_balance += balance
                    total_usd_spent += usd_spent

            # Sort by purchased amount descending
            liquidity_rows.sort(key=lambda x: x['purchased'], reverse=True)

            # Calculate summary metrics
            overall_balance = crypto.get_balance(self._coin)
            in_cold_storage = overall_balance - total_balance
            total_avg_cost = total_usd_spent / total_purchased if total_purchased > 0 else 0

            summary = {
                'total_purchased': total_purchased,
                'total_usd_spent': total_usd_spent,
                'total_avg_cost': total_avg_cost,
                'still_at_exchanges': total_balance,
                'in_cold_storage': in_cold_storage,
                'total_holdings': overall_balance
            }

            self.app.call_from_thread(self._update_liquidity_table, liquidity_rows, summary)
        except Exception as e:
            self.app.call_from_thread(self._show_liquidity_error, str(e))

    def _update_trades_table(self, trades: list[dict[str, Any]]) -> None:
        """Update trades table with data."""
        table = self.query_one("#trades-table", DataTable)
        status = self.query_one("#trades-status", Label)

        # Clear existing data
        table.clear(columns=True)

        if not trades:
            status.update("No trades found")
            return

        # Add columns
        table.add_column("Date", key="date")
        table.add_column("Type", key="type")
        table.add_column("Quantity", key="quantity")
        table.add_column("Trade Currency", key="trade_curr")
        table.add_column("Unit Cost (USD)", key="unit_cost")
        table.add_column("Total Cost (USD)", key="total_cost")
        table.add_column("Exchange", key="exchange")

        # Add rows
        for trade in trades:
            quantity = trade['quantity']
            trade_type = "Buy" if quantity > 0 else "Sell"
            quantity_str = f"{abs(quantity):.8f}"
            unit_cost_str = f"${trade['unit_cost']:.2f}" if trade['unit_cost'] is not None else "N/A"
            total_cost_str = f"${trade['total_cost']:.2f}" if trade['total_cost'] is not None else "N/A"

            table.add_row(
                str(trade['date'])[:10],  # Date only (YYYY-MM-DD)
                trade_type,
                quantity_str,
                trade['trade_curr'],
                unit_cost_str,
                total_cost_str,
                trade.get('exchange', 'Unknown')
            )

        status.update(f"Showing {len(trades)} trades")

    def _update_liquidity_table(
        self,
        liquidity_rows: list[dict[str, Any]],
        summary: dict[str, float]
    ) -> None:
        """Update liquidity table and summary with data."""
        table = self.query_one("#liquidity-table", DataTable)
        status = self.query_one("#liquidity-status", Label)
        summary_panel = self.query_one("#liquidity-summary", Container)

        # Clear existing data
        table.clear(columns=True)
        summary_panel.remove_children()

        if not liquidity_rows:
            status.update("No purchase history found")
            return

        # Add columns
        table.add_column("Exchange", key="exchange")
        table.add_column("Total Purchased", key="purchased")
        table.add_column("Current Balance", key="balance")
        table.add_column("Avg Cost (USD)", key="avg_cost")

        # Add rows
        for row in liquidity_rows:
            avg_cost_str = f"${row['avg_cost']:,.2f}" if row['avg_cost'] > 0 else "N/A"
            table.add_row(
                row['exchange'],
                f"{row['purchased']:.8f}",
                f"{row['balance']:.8f}",
                avg_cost_str
            )

        # Add totals row
        total_avg_str = f"${summary['total_avg_cost']:,.2f}" if summary['total_avg_cost'] > 0 else "N/A"
        table.add_row(
            "TOTALS",
            f"{summary['total_purchased']:.8f}",
            f"{summary['still_at_exchanges']:.8f}",
            total_avg_str
        )

        status.update(f"Showing {len(liquidity_rows)} exchanges with purchase history")

        # Build summary panel
        summary_panel.mount(Label("Cost Basis Summary", classes="summary-title"))

        # Summary rows
        summary_data = [
            ("Total purchased at exchanges:", f"{summary['total_purchased']:.8f} {self._coin}"),
            ("Total USD spent:", f"${summary['total_usd_spent']:,.2f}"),
            ("Average cost basis:", f"${summary['total_avg_cost']:,.2f} per {self._coin}"),
            ("Still at exchanges:", f"{summary['still_at_exchanges']:.8f} {self._coin}"),
            ("In cold storage:", f"{summary['in_cold_storage']:.8f} {self._coin}"),
            ("TOTAL HOLDINGS:", f"{summary['total_holdings']:.8f} {self._coin}")
        ]

        for lbl, val in summary_data:
            summary_row = Horizontal(classes="summary-row")
            summary_panel.mount(summary_row)
            summary_row.mount(Label(lbl, classes="summary-label"))
            summary_row.mount(Label(val, classes="summary-value"))

    def _show_trades_error(self, error_msg: str) -> None:
        """Show error message for trades view."""
        table = self.query_one("#trades-table", DataTable)
        status = self.query_one("#trades-status", Label)

        table.clear(columns=True)
        status.update(f"[red]Error: {error_msg}[/red]")

    def _show_liquidity_error(self, error_msg: str) -> None:
        """Show error message for liquidity view."""
        table = self.query_one("#liquidity-table", DataTable)
        status = self.query_one("#liquidity-status", Label)

        table.clear(columns=True)
        status.update(f"[red]Error: {error_msg}[/red]")

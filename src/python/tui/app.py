"""Main Textual application for Crypto Accounting."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, Static

from cryptoAccounts import CryptoAccounts
from tui.screens import DashboardScreen, ExportScreen, ImportWizardScreen, LedgerScreen, PortfolioScreen, RecordTransactionScreen, TaxReportingScreen, TradesScreen, VisualizationScreen


class HelpScreen(ModalScreen[None]):
    """Modal help overlay showing keyboard shortcuts and system info."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 70;
        max-height: 85%;
        border: double #f7931a;
        background: #1a1a2e;
        padding: 1 2;
    }
    #help-scroll {
        height: auto;
        max-height: 100%;
    }
    #help-dialog Label {
        width: 100%;
        margin: 0;
    }
    .help-header {
        text-style: bold;
        color: #f7931a;
        text-align: center;
    }
    .help-section {
        text-style: bold;
        color: #e0e0e0;
        margin-top: 1;
    }
    .help-line {
        color: #aaaaaa;
    }
    .help-desc {
        color: #777777;
        margin-left: 6;
    }
    .help-dim {
        color: #666666;
        text-align: center;
    }
    .help-about {
        color: #888888;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def __init__(self, about_info: str = "") -> None:
        super().__init__()
        self._about_info = about_info

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            with VerticalScroll(id="help-scroll"):
                yield Label("Crypto Accounting TUI", classes="help-header")
                yield Label("")

                yield Label("Navigation", classes="help-section")
                yield Label("  P   Portfolio & Balances", classes="help-line")
                yield Label("      Wallet balances, custody breakdown, wallet detail", classes="help-desc")
                yield Label("  L   Transaction Ledger", classes="help-line")
                yield Label("      Full transaction history with filtering by coin/wallet/date", classes="help-desc")
                yield Label("  X   Trade History & Liquidity", classes="help-line")
                yield Label("      Trade cost basis and exchange purchase summary", classes="help-desc")
                yield Label("  R   Record Transaction", classes="help-line")
                yield Label("      Buy, sell, transfer, or earn interest flows", classes="help-desc")
                yield Label("  I   Import CSV", classes="help-line")
                yield Label("      Import from exchanges and wallets with preview", classes="help-desc")
                yield Label("  E   Export Transactions", classes="help-line")
                yield Label("      Export filtered ledger to CSV", classes="help-desc")
                yield Label("  T   Tax & Reporting", classes="help-line")
                yield Label("      Capital gains tracker, 1099-B export, sale forecast", classes="help-desc")
                yield Label("  V   Visualizations", classes="help-line")
                yield Label("      Generate Orange Plot, Balance, Custody charts, PDF report", classes="help-desc")
                yield Label("")

                yield Label("Within Screens", classes="help-section")
                yield Label("  Esc       Back to previous screen", classes="help-line")
                yield Label("  Tab       Cycle through widgets", classes="help-line")
                yield Label("  Enter     Activate focused button/control", classes="help-line")
                yield Label("  Arrows    Navigate within tables and selectors", classes="help-line")
                yield Label("")

                yield Label("General", classes="help-section")
                yield Label("  ? / F1    Show this help", classes="help-line")
                yield Label("  Q         Quit application", classes="help-line")
                yield Label("")

                if self._about_info:
                    yield Label("About", classes="help-section")
                    yield Label(self._about_info, classes="help-about")
                    yield Label("")

                yield Label("Press Esc to close", classes="help-dim")


class MenuButton(Static):
    """A clickable menu button widget."""

    DEFAULT_CSS = """
    MenuButton {
        width: 1fr;
        height: 7;
        content-align: center middle;
        text-align: center;
        border: solid #444444;
        margin: 0 1;
    }
    MenuButton:hover {
        border: solid #f7931a;
        background: #16213e;
    }
    MenuButton.--active {
        border: solid #f7931a;
        background: #0f3460;
    }
    """

    def __init__(self, label: str, description: str, key: str, action: str) -> None:
        super().__init__(f"[bold]{label}[/bold]\n[dim]{description}[/dim]\n[dim]\\[{key}][/dim]")
        self._action = action

    def on_click(self) -> None:
        self.app.action_from_menu(self._action)  # type: ignore[attr-defined]


class MainMenu(Widget):
    """Main menu screen content with navigation buttons."""

    DEFAULT_CSS = """
    MainMenu {
        height: 1fr;
        align: center middle;
        layout: vertical;
    }
    #menu-title {
        text-align: center;
        text-style: bold;
        color: #f7931a;
        width: 100%;
        margin-bottom: 1;
    }
    #menu-subtitle {
        text-align: center;
        color: #888888;
        width: 100%;
        margin-bottom: 2;
    }
    Center {
        height: auto;
    }
    #menu-grid-top, #menu-grid-bottom {
        height: auto;
        width: auto;
    }
    #menu-hint {
        text-align: center;
        color: #555555;
        width: 100%;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Crypto Accounting", id="menu-title")
        yield Label("Bitcoin Portfolio Management & Tax Reporting", id="menu-subtitle")
        with Center():
            with Horizontal(id="menu-grid-top"):
                yield MenuButton("Portfolio", "Balances & custody", "P", "portfolio")
                yield MenuButton("Ledger", "Transaction history", "L", "ledger")
                yield MenuButton("Record Tx", "Buy/sell/transfer", "R", "record")
        with Center():
            with Horizontal(id="menu-grid-bottom"):
                yield MenuButton("Import", "Load CSV files", "I", "import")
                yield MenuButton("Tax / Report", "Gains & 1099-B", "T", "tax")
                yield MenuButton("Visualize", "Generate charts", "V", "viz")
        yield Label("Press a key or click a menu item  |  ? for help  |  Q to quit", id="menu-hint")


class CryptoApp(App[None]):
    """Crypto Accounting TUI application."""

    TITLE = "Crypto Accounting"
    SUB_TITLE = "Bitcoin Portfolio Management"

    # Load centralized theme from .tcss file (TUI-003)
    # Path is relative to this file's directory
    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "menu_portfolio", "Portfolio", show=False),
        Binding("l", "menu_ledger", "Ledger", show=False),
        Binding("x", "menu_trades", "Trades", show=False),
        Binding("r", "menu_record", "Record Tx", show=False),
        Binding("i", "menu_import", "Import", show=False),
        Binding("e", "menu_export", "Export", show=False),
        Binding("t", "menu_tax", "Tax/Report", show=False),
        Binding("v", "menu_viz", "Visualize", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("f1", "show_help", "Help", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.crypto: CryptoAccounts | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield MainMenu()
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.crypto = CryptoAccounts()
            # Push dashboard as default screen (TUI-002)
            self.push_screen(DashboardScreen())
        except Exception as e:
            self.notify(
                f"Database connection failed: {e}\n"
                "Check your .env file or database configuration and restart.",
                severity="error",
                timeout=10,
            )

    def on_unmount(self) -> None:
        if self.crypto is not None:
            self.crypto.close()  # type: ignore[no-untyped-call]

    def _get_about_info(self) -> str:
        """Build about section text with version, database path, and backend type."""
        lines = []
        if self.crypto is not None:
            backend = self.crypto.backend
            backend_type = type(backend).__name__
            lines.append(f"  Backend:  {backend_type}")
            if hasattr(backend, 'db_path'):
                lines.append(f"  Database: {backend.db_path}")
        else:
            lines.append("  Backend:  Not connected")
        return "\n".join(lines)

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen(about_info=self._get_about_info()))

    def action_from_menu(self, action: str) -> None:
        """Route menu button clicks to the correct action."""
        method = getattr(self, f"action_menu_{action}", None)
        if method:
            method()

    # -- Menu actions (stubs for TUI-001, implemented in later stories) --

    def action_menu_portfolio(self) -> None:
        # TUI-004: Full portfolio screen with balances and wallet detail
        self.push_screen(PortfolioScreen())

    def action_menu_ledger(self) -> None:
        # TUI-005: Transaction ledger screen with filtering
        self.push_screen(LedgerScreen())

    def action_menu_trades(self) -> None:
        # TUI-006: Trade history and exchange liquidity screens
        self.push_screen(TradesScreen())

    def refresh_dashboard_in_stack(self) -> None:
        """Find dashboard in screen stack and refresh it."""
        # Search the screen stack for any DashboardScreen instances
        for screen in self.screen_stack:
            if isinstance(screen, DashboardScreen):
                screen.refresh_dashboard()
                break

    def action_menu_record(self) -> None:
        # TUI-007: Record transaction screen
        self.push_screen(RecordTransactionScreen())

    def action_menu_import(self) -> None:
        # TUI-008: Import wizard screen with file picker and preview
        self.push_screen(ImportWizardScreen())

    def action_menu_export(self) -> None:
        # TUI-009: Export transactions screen
        self.push_screen(ExportScreen())

    def action_menu_tax(self) -> None:
        # TUI-010: Tax reporting screen
        self.push_screen(TaxReportingScreen())

    def action_menu_viz(self) -> None:
        # TUI-011: Visualization screen with chart generation
        self.push_screen(VisualizationScreen())

    def on_worker_state_changed(self, event: object) -> None:
        """Handle worker errors globally to show user-friendly notifications."""
        # Textual Worker.StateChanged carries the worker reference
        worker = getattr(event, 'worker', None)
        if worker is None:
            return
        state = getattr(worker, 'state', None)
        error = getattr(worker, 'error', None)
        if state is not None and str(state) == "ERROR" and error is not None:
            error_msg = str(error)
            if "connection" in error_msg.lower() or "database" in error_msg.lower():
                self.notify(
                    f"Database error: {error_msg}\n"
                    "Check connection settings and try again.",
                    severity="error",
                    timeout=8,
                )
            else:
                self.notify(
                    f"An error occurred: {error_msg}",
                    severity="error",
                    timeout=6,
                )


def main() -> None:
    """Entry point for the TUI application."""
    app = CryptoApp()
    app.run()

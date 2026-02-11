"""Main Textual application for Crypto Accounting."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, Static

from cryptoAccounts import CryptoAccounts
from tui.screens import DashboardScreen, PortfolioScreen


class HelpScreen(ModalScreen[None]):
    """Modal help overlay showing keyboard shortcuts and system info."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 64;
        max-height: 80%;
        border: double #f7931a;
        background: #1a1a2e;
        padding: 1 2;
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
    .help-dim {
        color: #666666;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Label("Crypto Accounting TUI", classes="help-header")
            yield Label("")
            yield Label("Navigation", classes="help-section")
            yield Label("  P   Portfolio & Balances", classes="help-line")
            yield Label("  L   Transaction Ledger", classes="help-line")
            yield Label("  R   Record Transaction", classes="help-line")
            yield Label("  I   Import CSV", classes="help-line")
            yield Label("  T   Tax & Reporting", classes="help-line")
            yield Label("  V   Visualizations", classes="help-line")
            yield Label("")
            yield Label("General", classes="help-section")
            yield Label("  ?       Show this help", classes="help-line")
            yield Label("  Esc     Back / Close", classes="help-line")
            yield Label("  Tab     Next widget", classes="help-line")
            yield Label("  Q       Quit", classes="help-line")
            yield Label("")
            yield Label("Press Esc to close", classes="help-dim")


class MenuButton(Static):
    """A clickable menu button widget."""

    DEFAULT_CSS = """
    MenuButton {
        width: 1fr;
        height: 5;
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

    def __init__(self, label: str, key: str, action: str) -> None:
        super().__init__(f"{label}\n[dim]\\[{key}][/dim]")
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
                yield MenuButton("Portfolio", "P", "portfolio")
                yield MenuButton("Ledger", "L", "ledger")
                yield MenuButton("Record Tx", "R", "record")
        with Center():
            with Horizontal(id="menu-grid-bottom"):
                yield MenuButton("Import", "I", "import")
                yield MenuButton("Tax / Report", "T", "tax")
                yield MenuButton("Visualize", "V", "viz")
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
        Binding("r", "menu_record", "Record Tx", show=False),
        Binding("i", "menu_import", "Import", show=False),
        Binding("t", "menu_tax", "Tax/Report", show=False),
        Binding("v", "menu_viz", "Visualize", show=False),
        Binding("question_mark", "show_help", "Help"),
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
            self.notify(f"Database connection failed: {e}", severity="error")

    def on_unmount(self) -> None:
        if self.crypto is not None:
            self.crypto.close()  # type: ignore[no-untyped-call]

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

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
        self.notify("Ledger screen coming in TUI-005", severity="information")

    def action_menu_record(self) -> None:
        self.notify("Record transaction screen coming in TUI-007", severity="information")

    def action_menu_import(self) -> None:
        self.notify("Import wizard coming in TUI-008", severity="information")

    def action_menu_tax(self) -> None:
        self.notify("Tax reporting screen coming in TUI-010", severity="information")

    def action_menu_viz(self) -> None:
        self.notify("Visualization screen coming in TUI-011", severity="information")


def main() -> None:
    """Entry point for the TUI application."""
    app = CryptoApp()
    app.run()

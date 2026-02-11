# Feature-9: Textual Patterns Reference (from Viper TUI)

Reference patterns extracted from `~/workspace/viper` - a production Textual TUI application.
Use these patterns when implementing Feature-9 stories.

---

## 1. App Setup Pattern

```python
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

class CryptoApp(App[None]):
    """Main application."""

    TITLE = "Crypto Accounting"

    # Embedded CSS (preferred over .tcss files per Viper pattern)
    CSS = """
    Screen {
        background: $background;
    }
    #main-container {
        layout: horizontal;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "show_portfolio", "Portfolio"),
        ("r", "show_record", "Record Tx"),
        ("i", "show_import", "Import"),
        ("t", "show_tax", "Tax/Report"),
        ("v", "show_viz", "Visualize"),
        ("question_mark", "show_help", "Help"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        # ... main content
        yield Footer()

    def on_mount(self) -> None:
        self.crypto = CryptoAccounts()

    def on_unmount(self) -> None:
        self.crypto.close()
```

**Entry point:**
```python
# src/scripts/crypto_tui
#!/usr/bin/env python3
import _bootstrap
from tui.app import CryptoApp

def main():
    app = CryptoApp()
    app.run()

if __name__ == "__main__":
    main()
```

---

## 2. Panel Toggle Pattern (Viper's Approach)

Viper uses **one screen with toggled panels**, NOT multi-screen navigation:

```python
class CryptoApp(App[None]):
    def __init__(self):
        super().__init__()
        self._portfolio_visible = True
        self._record_visible = False
        self._import_visible = False

    def _show_panel(self, panel_name: str) -> None:
        """Show one panel, hide all others."""
        panels = {
            "portfolio": self.query_one("#portfolio-container"),
            "record": self.query_one("#record-container"),
            "import": self.query_one("#import-container"),
            "tax": self.query_one("#tax-container"),
            "viz": self.query_one("#viz-container"),
        }
        for name, panel in panels.items():
            panel.styles.display = "block" if name == panel_name else "none"

    def action_show_portfolio(self) -> None:
        self._show_panel("portfolio")

    def action_show_record(self) -> None:
        self._show_panel("record")
```

**Alternative: Screen-based navigation** (also valid for our use case):
```python
from textual.screen import Screen

class PortfolioScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield PortfolioContent()
        yield Footer()

# In app:
def action_show_portfolio(self) -> None:
    self.push_screen(PortfolioScreen())
```

**Recommendation for CryptoAccounting:** Use the **Screen-based approach** since our screens are heavier and more independent than Viper's panels. Viper's panels all relate to one ticker; our screens are distinct functional areas.

---

## 3. Widget State Machine Pattern

Every widget/panel follows this four-state pattern:

```python
class DataPanel(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._state: str = "empty"  # empty | loading | success | error
        self._data: Any = None
        self._error: str | None = None

    def show_loading(self) -> None:
        self._state = "loading"
        self._rebuild_content()

    def show_data(self, data: Any) -> None:
        self._state = "success"
        self._data = data
        self._rebuild_content()

    def show_error(self, error: str) -> None:
        self._state = "error"
        self._error = error
        self._rebuild_content()

    def _rebuild_content(self) -> None:
        container = self.query_one("#content", Container)
        container.remove_children()

        if self._state == "empty":
            container.mount(Label("[dim]No data loaded[/dim]"))
        elif self._state == "loading":
            container.mount(LoadingIndicator())
        elif self._state == "success":
            self._render_data(container)
        elif self._state == "error":
            container.mount(Label(f"[red]Error: {self._error}[/red]"))

    def _render_data(self, container: Container) -> None:
        # Subclass implements this
        raise NotImplementedError
```

---

## 4. Custom Message Pattern

Widgets communicate with the app via custom messages:

```python
from textual.message import Message

class ImportWizard(Widget):
    class ImportComplete(Message):
        def __init__(self, imported: int, skipped: int) -> None:
            self.imported = imported
            self.skipped = skipped
            super().__init__()

    class FileSelected(Message):
        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    def _do_import(self) -> None:
        result = self.app.crypto.import_transactions(...)
        self.post_message(self.ImportComplete(result['imported'], result['skipped']))

# In app - handler auto-discovered by naming convention:
class CryptoApp(App):
    def on_import_wizard_import_complete(self, event: ImportWizard.ImportComplete) -> None:
        self.notify(f"Imported {event.imported} transactions ({event.skipped} skipped)")
```

---

## 5. Async Data Loading Pattern

**Critical**: Never block the UI thread with database queries.

```python
from textual.worker import Worker

class PortfolioPanel(Widget):
    async def load_data(self) -> None:
        self.show_loading()
        try:
            # run_worker executes in background thread
            worker = self.app.run_worker(self._fetch_portfolio_data)
            await worker.wait()
        except Exception as e:
            self.show_error(str(e))

    def _fetch_portfolio_data(self) -> dict:
        """Runs in thread pool - safe to call blocking CryptoAccounts API."""
        crypto = self.app.crypto
        balance = crypto.get_balance('BTC')
        wallets = crypto.get_wallet_balance('BTC', None)
        return {'balance': balance, 'wallets': wallets}
```

**Simpler approach using `call_from_thread`**:
```python
@work(thread=True)
def load_balance(self) -> None:
    """Decorated method runs in thread automatically."""
    balance = self.app.crypto.get_balance('BTC')
    # Update UI from worker thread using call_from_thread
    self.app.call_from_thread(self._update_balance_display, balance)
```

---

## 6. Keybinding Patterns

### App-Level Bindings (shown in footer)
```python
BINDINGS = [
    ("q", "quit", "Quit"),           # Shown in footer
    ("p", "portfolio", "Portfolio"),   # Shown in footer
]
```

### Widget-Level Bindings (context-specific, hidden)
```python
class WalletTable(Widget):
    BINDINGS = [
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("enter", "select", "Select", show=False, priority=True),
    ]
```

**NOTE:** Use arrow keys (up/down) and Tab for navigation, NOT vim-style j/k.
Arrow keys + Tab are more intuitive for general users. Viper uses j/k but we
deliberately diverge here for accessibility.

Key flags:
- `show=False` - don't clutter footer with context-specific bindings
- `priority=True` - widget binding takes precedence over app binding

---

## 7. CSS Patterns

### Embedded CSS (Viper's approach - recommended)

```python
class CryptoApp(App):
    CSS = """
    Screen {
        background: #1a1a2e;
    }

    #main-container {
        layout: vertical;
        height: 1fr;
    }

    #menu-bar {
        height: 3;
        background: #16213e;
        layout: horizontal;
    }

    .menu-item {
        width: 1fr;
        content-align: center middle;
        text-style: bold;
    }

    .menu-item:hover {
        background: #0f3460;
    }

    #content-area {
        height: 1fr;
        padding: 1 2;
    }

    DataTable {
        height: 1fr;
    }

    DataTable > .datatable--header {
        text-style: bold;
        color: #f7931a;
    }

    .positive { color: #00ff00; }
    .negative { color: #ff0000; }
    .btc-orange { color: #f7931a; }
    .muted { color: #666666; }
    """
```

### Widget-Level DEFAULT_CSS

```python
class BalanceWidget(Widget):
    DEFAULT_CSS = """
    BalanceWidget {
        height: auto;
        padding: 1 2;
        border: solid #f7931a;
    }
    BalanceWidget .label {
        color: #888888;
    }
    BalanceWidget .value {
        text-style: bold;
        color: #f7931a;
    }
    """
```

### Color Scheme for Crypto Accounting

```
Background:     #1a1a2e (dark navy)
Surface:        #16213e (slightly lighter)
Accent/Primary: #f7931a (Bitcoin orange)
Positive:       #00ff00 (green - gains)
Negative:       #ff0000 (red - losses)
Muted:          #666666 (dim text)
Text:           #e0e0e0 (light gray)
Border:         #f7931a (orange borders)
Header BG:      #0f3460 (deep blue)
```

---

## 8. DataTable Usage

Textual's built-in DataTable widget (Viper builds custom tables, but DataTable is better for our tabular data):

```python
from textual.widgets import DataTable

class TransactionTable(Widget):
    def compose(self) -> ComposeResult:
        table = DataTable(id="tx-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#tx-table", DataTable)
        table.add_columns("Date", "Type", "Amount", "Currency", "Exchange", "Wallet")

    def load_transactions(self, transactions: list[dict]) -> None:
        table = self.query_one("#tx-table", DataTable)
        table.clear()
        for tx in transactions:
            table.add_row(
                tx['Date'], tx['Type'],
                f"{tx['Buy'] or tx['Sell']:.8f}",
                tx['Buy_Curr'] or tx['Sell_Curr'],
                tx['Exchange'], tx.get('Wallet', '')
            )
```

---

## 9. TabbedContent Pattern

```python
from textual.widgets import TabbedContent, TabPane

class TaxScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Gains Tracker", id="gains"):
                yield GainsPanel()
            with TabPane("1099-B Export", id="export"):
                yield ExportPanel()
            with TabPane("Forecast Sale", id="forecast"):
                yield ForecastPanel()
        yield Footer()
```

---

## 10. Form Input Pattern

```python
from textual.widgets import Input, Select, RadioSet, RadioButton, Button
from textual.containers import Vertical, Horizontal

class RecordTransactionForm(Widget):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Transaction Type:")
            with RadioSet(id="tx-type"):
                yield RadioButton("Buy", value=True)
                yield RadioButton("Sell")
                yield RadioButton("Transfer")
                yield RadioButton("Interest")

            yield Label("Exchange:")
            yield Select(
                [(w, w) for w in self._wallets],
                id="exchange",
                prompt="Select exchange"
            )

            yield Label("Quantity:")
            with Horizontal():
                yield Input(id="quantity", placeholder="0.00000000")
                yield Label("BTC", classes="unit-label")

            yield Label("Total USD:")
            with Horizontal():
                yield Input(id="total-usd", placeholder="0.00")
                yield Label("USD", classes="unit-label")

            yield Label("Date:")
            yield Input(id="date", placeholder="YYYY-MM-DD HH:MM:SS")

            with Horizontal(classes="button-row"):
                yield Button("Record", variant="primary", id="submit")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._record_transaction()
        elif event.button.id == "cancel":
            self.app.pop_screen()

    def _record_transaction(self) -> None:
        qty = float(self.query_one("#quantity", Input).value)
        total = float(self.query_one("#total-usd", Input).value)
        # ... call crypto.deposit(), crypto.execute_trade(), etc.
```

---

## 11. Modal/Help Screen Pattern

```python
from textual.screen import ModalScreen

class HelpScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 70;
        height: 30;
        border: double #f7931a;
        background: #1a1a2e;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Label("[bold #f7931a]Crypto Accounting - Help[/]")
            yield Label("")
            yield Label("[bold]Navigation[/]")
            yield Label("  P  Portfolio & Balances")
            yield Label("  R  Record Transaction")
            yield Label("  I  Import CSV")
            yield Label("  T  Tax & Reporting")
            yield Label("  V  Visualizations")
            yield Label("  ?  This help screen")
            yield Label("  Q  Quit")
            yield Label("")
            yield Label("[dim]Press ESC to close[/dim]")
```

---

## 12. Notification Pattern

```python
# Success notification
self.notify("Transaction recorded successfully", severity="information")

# Warning
self.notify("2025+ requires per-wallet accounting", severity="warning")

# Error
self.notify(f"Import failed: {error}", severity="error")
```

---

## 13. File Structure Convention

Based on Viper's structure, adapted for CryptoAccounting:

```
src/python/tui/
├── __init__.py
├── app.py                    # CryptoApp(App) - main app class
├── screens/                  # One file per major screen
│   ├── __init__.py
│   ├── dashboard.py          # DashboardScreen
│   ├── portfolio.py          # PortfolioScreen
│   ├── ledger.py             # LedgerScreen
│   ├── transactions.py       # RecordTransactionScreen
│   ├── imports.py            # ImportWizardScreen
│   ├── tax_reporting.py      # TaxReportingScreen
│   ├── export.py             # ExportScreen
│   ├── visualizations.py     # VisualizationScreen
│   └── help.py               # HelpScreen (ModalScreen)
└── widgets/                  # Reusable custom widgets
    ├── __init__.py
    ├── balance_bar.py        # Balance summary bar
    ├── transaction_table.py  # DataTable wrapper for transactions
    └── form_fields.py        # Common form input patterns
```

---

## 14. Testing Pattern

```python
import pytest
from textual.pilot import Pilot

@pytest.mark.asyncio
async def test_app_launches():
    app = CryptoApp()
    async with app.run_test() as pilot:
        # App should show dashboard
        assert app.query_one("#dashboard-container")

@pytest.mark.asyncio
async def test_portfolio_keybinding():
    app = CryptoApp()
    async with app.run_test() as pilot:
        await pilot.press("p")
        # Should navigate to portfolio
        assert isinstance(app.screen, PortfolioScreen)

@pytest.mark.asyncio
async def test_record_transaction():
    app = CryptoApp()
    async with app.run_test() as pilot:
        await pilot.press("r")
        # Fill form
        await pilot.click("#quantity")
        await pilot.press(*"0.005")
        await pilot.click("#submit")
        # Verify transaction recorded
```

---

## Key Takeaways for Implementation

1. **Embed CSS in Python** - no separate .tcss files (simpler, follows Viper pattern)
2. **State machine for every panel** - empty/loading/success/error
3. **Custom messages** for widget-to-app communication
4. **`@work(thread=True)`** for all CryptoAccounts API calls (they're blocking)
5. **Screens over panels** for our use case (distinct functional areas)
6. **Arrow key + Tab navigation** in list widgets (NOT vim j/k - more accessible for general users)
7. **`priority=True`** on widget bindings to override app bindings when focused
8. **Rich markup** in Labels for inline styling (`[bold #f7931a]text[/]`)
11. **Label.content** to read text (NOT `.renderable` which was removed in Textual v7.5+)
9. **`notify()`** for user feedback (success/warning/error)
10. **Bitcoin orange `#f7931a`** as accent color throughout

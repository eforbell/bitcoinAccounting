# Feature-9: Interactive TUI Application - Analysis & Recommendation

## Executive Summary

This document analyzes two approaches for adding a graphical interface to the Crypto Accounting system: a **Textual TUI** (Terminal User Interface) and a **Web Front-End** (Flask/FastAPI). After weighing the trade-offs, the recommendation is to build a **Textual TUI** as the primary interactive interface, with the existing CLI scripts preserved as-is.

The TUI will serve as a **unified menu-driven application** that exposes *all* system functionality - portfolio views, transaction recording, CSV imports, tax reporting, visualizations, and diagnostics - through a single entry point.

---

## Current State

### What Exists Today

The system currently has **20 standalone CLI scripts** covering five functional areas:

| Category | Scripts | Interface Style |
|----------|---------|-----------------|
| **Record Transactions** | `buySats`, `sell`, `transfer`, `earnInterest` | Interactive (prompt_toolkit) |
| **Portfolio Views** | `balance`, `wallet_balances`, `wallet_ledger`, `trades`, `exchange_liquidity` | Batch (args + stdout) |
| **Tax & Reporting** | `gains_tracker`, `export_1099b`, `export_tx`, `forecast_gains` | Batch (args + file output) |
| **Import** | `import_csv`, `compare_with_sparrow`, `validate_transfers` | Batch (args + stdout) |
| **Visualizations** | `btc_viz` | Batch (args + file output) |
| **Database** | `diagnose_balances`, `migrate_to_sqlite` | Batch (args + stdout) |

### Pain Points for New Users

1. **Discovery** - Users must know which script to run and what arguments it expects
2. **Context Switching** - Moving between scripts loses flow (e.g., checking balance, then selling, then forecasting)
3. **Argument Syntax** - Each script has different argument patterns (`--wallet=X` vs `--wallet X` vs positional)
4. **No Guided Flow** - New users importing legacy data have no guided onboarding path
5. **Output Fragmentation** - Results print to stdout and disappear on scroll

### Architecture Advantage

The Feature-8 refactoring created an excellent foundation. All business logic lives in `CryptoAccounts` and its query classes with clean dependency injection. The TUI only needs to wrap this existing API - no new business logic required.

```
┌─────────────────────────────────┐
│         TUI Application         │  ← NEW (Feature-9)
│  (Textual screens & widgets)    │
├─────────────────────────────────┤
│       CryptoAccounts API        │  ← EXISTS (Feature-8)
│  TransactionQuery │ LedgerWriter│
│  CapitalGainCalc  │ WalletQuery │
├─────────────────────────────────┤
│     DatabaseBackend (SQLite)    │  ← EXISTS (Feature-1)
└─────────────────────────────────┘
```

---

## Option A: Textual TUI

### What is Textual?

[Textual](https://textual.textualize.io/) is a Python framework for building rich terminal applications. It provides CSS-like styling, reactive widgets, and modern UI patterns - all running in a terminal. Think of it as "React for the terminal."

### Proposed Architecture

```
src/python/
├── tui/                          # NEW - TUI package
│   ├── __init__.py
│   ├── app.py                    # Main CryptoApp(App) entry point
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── dashboard.py          # Home screen with portfolio overview
│   │   ├── portfolio.py          # Balances, wallet breakdown
│   │   ├── transactions.py       # Record buy/sell/transfer/interest
│   │   ├── imports.py            # Import wizard with file picker
│   │   ├── tax_reporting.py      # Gains tracker, 1099-B, forecasting
│   │   ├── export.py             # Transaction exports
│   │   └── visualizations.py     # Chart generation & launch
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── balance_bar.py        # Balance summary widget
│   │   ├── transaction_table.py  # DataTable for transactions
│   │   ├── lot_table.py          # DataTable for FIFO lots
│   │   └── form_fields.py        # Reusable form inputs
│   └── styles/
│       └── app.tcss              # Textual CSS stylesheet
│
src/scripts/
    └── crypto_tui                # NEW - Entry point script
```

### Screen Flow

```
┌──────────────────────────────────────────────────┐
│               MAIN DASHBOARD                      │
│                                                    │
│  BTC Balance: 1.23456789    Cost Basis: $45,230   │
│  Current Price: $97,500     Unrealized: +$75,120  │
│                                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐│
│  │  Portfolio   │ │  Record Tx  │ │   Import     ││
│  │  [P]        │ │  [R]        │ │   [I]        ││
│  ├─────────────┤ ├─────────────┤ ├──────────────┤│
│  │  Tax/Report │ │  Visualize  │ │   Settings   ││
│  │  [T]        │ │  [V]        │ │   [S]        ││
│  └─────────────┘ └─────────────┘ └──────────────┘│
│                                                    │
│  Recent Activity:                                  │
│  2026-02-10  Buy   0.005 BTC @ $97,200  Strike   │
│  2026-02-08  Buy   0.010 BTC @ $96,800  River    │
│  2026-02-05  Xfer  0.015 BTC  Strike → Vault     │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│            PORTFOLIO SCREEN                       │
│                                                    │
│  Tabs: [Balances] [Wallet Detail] [Trades]        │
│        [Exchange Liquidity]                        │
│                                                    │
│  ┌──────────────────────────────────────────────┐│
│  │ Wallet          Balance      %     Custody   ││
│  │ ─────────────────────────────────────────── ││
│  │ Vault           0.89000000  72.1%  Self      ││
│  │ Strike          0.15456789  12.5%  Custodial ││
│  │ Ledger-2        0.10000000   8.1%  Self      ││
│  │ River           0.09000000   7.3%  Custodial ││
│  │ ─────────────────────────────────────────── ││
│  │ TOTAL           1.23456789  100%             ││
│  └──────────────────────────────────────────────┘│
│                                                    │
│  Custody: Self-custodied 80.2% | Custodial 19.8% │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│         RECORD TRANSACTION SCREEN                 │
│                                                    │
│  Type: (o) Buy  ( ) Sell  ( ) Transfer  ( ) Interest│
│                                                    │
│  Exchange:    [Strike          ▾]                  │
│  Quantity:    [0.005           ] BTC               │
│  Total Cost:  [$487.50        ] USD                │
│  Fee:         [0              ] BTC                │
│  Date:        [2026-02-11     ] [14:30:00]         │
│  Group:       [               ] (optional)         │
│                                                    │
│  ── Preview ──────────────────────────────────── │
│  Buy 0.00500000 BTC @ $97,500.00/BTC              │
│  Total: $487.50 | Fee: 0 BTC                      │
│                                                    │
│  [ ] Withdraw to cold storage after purchase       │
│      Wallet: [Vault ▾]                             │
│                                                    │
│  [Record Transaction]              [Cancel]        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│            IMPORT WIZARD SCREEN                   │
│                                                    │
│  Step 1 of 3: Select File                         │
│  ━━━━━━━━━━━━━━━━  ░░░░░░░░░░░░░░░░░░░░░░░░░   │
│                                                    │
│  File: [~/Downloads/coinbase-2024.csv    ] [Browse]│
│                                                    │
│  Detected Format: Coinbase (Exchange)              │
│  Rows Found: 247                                   │
│                                                    │
│  Options:                                          │
│  Withdraw-to wallet: [Vault            ▾]         │
│  [x] Dry-run first (preview without importing)     │
│                                                    │
│  [Next →]                             [Cancel]     │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│          TAX & REPORTING SCREEN                   │
│                                                    │
│  Tabs: [Gains Tracker] [1099-B Export]             │
│        [Forecast Sale] [Export Transactions]        │
│                                                    │
│  ── Capital Gains: 2025 ──────────────────────── │
│  Wallet: [All Wallets ▾]  Coin: [BTC ▾]          │
│                                                    │
│  Short-Term (<1yr):  3 sales   Gain: $1,234.56    │
│  Long-Term  (≥1yr):  1 sale    Gain: $5,678.90    │
│  TOTAL:              4 sales   Gain: $6,913.46    │
│                                                    │
│  ┌──────────────────────────────────────────────┐│
│  │ Sale Date   Qty         Proceeds  Cost   G/L ││
│  │ 01/15/2025  0.01000000  $975.00  $450   $525 ││
│  │ 03/20/2025  0.00500000  $510.00  $275   $235 ││
│  │ ...                                          ││
│  └──────────────────────────────────────────────┘│
│                                                    │
│  [Export 1099-B CSV]  [Export Worksheet]            │
└──────────────────────────────────────────────────┘
```

### Textual Capabilities Used

| Feature | Widget/API | Use Case |
|---------|-----------|----------|
| Navigation | `Screen`, `push_screen()` | Menu → sub-screens |
| Data display | `DataTable` | Transaction lists, lot breakdowns, wallet balances |
| Forms | `Input`, `Select`, `RadioSet`, `Checkbox` | Transaction recording, import options |
| Layout | `Container`, `Horizontal`, `Vertical` | Screen composition |
| Styling | `.tcss` files | Bitcoin-orange theme, consistent look |
| Keybindings | `Binding` | Keyboard shortcuts (P=Portfolio, R=Record, etc.) |
| Notifications | `notify()` | Success/error messages |
| Progress | `ProgressBar` | Import progress |
| File picker | `DirectoryTree` / custom | CSV file selection |
| Tabs | `TabbedContent` | Sub-views within screens |
| Rich text | `Static`, `RichLog` | Formatted output areas |

### Pros

- **Pure Python** - no additional tech stack, same language as the entire project
- **Direct API access** - calls `CryptoAccounts` methods directly, no serialization layer
- **Terminal-native** - fits the project's identity as a power-user tool
- **Works over SSH** - useful for headless/server setups
- **Keyboard-first** - efficient navigation for experienced users
- **Fast iteration** - Textual has hot-reload during development
- **Rich rendering** - tables, colors, borders, progress bars, rich text
- **Low dependency count** - just `textual` (pulls in `rich` which is already common)
- **Testable** - Textual has a built-in testing framework (`pilot`)
- **You enjoy TUIs** - developer satisfaction matters for maintenance

### Cons

- **No inline charts** - matplotlib PNGs must be opened externally (OS viewer)
- **Terminal dependency** - requires a modern terminal emulator (iTerm2, Kitty, etc.)
- **Fixed-width rendering** - tables constrained by terminal width
- **Steeper learning curve for Textual** - CSS-like styling has its own idioms
- **No mouse-first users** - some new users may expect point-and-click web experience

### Mitigation for Cons

- Charts: TUI triggers generation and opens in default viewer (`open` on macOS)
- Terminal: Works well in macOS Terminal.app, iTerm2, VS Code terminal
- Width: Responsive layouts with Textual CSS breakpoints
- New users: Clear on-screen help, guided flows, sensible defaults
- **CSS learning curve: De-risked** - see `feature-9-textual-patterns.md` extracted from the Viper TUI project (`~/workspace/viper`), a production Bloomberg-like terminal built entirely on Textual. Patterns cover app setup, panel toggling, state machines, async loading, keybindings, CSS embedding, DataTable usage, forms, modals, and testing.

---

## Option B: Web Front-End (Flask/FastAPI + HTML)

### Proposed Architecture

```
src/python/
├── web/                          # NEW - Web package
│   ├── __init__.py
│   ├── app.py                    # FastAPI application
│   ├── routes/
│   │   ├── dashboard.py
│   │   ├── portfolio.py
│   │   ├── transactions.py
│   │   ├── imports.py
│   │   ├── tax.py
│   │   └── viz.py
│   ├── templates/                # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── portfolio.html
│   │   └── ...
│   └── static/
│       ├── css/
│       ├── js/
│       └── img/
```

### Pros

- **Universally familiar** - everyone knows how to use a browser
- **Inline charts** - embed matplotlib/plotly charts directly in pages
- **Responsive design** - works on any screen size
- **Rich interactivity** - dropdowns, date pickers, modals, drag-and-drop file upload
- **Future extensibility** - could eventually be deployed as a service

### Cons

- **Two tech stacks** - Python backend + HTML/CSS/JS frontend
- **API layer required** - must build REST/JSON endpoints wrapping CryptoAccounts
- **State management** - HTTP is stateless; need sessions or token auth
- **More dependencies** - FastAPI/Flask, Jinja2, possibly a JS framework
- **Security surface** - even on localhost, need to consider CSRF, injection, etc.
- **Slower development** - HTML templates, CSS styling, JavaScript interactivity
- **Packaging complexity** - harder to distribute (pip install + browser launch)
- **Heavier runtime** - web server + browser vs. single terminal process

---

## Comparison Matrix

| Criterion | Textual TUI | Web UI | Winner |
|-----------|:-----------:|:------:|:------:|
| Development speed | Fast | Slow | **TUI** |
| Lines of code (est.) | ~2,500 | ~5,000+ | **TUI** |
| New dependencies | 1 (textual) | 3-5 | **TUI** |
| API integration | Direct calls | REST layer needed | **TUI** |
| Inline charts | External viewer | Embedded | **Web** |
| User familiarity | Terminal users | Everyone | **Web** |
| Testing | Textual Pilot | Selenium/Playwright | **TUI** |
| Packaging | pip install | pip + browser | **TUI** |
| Power-user efficiency | Keyboard shortcuts | Mouse-driven | **TUI** |
| Maintenance burden | Low | Medium-High | **TUI** |
| Project identity fit | Strong | Moderate | **TUI** |
| SSH/remote access | Works natively | Port forwarding | **TUI** |

**Score: TUI 9 - Web 3**

---

## Recommendation: Textual TUI

Build the interactive interface as a **Textual TUI application** for these reasons:

1. **Fastest path to value** - Direct Python API calls, no serialization layer, single language
2. **Project identity** - This is a power-user Bitcoin accounting tool. Terminal-native fits.
3. **Architecture alignment** - CryptoAccounts API + query classes are already perfectly structured for direct consumption
4. **Developer preference** - You enjoy TUIs, which means better long-term maintenance
5. **Minimal dependencies** - Just `textual` added to requirements.txt
6. **Testability** - Textual's `pilot` test framework integrates with existing pytest suite
7. **Preserves CLI** - All existing scripts continue to work; TUI is an *additional* interface, not a replacement

### Future Web Layer

If a web interface is desired later (Feature-11+), the TUI work still pays off:
- Screen logic and data flows translate directly to web routes
- Business logic stays in CryptoAccounts (already decoupled)
- Web becomes a second UI layer, not a rewrite

---

## Proposed Story Breakdown

The feature is organized into **12 stories** across 4 phases:

### Phase 1: Foundation (Stories 1-3)
Set up the Textual application shell, navigation, and dashboard.

| ID | Story | Priority | Est. Lines |
|----|-------|----------|------------|
| TUI-001 | Application shell & main menu | 1 | ~200 |
| TUI-002 | Dashboard screen with portfolio summary | 2 | ~250 |
| TUI-003 | Textual CSS theme & styling | 3 | ~150 |

### Phase 2: Portfolio & Viewing (Stories 4-6)
Read-only screens displaying existing data.

| ID | Story | Priority | Est. Lines |
|----|-------|----------|------------|
| TUI-004 | Portfolio screen (balances + wallet breakdown) | 4 | ~300 |
| TUI-005 | Transaction ledger screen with filtering | 5 | ~250 |
| TUI-006 | Trade history & exchange liquidity screens | 6 | ~250 |

### Phase 3: Actions & Recording (Stories 7-9)
Screens that write data - transaction recording and CSV imports.

| ID | Story | Priority | Est. Lines |
|----|-------|----------|------------|
| TUI-007 | Record transaction screen (buy/sell/transfer/interest) | 7 | ~400 |
| TUI-008 | Import wizard screen (file select, preview, import) | 8 | ~350 |
| TUI-009 | Export transactions screen | 9 | ~200 |

### Phase 4: Tax, Viz & Polish (Stories 10-12)
Tax reporting, chart generation, and final polish.

| ID | Story | Priority | Est. Lines |
|----|-------|----------|------------|
| TUI-010 | Tax reporting screen (gains tracker + 1099-B + forecast) | 10 | ~400 |
| TUI-011 | Visualization screen (chart generation + external viewer) | 11 | ~200 |
| TUI-012 | Help system, keyboard shortcuts, error handling polish | 12 | ~200 |

**Total estimated new code: ~3,150 lines** (plus ~200 lines Textual CSS)

### Dependency Chain

```
TUI-001 (shell) → TUI-002 (dashboard) → TUI-003 (styling)
                → TUI-004 (portfolio) → TUI-005 (ledger) → TUI-006 (trades)
                → TUI-007 (record tx) → TUI-008 (import) → TUI-009 (export)
                → TUI-010 (tax) → TUI-011 (viz) → TUI-012 (polish)
```

Stories within each phase can be developed linearly. The foundation (Phase 1) must be complete before other phases begin.

---

## Technical Decisions

### Entry Point

```bash
# New unified entry point
crypto_tui          # Launch the TUI application

# Existing CLI scripts preserved
buySats             # Still works as before
import_csv file.csv # Still works as before
```

### Database Connection Management

The TUI maintains a single `CryptoAccounts` instance for the session lifetime (vs. scripts that open/close per invocation). This gives better performance and enables reactive updates.

```python
class CryptoApp(App):
    def on_mount(self):
        self.crypto = CryptoAccounts()

    def on_unmount(self):
        self.crypto.close()
```

### Screen Pattern

Each screen follows a consistent pattern:

```python
class PortfolioScreen(Screen):
    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield TabbedContent(...)
        yield Footer()

    def on_mount(self):
        self.load_data()

    def load_data(self):
        # Call CryptoAccounts API
        # Populate widgets
```

### Chart Handling

Since Textual can't render images inline, charts are:
1. Generated to the standard output directory (`output/viz/`)
2. Opened in the OS default viewer via `subprocess.run(["open", path])` on macOS
3. TUI shows a confirmation message with the file path

### New Dependency

Only one new package:
```
textual>=0.47.0
```

(Textual includes `rich` as a dependency, which handles colored terminal output.)

---

## Risk Assessment

### High Risk
- None identified (TUI is purely additive; no existing functionality modified)

### Medium Risk
- ~~Textual CSS learning curve may slow initial development~~ **De-risked**: Viper TUI patterns extracted to `feature-9-textual-patterns.md` - covers all needed patterns including CSS embedding, state machines, async workers, keybindings, forms, DataTables, and testing
- Long-running database queries could block the TUI event loop (mitigate with `@work(thread=True)` decorator or `run_worker()` - both patterns demonstrated in Viper)

### Low Risk
- Chart opening behavior varies by OS (mitigate with platform detection)
- Terminal width constraints for wide tables (mitigate with horizontal scrolling)

---

## Success Criteria

1. Single `crypto_tui` command launches the full application
2. All 20 existing script functions accessible through the TUI
3. New users can import legacy CSV, view balances, and generate tax reports without touching the CLI
4. Keyboard navigation for all screens (no mouse required, but mouse supported)
5. All existing CLI scripts continue to work unchanged
6. Test coverage for TUI screens via Textual Pilot framework
7. Textual CSS theme with consistent Bitcoin-orange branding

---

## References

- [Textual Documentation](https://textual.textualize.io/)
- [Textual Widget Gallery](https://textual.textualize.io/widget_gallery/)
- [Textual CSS Guide](https://textual.textualize.io/css_guide/)
- Feature-8 Summary: `planning/features/feature-8-summary.md`
- Current Scripts: `src/scripts/` (20 entry points)
- CryptoAccounts API: `src/python/cryptoAccounts.py`

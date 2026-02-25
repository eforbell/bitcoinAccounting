# Getting Started

The fastest way to use Bitcoin Accounting is through the interactive **Terminal UI (TUI)**. It gives you access to everything -- portfolio tracking, transaction recording, CSV imports, tax reporting, and visualizations -- from a single interface. Navigate with keyboard shortcuts or use the mouse -- click buttons, select table rows, scroll, and interact with forms directly.

## Install

```bash
# Clone the repo
git clone https://github.com/eforbell/bitcoinAccounting.git
cd bitcoinAccounting

# Install dependencies
python -m pip install -r requirements.txt
python -m pip install -e .
```

No database setup required. A SQLite database is created automatically on first use at `~/.bitcoinaccounting/ledger.db`.
Using `-e` (editable install) means `git pull` updates are usually picked up without reinstalling.

## Launch the TUI

```bash
python -m bitcoinAccounting
```

Alternative (direct script):

```bash
python -m bitcoinAccounting
```

Installed entrypoints (after `python -m pip install .`):

```bash
bitcoin-accounting
```

You'll land on the **Dashboard**, which shows your BTC balance, cost basis, custody breakdown, and recent transactions. From here you can navigate to any screen using the keyboard shortcuts shown on the main menu.

## Keyboard Navigation

| Key | Screen | What it does |
|-----|--------|-------------|
| **P** | Portfolio | Wallet balances with custody breakdown |
| **L** | Ledger | Full transaction history with filters and summary stats |
| **X** | Trades | Trade history and exchange liquidity analysis |
| **R** | Record | Manually enter buys, sells, transfers, interest |
| **I** | Import | Import CSV files from exchanges and wallets |
| **E** | Export | Export filtered transactions to CSV |
| **T** | Tax | Gains tracker, 1099-B export, and sale forecast |
| **V** | Visualize | Generate charts and PDF reports |
| **W** | Wallets | Manage wallet metadata (create, edit, rename, merge) |
| **?** / **F1** | Help | Keyboard shortcut reference |
| **Esc** | -- | Go back to previous screen |
| **Q** | -- | Quit |

> **Treasury Integrity panel**: The Dashboard displays a **Treasury Integrity** panel with the latest health score. Click **View Details →** to open the Attestation screen (finding drill-down, filters, and export).

## Common Workflows

### 1. Import your exchange history

Press **I** to open the Import Wizard.

1. Type a file path or click **Browse** to find your CSV file
2. Click **Detect Format** -- the system auto-detects your exchange (Coinbase, Kraken, Strike, River, Swan, Cash App, Gemini) or wallet (Ledger, Trezor, Sparrow, Coldcard)
3. Configure options (wallet name for wallet imports, dry-run toggle)
4. Preview and import

### 2. Record a transaction

Press **R** to open the Record Transaction screen. Choose a type:

- **Buy** -- Record a BTC purchase with optional auto-withdrawal to cold storage
- **Sell** -- Record a sale with optional transfer from wallet to exchange
- **Transfer** -- Move BTC between wallets (creates withdrawal + deposit pair)
- **Earn Interest** -- Record staking/interest income

A live preview updates as you fill in the form.

### 3. Check your portfolio

Press **P** to see wallet balances with custody breakdown (self-custodied, custodial, multisig). Toggle inactive wallets on/off.

Press **L** to open the Ledger for full transaction history. Filter by coin, wallet, and date range. When a specific coin is selected, a summary bar shows total credits, debits, fees, net balance, and transaction count.

### 4. Tax season

Press **T** to open Tax Reporting with three tabs:

- **Gains Tracker** -- Load realized capital gains for a tax year with lot-by-lot breakdown
- **1099-B Export** -- Generate TaxAct-compatible CSV files for filing
- **Forecast Sale** -- Model a hypothetical sale to see short-term vs. long-term tax impact before selling

All tools support per-wallet FIFO accounting (required for IRS 2025+ compliance).

### 5. Generate charts

Press **V** to open Visualizations. Choose a chart type (Orange Plot, Balance, Custody, or PDF Report), set a date range and DPI, then generate. Open the results directly from the TUI.

### 6. Monthly treasury attestation

At the end of each month, produce a durable evidence bundle for your treasury.

**Quick start (CLI + Python):**

```bash
# 1. Persist this month's health snapshot
bitcoin-integrity --persist

# 2. Generate a JSON attestation bundle via Python
python - <<'EOF'
from db.backend import get_backend
from attestation.generator import AttestationGenerator
import datetime, json

backend = get_backend()
gen = AttestationGenerator(backend)
today = datetime.date.today()
bundle = gen.generate(year=today.year, month=today.month)
print(json.loads(gen.export_bundle_json(bundle))["metadata"])
EOF
```

**From the TUI:**

1. The Dashboard shows the **Treasury Integrity** panel with your latest health score.
2. Click **View Details →** to open the Attestation screen.
3. Use the source and severity filter buttons to focus on critical findings.
4. Click **Export JSON** or **Export CSV** to save the finding list.

**Optional PDF summary (requires `reportlab`):**

```bash
pip install reportlab
```

```python
from attestation.reports import AttestationReportFormatter
from pathlib import Path
formatter = AttestationReportFormatter(backend=backend)
formatter.generate_pdf(bundle, Path("attestation.pdf"))
```

See the [Monthly Treasury Attestation](README.md#monthly-treasury-attestation) section in the README for the full workflow including alert rules and finding lifecycle management.

## Supported Exchanges & Wallets

**Exchanges**: Coinbase, Coinbase Pro, Kraken, Strike, River, Swan, Cash App, Gemini

**Wallets**: Ledger Live, Trezor Suite, Sparrow Wallet, Coldcard

All formats are auto-detected from CSV headers. See [docs/CSV_FORMAT_GUIDE.md](docs/CSV_FORMAT_GUIDE.md) for export instructions per platform.

## CLI Scripts

The same functionality is also available as individual CLI scripts in `src/scripts/`. Useful for scripting, automation, or if you prefer a traditional command-line workflow. See the [README](README.md#workflow) for the full script reference.

## Database Options

- **SQLite** (default) -- Zero config, works immediately
- **PostgreSQL** -- For multi-user or network access

See the [README](README.md#environment-variables) for PostgreSQL setup and configuration details.

## Rebrand Status

- Canonical module names are now `bitcoinAccounting` and `bitcoinAccounts`.
- Canonical default SQLite path is `~/.bitcoinaccounting/ledger.db`.
- Rebrand deprecations completed on February 19, 2026:
  - Legacy CLI aliases removed
  - Legacy module shim files removed
  - Legacy data path fallback removed

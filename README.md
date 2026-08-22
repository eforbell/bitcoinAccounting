# Bitcoin Accounting System

Lightweight bookkeeping and reporting for Bitcoin with SQLite or PostgreSQL.

Includes an interactive terminal UI and CLI scripts for maintaining a transaction
ledger and producing balance, cost-basis reports, and visualizations.

## Key Features
- **Interactive Terminal UI** - Full-featured TUI for portfolio tracking, imports, tax reporting, and more
- **Zero-config SQLite option** - Start tracking immediately with no database setup
- **PostgreSQL support** - Use existing PostgreSQL infrastructure if preferred
- Store transactions (deposits, withdrawals, trades, mining/interest)
- Compute balances and cost-basis automatically
- CLI helpers for common operations (buy, sell, transfer, export)
- Tax reporting (1099-B exports, FIFO calculations)
- Chart generation and PDF reports
- Bulk import from exchanges (Coinbase, Kraken, Strike, River, Swan, Cash App, Gemini) and wallets (Ledger, Trezor, Sparrow, Coldcard) with auto-detection
- **Treasury integrity checks** - Deterministic ledger reconciliation, transfer-pair validation, cost-basis continuity, and a weighted health score via `bitcoin-integrity`
- **Monthly attestation workflow** - Generate durable month-end evidence bundles (JSON/CSV/PDF), track finding lifecycle (new → acknowledged → resolved), and monitor score trends from the TUI

## Getting Started

**New here?** The fastest way to get started is the interactive **Terminal UI (TUI)** -- install dependencies, run one command, and you're in. Fully keyboard-driven with excellent mouse support:

```bash
python -m pip install -r requirements.txt
python -m pip install .
bitcoin-accounting
```

Editable install option (recommended for users who pull updates):

```bash
python -m pip install -e .
```

With `-e`, pulling new commits usually updates behavior immediately without reinstalling.

Alternative launchers:

```bash
python -m bitcoinAccounting
```

Installed entrypoint launcher:

```bash
bitcoin-accounting
```

See the **[Getting Started Guide](GETTING_STARTED.md)** for a walkthrough of the TUI, keyboard shortcuts, and common workflows.

---

## Run the Web App Locally

The repo also includes a FastAPI web app with a bundled frontend shell under `src/python/web/`.

For local development on this machine, prefer the repo-local virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
```

The web app reads `.env` from the repository root via the database package import. For a simple local SQLite run, this is enough:

```bash
cp .env.example .env
```

Recommended local `.env` settings:

```env
DB_BACKEND=sqlite
BITCOIN_ACCOUNTING_ENV=development
BITCOIN_ACCOUNTING_AUTH_ENABLED=0
BITCOIN_ACCOUNTING_WEB_BASE_PATH=
BITCOIN_ACCOUNTING_WEB_DOCS=1
```

Initialize runtime state before starting the server:

```bash
.venv/bin/bitcoin-accounting-web-init
```

Then run the app server with the new one-liner:

```bash
.venv/bin/bitcoin-accounting-web
```

Python module form:

```bash
.venv/bin/python -m web
```

You can still run the explicit `uvicorn` command if you want:

```bash
.venv/bin/uvicorn web.app:create_app --factory --host 127.0.0.1 --port 3010
```

Open it at:

```text
http://127.0.0.1:3010/
```

Useful local endpoints:

- UI: `http://127.0.0.1:3010/`
- OpenAPI docs: `http://127.0.0.1:3010/docs`
- Liveness: `http://127.0.0.1:3010/api/health`
- Readiness: `http://127.0.0.1:3010/api/ready`

Notes:

- SQLite is the default local backend and `bitcoin-accounting-web-init` will create the core tables automatically for SQLite.
- The web launcher defaults to `127.0.0.1:3010`. For example: `.venv/bin/bitcoin-accounting-web --reload --port 3011`
- If you set `BITCOIN_ACCOUNTING_AUTH_ENABLED=1`, you must also set `BITCOIN_ACCOUNTING_AUTH_PASSPHRASE` and `BITCOIN_ACCOUNTING_SESSION_SECRET` before startup.
- If you want to test a subpath mount locally, set `BITCOIN_ACCOUNTING_WEB_BASE_PATH=/bitcoin-accounting` and serve the app behind a proxy that strips that prefix before forwarding upstream.

---

## Rebrand Status

As of **February 19, 2026**, the canonical runtime names are:

- Module entrypoint: `bitcoinAccounting`
- Core API module: `bitcoinAccounts`
- Default SQLite path: `~/.bitcoinaccounting/ledger.db`

Rebrand deprecation milestones completed on **February 19, 2026**:

- Legacy runtime command aliases removed
- Legacy module shim files removed
- Legacy home-directory fallback removed

Current path policy:

- If `SQLITE_DB_PATH` is set, it always wins.
- If unset, the app uses `~/.bitcoinaccounting/ledger.db`.

---

## Quick Start (CLI Scripts)

Prefer individual command-line scripts? Everything the TUI does is also available as standalone scripts.

### Option 1: SQLite (Recommended for Most Users)

**Zero configuration required!** Just install dependencies and start using the scripts.

1. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Start using the scripts immediately:

```bash
# Buy some BTC
src/scripts/buySats

# Check your balance
src/scripts/balance

# View trade history
src/scripts/trades BTC
```

The database file will be automatically created at `~/.bitcoinaccounting/ledger.db` on first use.

### Option 2: PostgreSQL (For Advanced Users)

If you need multi-user access, network access, or have existing PostgreSQL infrastructure:

1. Create a PostgreSQL database and user:

```sql
-- Run in psql as a DB admin
CREATE DATABASE bitcoin_accounting;
CREATE USER bitcoin_accountant WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE bitcoin_accounting TO bitcoin_accountant;
```

2. Apply the schema:

```bash
# From the repository root - creates all tables
psql -U <db-admin> -d bitcoin_accounting -f src/sql/tables.sql
```

The `tables.sql` file creates all required tables:
- `coins` - Cryptocurrency metadata
- `ledger` - Transaction history (buys, sells, transfers, etc.)
- `pair_price` - Historical price data for cost basis calculations
- `wallets` - Wallet/account metadata (matches ledger.exchange field)
- `integrity_health_snapshots` - Treasury health score history (used by `bitcoin-integrity --persist`)

All query logic is implemented in Python for database-agnostic support (works with both SQLite and PostgreSQL).

3. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

4. Configure PostgreSQL connection:

**IMPORTANT: Use .env file for credentials - NEVER commit credentials to git**

```bash
# Copy the example file
cp .env.example .env

# Edit .env and fill in your credentials:
# DB_BACKEND=postgres
# PGHOST=localhost
# PGPORT=5432
# PGUSER=bitcoin_accountant
# PGPASSWORD=your-secure-password
# PGDATABASE=bitcoin_accounting
```

The `.env` file is automatically loaded by all scripts and is in `.gitignore` to prevent accidental commits.

## Environment Variables

### Database Selection

- **`DB_BACKEND`**: Choose database backend
  - `sqlite` (default) - Local file-based database
  - `postgres` - PostgreSQL database

- **`SQLITE_DB_PATH`**: Path to SQLite database file
  - Default: `~/.bitcoinaccounting/ledger.db`
  - Use `:memory:` for in-memory database (testing only)

### PostgreSQL Configuration

Required when `DB_BACKEND=postgres`:

- **`PGHOST`**: PostgreSQL server hostname (e.g., `localhost`)
- **`PGPORT`**: PostgreSQL server port (default: `5432`)
- **`PGUSER`**: PostgreSQL username
- **`PGPASSWORD`**: PostgreSQL password
- **`PGDATABASE`**: PostgreSQL database name

## Choosing SQLite vs PostgreSQL

### Use SQLite if you:
- Are a single user tracking your own portfolio
- Want zero setup and maintenance
- Need a portable database file (backup = copy file)
- Run on a local machine (laptop, desktop)
- Want the simplest possible experience

### Use PostgreSQL if you:
- Need multi-user concurrent access
- Want network access from multiple machines
- Have existing PostgreSQL infrastructure
- Need advanced backup/replication features
- Are already using PostgreSQL for other projects

**Performance note**: For typical personal Bitcoin portfolios (< 100k transactions), SQLite and PostgreSQL perform identically. SQLite is actually faster for single-user workloads.

## Migrating from PostgreSQL to SQLite

If you're currently using PostgreSQL and want to switch to SQLite:

1. Run the migration script:

```bash
# Ensure PostgreSQL environment variables are set
export PGHOST=localhost
export PGUSER=bitcoin_accountant
export PGPASSWORD=your-password
export PGDATABASE=bitcoin_accounting

# Run migration (dry-run to preview)
src/scripts/migrate_to_sqlite --dry-run

# Run actual migration
src/scripts/migrate_to_sqlite --output ~/.bitcoinaccounting/ledger.db
```

2. Verify the migration:

```bash
# Set SQLite as the backend
export DB_BACKEND=sqlite
export SQLITE_DB_PATH=~/.bitcoinaccounting/ledger.db

# Check balances match
src/scripts/balance
```

3. Compare a few transactions:

```bash
# Check recent transactions
src/scripts/wallet_ledger WALLET_NAME

# Verify trade history
src/scripts/trades BTC
```

4. Once verified, update your shell profile to use SQLite by default:

```bash
# Add to ~/.bashrc or ~/.zshrc
export DB_BACKEND=sqlite
export SQLITE_DB_PATH=~/.bitcoinaccounting/ledger.db
```

### Migration Options

- **`--dry-run`**: Preview what will be migrated without writing any data
- **`--output PATH`**: Specify custom SQLite file path (default: `~/.bitcoinaccounting/ledger.db`)
- **`--force`**: Overwrite existing SQLite file if it exists

The migration tool copies all data from these tables:
- `ledger` (all transactions)
- `pair_price` (price history)
- `coins` (coin metadata)
- `wallets` (wallet information)

## Troubleshooting

### "Database is locked" (SQLite)

**Cause**: Another process is writing to the database.

**Solution**:
- SQLite allows multiple readers but only one writer at a time
- Wait for the other process to finish, or close it
- For concurrent access needs, consider PostgreSQL instead

### "Permission denied" on ~/.bitcoinaccounting/

**Cause**: The scripts can't create the database directory.

**Solution**:
```bash
# Create directory manually with correct permissions
mkdir -p ~/.bitcoinaccounting
chmod 755 ~/.bitcoinaccounting
```

### Migration Verification Steps

After migrating from PostgreSQL to SQLite, verify:

1. **Row counts match**:
   - The migration script reports row counts for each table
   - Ledger row count is most critical

2. **Balances match**:
   ```bash
   # Compare balances before and after
   src/scripts/balance
   ```

3. **Trade history matches**:
   ```bash
   # Spot-check trade history for a few coins
   src/scripts/trades BTC
   ```

4. **Cost basis matches**:
   ```bash
   # Verify cost basis calculations
   src/scripts/forecast_gains BTC
   ```

5. **Date ranges preserved**:
   - Check earliest and latest transaction dates match
   - Verify timestamps are formatted correctly (ISO 8601)

### Common Integrity Findings

**`one_sided_send` / `one_sided_receive` (transfer_integrity)**

**Cause**: A withdrawal in one wallet has no matching deposit in another wallet (or vice versa), usually because the receiving transaction wasn't imported yet.

**Resolution**:
1. Import the missing side: `import_csv --wallet-name DestWallet file.csv`
2. Ensure both wallets use matching coin/amount/date
3. Re-run `bitcoin-integrity` to verify the pair resolves

**`missing_cost` (basis_continuity)**

**Cause**: A transaction references a lot whose cost basis was never established — common when on-chain receives are imported without a paired buy record.

**Resolution**:
1. Find the originating purchase and add it: `buySats` or `import_csv`
2. If the asset was mined or gifted, record it with `earnInterest` (FMV at receipt)
3. Re-run `bitcoin-integrity --coin BTC` to confirm the finding clears

**`discrepancy` (reconciliation)**

**Cause**: The calculated ledger balance differs from the declared wallet balance. Often caused by an import gap, a rounding error, or an un-imported fee.

**Resolution**:
1. Compare with wallet export: `compare_with_sparrow` or `bitcoin-integrity --wallet WALLET_NAME --format json`
2. Check for missing fee records or duplicate rows in the ledger
3. Use `diagnose_balances` to isolate the calculation discrepancy

**Score below threshold (alert: `critical-score`)**

**Cause**: Accumulated unresolved findings have driven the health score below your configured minimum.

**Resolution**:
1. Run `bitcoin-integrity --format json --output report.json` for the full finding list
2. Prioritize `critical` severity findings first
3. Acknowledge known issues with `FindingTracker.acknowledge()` to keep noise low
4. After fixing root causes, re-run `bitcoin-integrity --persist` to record the improved score

### "No module named 'psycopg2'" when using SQLite

**Cause**: PostgreSQL driver is an optional dependency for SQLite-only users.

**Solution**:
- If using SQLite only, you can safely ignore this warning
- To suppress: `pip install psycopg2-binary` (even if not using PostgreSQL)

## Workflow

Add `src/scripts` to your PATH or run scripts directly with full path.

### Optional Web Dashboard Bitcoin Presence

If you run the private web app alongside a local `bitcoind`, the dashboard can show a compact **Bitcoin Presence** panel with current height, last block age, peer count, and mempool activity.

This integration is intentionally optional:

- If disabled, the panel does not appear.
- If enabled but RPC is unavailable, the rest of the dashboard still loads.
- Descriptor-based wallet balance verification uses Bitcoin Core for descriptor handling and an Electrum-compatible server for chain balances.
- Wallet detail also offers **Proof of Spend**: paste a finalized, signed transaction and Bitcoin Accounting calls Bitcoin Core's `testmempoolaccept` without broadcasting it.

Recommended environment variables:

```bash
BITCOIN_CHAIN_STATUS_ENABLED=1
BITCOIN_RPC_URL=http://127.0.0.1:8332
BITCOIN_RPC_COOKIE_FILE=/path/to/.cookie
BITCOIN_RPC_TIMEOUT_SECONDS=3
```

Cookie auth is preferred over storing explicit RPC usernames and passwords. If you do not use a cookie file, set both `BITCOIN_RPC_USER` and `BITCOIN_RPC_PASSWORD` instead.

The RPC URL and authentication are required for Proof of Spend even when the optional dashboard presence panel is disabled. Bitcoin Accounting never calls `sendrawtransaction` from this workflow and does not persist finalized transaction hex. It retains only the wallet association, acceptance verdict, transaction identifiers, fee/size metadata, rejection reason, and test time. A successful result proves that the submitted signed transaction satisfied the connected node's chain and mempool policy at that moment; it does not broadcast the transaction.

Refresh behavior:

- When the dashboard is open and node status is available, the panel refreshes about once per minute.
- When the node is unavailable, the UI backs off to a slower retry cadence.
- Stale or unavailable node data is shown as a degraded state inside the panel rather than as a fatal application error.

### Recording Transactions

- **Purchase BTC**: `buySats` - Records buy with automatic price lookup
- **Sell BTC**: `sell` - Records sale (try not to sell your bitcoin!)
- **Transfer between wallets**: `transfer` - Creates withdrawal + deposit pair
- **Interest/Staking income**: `earnInterest` - Records income with cost basis

### Importing from Exchanges and Wallets

Bulk-import transaction history from exchange CSV/xlsx exports and hardware wallet exports. **Fiat tracking** is automatically enabled: USD deposits/withdrawals and other fiat currencies are captured alongside BTC transactions for complete accounting.

- **Auto-detect and import**: `import_csv coinbase_export.csv`
- **Preview first**: `import_csv --dry-run coinbase_export.csv`
- **Specify parser**: `import_csv --source kraken ledger.csv`
- **Set withdrawal destination**: `import_csv --withdraw-to ColdCard file.csv`
- **List supported parsers**: `import_csv --list`
- **Show expected format**: `import_csv --format gemini`

**Exchanges**: Coinbase, Coinbase Pro, Kraken, Strike, River, Swan, Cash App, Gemini (CSV + native xlsx), and a Native pass-through format.

- **Fiat support**: Kraken, Strike, River, Swan, Gemini (xlsx), and Coinbase Pro automatically capture fiat deposits/withdrawals (USD, EUR, stablecoins)
- **BTC-only**: Cash App (gain/loss export) and standard Coinbase imports include BTC transactions only

**Wallets**: Ledger Live, Trezor Suite, Sparrow Wallet, Coldcard. Wallet imports require `--wallet-name` to identify the destination:

```bash
# Import Ledger Live export
import_csv --wallet-name MyLedger ledger_operations.csv

# Import with withdrawal destination
import_csv --wallet-name MyTrezor --withdraw-to ColdStorage trezor_export.csv
```

See [docs/CSV_FORMAT_GUIDE.md](docs/CSV_FORMAT_GUIDE.md) for per-parser export instructions and column details.

**Withdrawal handling**: Use `--withdraw-to` to set the destination wallet name
(e.g. `--withdraw-to ColdCard`). Without it, withdrawals are tagged with a
review comment so you can update them later.

### Checking Balances

- **Overall balances**: `balance` - Shows all coin balances
- **Per-wallet view**: `wallet_balances` - Balance breakdown by wallet
- **Transaction history**: `wallet_ledger WALLET_NAME` - Detailed ledger

### Tax and Reporting

- **Cost basis**: `forecast_gains` - Preview capital gains with FIFO/per-wallet
- **Realized gains**: `gains_tracker` - Review past sales and gains
- **1099-B export**: `export_1099b` - Generate tax report
- **Transaction export**: `export_tx` - CSV export with filtering
  - Filter by wallet: `export_tx output.csv --wallet Strike`
  - Filter by multiple wallets: `export_tx output.csv --wallets Strike,Coldcard,Vault`
  - Filter by date: `export_tx output.csv --start-date 2024-01-01 --end-date 2024-12-31`
  - Preview before export: `export_tx --wallet Coldcard --dry-run`
  - Combine filters: `export_tx output.csv --wallet Strike --coin BTC --start-date 2024-01-01`
  - Export wallet ecosystem: `export_tx custody.csv --wallets Strike,River,Coldcard`
  - Round-trip compatible with `import_csv --source native`

### Treasury Integrity

Run deterministic checks against your ledger at any time:

```bash
# Terminal summary (reconciliation + transfer pairs + cost basis + health score)
bitcoin-integrity

# Restrict to a single coin or wallet
bitcoin-integrity --coin BTC --wallet Strike

# Export full JSON report
bitcoin-integrity --format json --output report.json

# Export flat CSV of all findings
bitcoin-integrity --format csv --output findings.csv

# Persist the health score snapshot for trend tracking
bitcoin-integrity --persist

# Adjust tier thresholds (default: HEALTHY ≥ 80, WARNING ≥ 60)
bitcoin-integrity --warning-min 90 --critical-min 70
```

The command exits with a concise summary showing an overall health score (0–100), sub-scores for each check, top findings, and remediation counts. Use `--persist` to build a score history queryable via the TUI or the `integrity_health_snapshots` table directly.

### Monthly Treasury Attestation

The monthly attestation workflow produces a durable, reviewable evidence bundle for a calendar month. It composes integrity check results, finding metadata, and a deterministic run ID into JSON or CSV artifacts suitable for archival and audit.

**Step 1 — Run and persist the integrity check**

```bash
# Store a health snapshot for the period you want to attest
bitcoin-integrity --persist
```

**Step 2 — Generate an attestation bundle (Python API)**

```python
from db.backend import get_backend
from attestation.generator import AttestationGenerator

backend = get_backend()
gen = AttestationGenerator(backend)
bundle = gen.generate(year=2026, month=1)   # January 2026

# Export as JSON
print(gen.export_bundle_json(bundle))

# Export as CSV (one row per finding)
print(gen.export_bundle_csv(bundle))
```

The bundle includes:
- `metadata` — period label, run ID (deterministic UUID), generation timestamp
- `report` — full integrity report (health score, sub-scores, findings)
- `unresolved_findings` — flat list of unresolved findings for export

**Step 3 — Optional PDF summary**

```python
from attestation.reports import AttestationReportFormatter, PDFNotAvailableError
from pathlib import Path

formatter = AttestationReportFormatter(backend=backend)
try:
    out = formatter.generate_pdf(bundle, Path("attestation-2026-01.pdf"))
    print(f"PDF written to {out}")
except PDFNotAvailableError:
    print("Install reportlab for PDF output: pip install reportlab")
```

The PDF renders score trends, a top-findings summary, and a remediation checklist.

**Step 4 — Track finding lifecycle**

```python
from attestation.alerts import FindingTracker, FindingState

tracker = FindingTracker(backend)
tracker.sync_findings(bundle.unresolved_findings)

# Acknowledge a finding you are aware of
tracker.acknowledge(finding_id)

# Mark resolved once fixed
tracker.resolve(finding_id)

# Query by state
open_findings = tracker.load_all(state=FindingState.NEW)
```

**Step 5 — Configure alert rules**

```python
from attestation.alerts import AlertEngine, AlertRule

rules = [
    AlertRule("critical-score", score_below=60.0),
    AlertRule("critical-findings", severity="critical"),
    AlertRule("missing-cost", category="missing_cost"),
]
engine = AlertEngine(rules)
alerts = engine.evaluate(bundle)
print(engine.format_summary(alerts))
```

**Step 6 — Monitor from the TUI**

Open the TUI (`bitcoin-accounting`) and view the **Treasury Integrity** panel on the Dashboard. The panel shows the latest health score and recent deltas. Click **View Details →** to open the Attestation screen where you can:

- Filter findings by source or severity
- Export the current findings to JSON or CSV
- Acknowledge findings inline

> **Disclaimer**: Attestation bundles are operational evidence artifacts for internal audit and review. They are not formal legal, tax, or financial opinions.

### Data Validation

- **Balance verification**: `diagnose_balances` - Detect calculation issues
- **Transfer matching**: `validate_transfers` - Find mismatched transfers
- **Wallet reconciliation**: `compare_with_sparrow` - Compare with wallet export
- **Exchange liquidity**: `exchange_liquidity` - Where you have cost basis

For detailed script documentation and quick reference, see [SCRIPTS_UPDATE.md](SCRIPTS_UPDATE.md).

**2025+ Tax Compliance:**
- Starting tax year 2025, IRS Rev. Proc. 2024-28 requires per-wallet FIFO accounting
- All gain/forecast tools support `--wallet` parameter for per-wallet calculations
- Tools provide clear warnings when using global FIFO for 2025+ transactions

## Database Schema

### SQLite
- Schema is defined in `src/python/db/schema.py`
- Automatically created on first use (zero configuration)
- Core tables: `ledger`, `pair_price`, `coins`, `wallets`
- Query logic in `src/python/db/queries/` package

### PostgreSQL
- Tables defined in `src/sql/tables.sql`
- Must be manually applied (see Quick Start above)
- Query logic uses Python classes (same as SQLite)

### Core Tables (Both Backends)

- **`ledger`**: All transactions (trades, transfers, income)
- **`pair_price`**: Historical price data for cost-basis calculations
- **`coins`**: Coin metadata (optional)
- **`wallets`**: Wallet information (optional)
- **`integrity_health_snapshots`**: Treasury health score history (written by `bitcoin-integrity --persist`)

## Testing

Run the full test suite:

**Linux / macOS:**
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=src/python/db --cov-report=term-missing
```

**Windows (PowerShell):**
```powershell
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run with coverage
python -m pytest --cov=src\python\db --cov-report=term-missing
```

### Test Suite Coverage

**1,200+ tests passing** (PostgreSQL tests skipped when database unavailable)

- **Database abstraction layer** (`tests/test_db_backend.py`):
  - Backend interface (SQLite, PostgreSQL)
  - Query execution and result handling
  - Transaction commit/rollback
  - Error handling and exceptions

- **Query classes** (same file):
  - Price lookups with fuzzy date matching
  - Balance calculations (buys, sells, transfers)
  - Trade history with perspective logic
  - Cost basis calculations (weighted average)
  - Income tracking (interest, dividends)

- **Migration tools** (`tests/test_migration.py`):
  - PostgreSQL to SQLite data migration
  - Timestamp conversion
  - Row count verification
  - Dry-run mode

- **Integration tests** (`tests/test_1099b_export.py`, `tests/test_cli_scripts.py`):
  - Tax export (1099-B) with real data
  - CLI script compatibility (all 16 scripts)
  - End-to-end workflows
  - FIFO calculations

- **Import parsers** (`tests/test_import_*.py`):
  - 8 exchange parsers: Native, Coinbase, Kraken, Strike, River, Swan, Cash App, Gemini
  - 4 wallet parsers: Ledger Live, Trezor Suite, Sparrow Wallet, Coldcard
  - Per-parser detection, parsing, registration, and integration tests
  - Gemini dual-path: CSV and native xlsx formats

- **Legacy tests** (`tests/test_sqlite_integration.py`):
  - Balance calculation edge cases
  - Currency-specific filtering
  - Fee handling (tracked but not deducted)
  - Multi-currency isolation

**All tests use in-memory SQLite** - no database setup required for development.

**Type checking**:
```bash
mypy --strict src/python/db/
```

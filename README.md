# Crypto Accounting System

Lightweight bookkeeping and reporting for cryptocurrency with SQLite or PostgreSQL.

This repository contains Python helper scripts and database abstraction layer to
maintain a transaction ledger and produce balance, cost-basis reports, and
visualizations. The ledger is database-backed and primarily focused on Bitcoin,
with support for any cryptocurrency.

## Key Features
- **Zero-config SQLite option** - Start tracking immediately with no database setup
- **PostgreSQL support** - Use existing PostgreSQL infrastructure if preferred
- Store transactions (deposits, withdrawals, trades, mining/interest)
- Compute balances and cost-basis automatically
- CLI helpers for common operations (buy, sell, transfer, export)
- Tax reporting (1099-B exports, FIFO calculations)
- Lightweight visualization helpers and example notebook
- Bulk import from exchanges (Coinbase, Kraken, Strike, River, Swan, Cash App, Gemini) and wallets (Ledger, Trezor, Sparrow, Coldcard) with auto-detection

## Quick Start

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

The database file will be automatically created at `~/.cryptoaccounting/ledger.db` on first use.

### Option 2: PostgreSQL (For Advanced Users)

If you need multi-user access, network access, or have existing PostgreSQL infrastructure:

1. Create a PostgreSQL database and user:

```sql
-- Run in psql as a DB admin
CREATE DATABASE crypto;
CREATE USER bitcoin_accounting WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE crypto TO bitcoin_accounting;
```

2. Apply the schema:

```bash
# From the repository root - creates all 4 tables (coins, ledger, pair_price, wallets)
psql -U <db-admin> -d crypto -f src/sql/tables.sql
```

The `tables.sql` file creates all required tables:
- `coins` - Cryptocurrency metadata
- `ledger` - Transaction history (buys, sells, transfers, etc.)
- `pair_price` - Historical price data for cost basis calculations
- `wallets` - Wallet/account metadata (matches ledger.exchange field)

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
# PGUSER=bitcoin_accounting
# PGPASSWORD=your-secure-password
# PGDATABASE=crypto
```

The `.env` file is automatically loaded by all scripts and is in `.gitignore` to prevent accidental commits.

## Environment Variables

### Database Selection

- **`DB_BACKEND`**: Choose database backend
  - `sqlite` (default) - Local file-based database
  - `postgres` - PostgreSQL database

- **`SQLITE_DB_PATH`**: Path to SQLite database file
  - Default: `~/.cryptoaccounting/ledger.db`
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

**Performance note**: For typical personal cryptocurrency portfolios (< 100k transactions), SQLite and PostgreSQL perform identically. SQLite is actually faster for single-user workloads.

## Migrating from PostgreSQL to SQLite

If you're currently using PostgreSQL and want to switch to SQLite:

1. Run the migration script:

```bash
# Ensure PostgreSQL environment variables are set
export PGHOST=localhost
export PGUSER=bitcoin_accounting
export PGPASSWORD=your-password
export PGDATABASE=crypto

# Run migration (dry-run to preview)
src/scripts/migrate_to_sqlite --dry-run

# Run actual migration
src/scripts/migrate_to_sqlite --output ~/.cryptoaccounting/ledger.db
```

2. Verify the migration:

```bash
# Set SQLite as the backend
export DB_BACKEND=sqlite
export SQLITE_DB_PATH=~/.cryptoaccounting/ledger.db

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
export SQLITE_DB_PATH=~/.cryptoaccounting/ledger.db
```

### Migration Options

- **`--dry-run`**: Preview what will be migrated without writing any data
- **`--output PATH`**: Specify custom SQLite file path (default: `~/.cryptoaccounting/ledger.db`)
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

### "Permission denied" on ~/.cryptoaccounting/

**Cause**: The scripts can't create the database directory.

**Solution**:
```bash
# Create directory manually with correct permissions
mkdir -p ~/.cryptoaccounting
chmod 755 ~/.cryptoaccounting
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

### "No module named 'psycopg2'" when using SQLite

**Cause**: PostgreSQL driver is an optional dependency for SQLite-only users.

**Solution**:
- If using SQLite only, you can safely ignore this warning
- To suppress: `pip install psycopg2-binary` (even if not using PostgreSQL)

## Workflow

Add `src/scripts` to your PATH or run scripts directly with full path.

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
- **Transaction export**: `export_tx` - CSV export for external tools

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

**640+ tests passing** (PostgreSQL tests skipped when database unavailable)

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




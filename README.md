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

2. Apply the schema (tables and functions):

```bash
# From the repository root
psql -U <db-admin> -d crypto -f src/sql/tables.sql
psql -U <db-admin> -d crypto -f src/sql/functions.sql
```

3. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

4. Configure PostgreSQL connection via environment variables:

```bash
export DB_BACKEND=postgres
export PGHOST=localhost
export PGPORT=5432
export PGUSER=bitcoin_accounting
export PGPASSWORD=strong-password
export PGDATABASE=crypto
```

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
- Functions defined in `src/sql/functions.sql`
- Must be manually applied (see Quick Start above)
- Query logic uses stored procedures

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

**125+ tests passing** ✅ (PostgreSQL tests skipped when database unavailable)

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




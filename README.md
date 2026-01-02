# Crypto Accounting system

Lightweight bookkeeping and reporting for cryptocurrency (Postgres-first).

This repository contains Python helper scripts, SQL schema and functions used to
maintain a transaction ledger in Postgres and produce simple balance / cost-basis
reports and visualizations. The current workflow is Postgres-first (the
database is the authoritative ledger) and primarily focused on Bitcoin.

Key features
- Store transactions (deposits, withdrawals, trades, mining/interest) in Postgres
- Compute balances and cost-basis using Postgres functions
- Small Python CLI helpers for common operations (buy, sell, transfer, export)
- Lightweight visualization helpers and an example notebook

Quick start (developer)

1. Create a Postgres database and a user for the project. Example:

```powershell
# Create DB and user (run in psql / as a DB admin)
CREATE DATABASE crypto;
CREATE USER bitcoin_accounting WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE crypto TO bitcoin_accounting;
```

2. Apply the table and function definitions in `src/sql/` to your database:

```powershell
# from the repository root
psql -U <db-admin> -d crypto -f src/sql/tables.sql
psql -U <db-admin> -d crypto -f src/sql/functions.sql
```

3. Install Python dependencies (see `requirements.txt`):

```powershell
python -m pip install -r requirements.txt
```

4. Configure the DB connection used by the scripts. Two options:

- Edit `src/python/config.py` and update details to match your host/user/password/database.

Workflow (how I use it locally)
- Copy the repo to target machine and add the src/scripts folder to your path or run directly. These scripts have a bootstrap loader and nicely wrap the primary logic.
- When you purchase BTC, run the `buySats` script which will insert a `Trade`/`Deposit` (or appropriate) row into the `ledger` table. 'sell' does the opposite (try not to sell your bitcoin!)
- When moving BTC between wallets, run the `transfer` script which inserts a withdrawal + deposit pair to reflect the transfer.
- To check balances and basic cost-basis, use `wallet_balances`, `gains_tracker`, or `forecast_gains` scripts.
- For detailed transaction history, use `wallet_ledger WALLET_NAME`.
- To validate data integrity, use `diagnose_balances`, `validate_transfers`, or `compare_with_sparrow`.
- To analyze where you have cost basis for selling, use `exchange_liquidity`.

For detailed script documentation and quick reference, see [SCRIPTS_UPDATE.md](SCRIPTS_UPDATE.md).

**2025+ Tax Compliance:**
- Starting tax year 2025, IRS Rev. Proc. 2024-28 requires per-wallet FIFO accounting
- All gain/forecast tools support `--wallet` parameter for per-wallet calculations
- Tools provide clear warnings when using global FIFO for 2025+ transactions

Notes about the schema
- Tables are defined in `src/sql/tables.sql` (notably `ledger` and `pair_price`).
- Key Postgres functions are in `src/sql/functions.sql` and include `get_trades`, `get_trade_cost_new`, `get_price`, and `get_avg_purchase_price(_new)` — these compute cost details basis using the ledger and pair_price tables.

Testing
- Run the full test suite using the appropriate test runner for your OS:

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File run_tests.ps1 -Verbose
```

**Linux / macOS (Bash):**
```bash
chmod +x run_tests.sh
./run_tests.sh -v
```

- Tests use in-memory SQLite to validate core ledger and balance logic without requiring a live Postgres instance.
- **All 15 unit tests passing** ✅
- Current test coverage:
  - Balance calculation (buys, sells, fees)
  - Currency-specific balance filtering
  - Average purchase price / cost-basis
  - Transfers with fees (withdrawal + deposit pairs)
  - Fee handling (tracking only, not subtracted from balances)
  - Price lookups and fiat conversions
  - Multi-currency isolation
- Both runners support verbose output (`-v` or `-Verbose`) and coverage reports (`-c` or `-Coverage`).




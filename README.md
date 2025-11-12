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

- Quick and dirty: edit `src/python/cryptoAccounts.py` and `src/python/cryptoViz.py` and update the psycopg2.connect(...) calls to match your host/user/password/database.
- Recommended: refactor the connection code to read from environment variables (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE) or a small `config.py` to avoid embedding secrets in source.

Workflow (how I use it locally)
- Copy the small wrapper scripts (the files in `scripts/`) to `~/bin` on your local machine or node. Make them executable.
- When you purchase BTC, run the `buySats` script which will insert a `Trade`/`Deposit` (or appropriate) row into the `ledger` table.
- When moving BTC between wallets, run the `transfer` script which inserts a withdrawal + deposit pair to reflect the transfer.
- To check balances and basic cost-basis, use the Python helpers (or the `balance` script) which call the database functions `get_balance`, `get_avg_purchase_price`, and the `get_trade_cost_new` reporting functions.

For detailed instructions on how to deploy scripts to `~/bin` and establish the Python module path, see [SCRIPTS_DEPLOYMENT.md](SCRIPTS_DEPLOYMENT.md).

Notes about the schema
- Tables are defined in `src/sql/tables.sql` (notably `ledger` and `pair_price`).
- Key Postgres functions are in `src/sql/functions.sql` and include `get_balance`, `get_trades`, `get_trade_cost_new`, `get_price`, and `get_avg_purchase_price(_new)` — these compute balances and cost-basis using the ledger and pair_price tables.

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
- Current test coverage:
  - Balance calculation (buys, sells, fees)
  - Average purchase price / cost-basis
  - Transfers with fees (withdrawal + deposit pairs)
  - Price lookups and fiat conversions
  - Multi-currency isolation
- Both runners support verbose output (`-v` or `-Verbose`) and coverage reports (`-c` or `-Coverage`).

Recommended next steps
- Replace hard-coded DB connection strings in Python with environment-driven configuration.
- If you want a dedicated Bitcoin-only ledger, decide whether you want a UTXO-level model (more precise) or a simpler account-based model. I can propose a minimal UTXO schema and migration steps.
- Add a tiny `requirements.txt` and a short developer README (this file) is already updated.

If you'd like, I can:
- summarize the current Postgres schema in more detail,
- propose and create a minimal Bitcoin-only schema and migration SQL,
- or update the Python code to use environment variables for DB connections.



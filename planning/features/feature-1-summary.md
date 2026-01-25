# Feature 1: SQLite Database Backend

**Status**: Planned
**Branch**: `feature/sqlite-database-backend`
**Stories**: SQL-001 through SQL-012 (12 stories)

## Summary

Add SQLite as an embedded database option, eliminating the PostgreSQL dependency for typical users while maintaining full backward compatibility.

### Goals
- Zero external dependencies for new users (SQLite is Python stdlib)
- Existing PostgreSQL users unaffected
- Identical functionality regardless of backend
- Easy migration path from PostgreSQL to SQLite

## File Structure

New `src/python/db/` package organization:

```
src/python/
├── __init__.py                  # NEW: Package marker
├── config.py                    # MODIFIED: Add get_backend() factory
├── cryptoAccounts.py            # MODIFIED: Use db layer
├── cryptoViz.py                 # UNCHANGED
└── db/
    ├── __init__.py              # Exports: DatabaseBackend, get_backend()
    ├── backend.py               # Abstract base class
    ├── exceptions.py            # DatabaseError exception
    ├── postgres.py              # PostgresBackend (wraps psycopg2)
    ├── sqlite.py                # SqliteBackend (wraps sqlite3)
    ├── schema.py                # DDL for all tables
    ├── migration.py             # PostgreSQL → SQLite migration
    └── queries/
        ├── __init__.py
        ├── price.py             # PriceLookup class
        ├── balance.py           # BalanceCalculator class
        ├── trades.py            # TradeQuery class
        ├── income.py            # IncomeQuery class
        └── basis.py             # BasisCalculator class

tests/
├── test_sqlite_integration.py   # EXISTING: Expand with new tests
├── test_1099b_export.py         # EXISTING
├── test_db_backend.py           # NEW: Backend abstraction tests
├── test_queries.py              # NEW: Query class tests
├── test_migration.py            # NEW: Migration tool tests
└── conftest.py                  # NEW: Shared fixtures
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Placeholder syntax** | `:named` params | Both sqlite3 and psycopg2 support `:name` style. Avoids `%s` vs `?` problem. |
| **Return types** | `List[dict]` | Dictionaries preserve column names, are JSON-serializable, simple to use. |
| **NULL handling** | Python `None` | Both backends map NULL→None. Return None (not 0) for missing data. |
| **Timestamps** | ISO 8601 strings | SQLite has no datetime type. ISO 8601 sorts correctly. |
| **Transactions** | Explicit commit | No autocommit. Caller must call `backend.commit()`. |
| **Errors** | `DatabaseError` | Unified exception wraps psycopg2.Error and sqlite3.Error. |

## Backend Interface

```python
class DatabaseBackend(ABC):
    def execute(query: str, params: dict = None) -> List[dict]: ...
    def execute_one(query: str, params: dict = None) -> dict | None: ...
    def execute_scalar(query: str, params: dict = None) -> Any: ...
    def commit() -> None: ...
    def rollback() -> None: ...
    def close() -> None: ...
```

## Story Breakdown

| ID | Title | Risk | Key Deliverable |
|----|-------|------|-----------------|
| SQL-001 | Database abstraction layer | Medium | `db/backend.py`, `db/sqlite.py`, `db/postgres.py` |
| SQL-002 | SQLite schema creation | Low | `db/schema.py`, auto-init on first use |
| SQL-003 | Port get_price() | **High** | `db/queries/price.py` - fuzzy date matching |
| SQL-004 | Port balance functions | Low | `db/queries/balance.py` |
| SQL-005 | Port get_trades() | Medium | `db/queries/trades.py` |
| SQL-006 | Port get_trade_cost_new() | Medium | Extends `TradeQuery` class |
| SQL-007 | Port avg_purchase_price | Low | `db/queries/basis.py` |
| SQL-008 | Port income functions | Medium | `db/queries/income.py` |
| SQL-009 | Refactor CryptoAccounts | **High** | Convert all queries, swap to backend |
| SQL-010 | Migration tool | Medium | `db/migration.py`, CLI script |
| SQL-011 | CLI scripts verification | Low | Test all 16 scripts |
| SQL-012 | Documentation | Low | README updates |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_BACKEND` | `sqlite` | Backend: `sqlite` or `postgres` |
| `SQLITE_DB_PATH` | `~/.cryptoaccounting/ledger.db` | SQLite file location |
| `PGHOST` | (existing) | PostgreSQL host |
| `PGPORT` | (existing) | PostgreSQL port |
| `PGUSER` | (existing) | PostgreSQL user |
| `PGPASSWORD` | (existing) | PostgreSQL password |
| `PGDATABASE` | (existing) | PostgreSQL database |

## CLI Scripts (16 total)

All scripts verified in SQL-011:

| Script | Purpose |
|--------|---------|
| `balance` | Show coin balances |
| `buySats` | Record BTC purchase |
| `compare_with_sparrow` | Reconcile with wallet export |
| `diagnose_balances` | Validate balance calculations |
| `earnInterest` | Record interest income |
| `exchange_liquidity` | Show per-exchange holdings |
| `export_1099b` | Generate tax report |
| `export_tx` | Export transactions to CSV |
| `forecast_gains` | Project capital gains |
| `gains_tracker` | Review realized gains |
| `sell` | Record sale transaction |
| `trades` | Display trade history |
| `transfer` | Move funds between wallets |
| `validate_transfers` | Check transfer pairs match |
| `wallet_balances` | Per-wallet balance view |
| `wallet_ledger` | Transaction history for wallet |

## Testing Strategy

**PostgreSQL is NOT required for development or testing.**

- All new code testable with SQLite only (in-memory `:memory:` databases)
- PostgreSQL comparison tests are optional, skipped when `PGHOST` not set
- Existing 15 SQLite tests validate the refactored CryptoAccounts
- Target: 90%+ coverage on new code

## Type Mappings

| PostgreSQL | SQLite |
|------------|--------|
| `SERIAL4` | `INTEGER PRIMARY KEY` |
| `VARCHAR(n)` | `TEXT` |
| `FLOAT8` | `REAL` |
| `TIMESTAMP` | `TEXT` (ISO 8601) |

## Date Function Mappings

| PostgreSQL | SQLite |
|------------|--------|
| `date_trunc('day', ts)` | `date(ts)` |
| `EXTRACT('year' FROM ts)` | `CAST(strftime('%Y', ts) AS INTEGER)` |
| `DATE_PART('minute', ts)` | `CAST(strftime('%M', ts) AS INTEGER)` |
| `now()` | `datetime('now')` |

## Risk Areas

**High Risk:**
- `get_price()` fuzzy date matching - core to all cost basis calculations
- `CryptoAccounts` refactor (SQL-009) - central class, touches everything

**Mitigations:**
- Existing 15 SQLite tests catch regressions
- Incremental query conversion in SQL-009
- Dependency injection enables isolated unit testing

## Files

- PRD: [feature-1-prd.json](feature-1-prd.json)
- Progress: (created when work begins)

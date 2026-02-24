"""Database schema definitions for SQLite and PostgreSQL."""

from __future__ import annotations

import os

from .backend import DatabaseBackend


# SQLite DDL for all tables
# Type mappings from PostgreSQL:
#   SERIAL4 -> INTEGER PRIMARY KEY (auto-increments automatically)
#   VARCHAR(n) -> TEXT
#   FLOAT8/NUMERIC/DOUBLE PRECISION -> REAL
#   TIMESTAMP -> TEXT (ISO 8601 format)
#   BOOLEAN -> INTEGER (0/1)

LEDGER_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY,
    createddate TEXT NOT NULL,
    trans_type TEXT,
    buy REAL,
    buy_curr TEXT,
    sell REAL,
    sell_curr TEXT,
    fee REAL,
    fee_curr TEXT,
    exchange TEXT,
    "group" TEXT,
    comment TEXT,
    transactionid TEXT,
    deleted INTEGER DEFAULT 0,
    deleted_date TEXT
)
"""

PAIR_PRICE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS pair_price (
    to_curr TEXT NOT NULL,
    price REAL NOT NULL,
    from_curr TEXT NOT NULL,
    date TEXT
)
"""

COINS_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS coins (
    name TEXT PRIMARY KEY,
    max_supply INTEGER,
    circ_supply INTEGER
)
"""

WALLETS_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS wallets (
    wallet_id TEXT PRIMARY KEY,
    wallet_type TEXT NOT NULL,
    custody TEXT NOT NULL,
    description TEXT,
    seed_info TEXT,
    active INTEGER DEFAULT 1,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
)
"""

# List of all table creation statements in dependency order
SQLITE_TABLES = [
    LEDGER_TABLE_SQLITE,
    PAIR_PRICE_TABLE_SQLITE,
    COINS_TABLE_SQLITE,
    WALLETS_TABLE_SQLITE,
]


def get_sqlite_path() -> str:
    """Get the path to the SQLite database file.

    Returns:
        Path from SQLITE_DB_PATH environment variable or default
        ~/.bitcoinaccounting/ledger.db.
    """
    env_path = os.getenv('SQLITE_DB_PATH')
    if env_path:
        return env_path

    return os.path.expanduser('~/.bitcoinaccounting/ledger.db')


def _migrate_ledger_soft_delete(backend: DatabaseBackend) -> None:
    """Add soft-delete columns to existing ledger tables.

    This migration is idempotent - ALTER TABLE will be skipped if columns
    already exist. Handles existing databases that were created before
    the soft-delete feature was added.

    Args:
        backend: DatabaseBackend instance to execute DDL on
    """
    # SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS,
    # so we check existing columns first via PRAGMA
    from .sqlite import SqliteBackend
    if isinstance(backend, SqliteBackend):
        rows = backend.execute("PRAGMA table_info(ledger)")
        existing_cols = {row['name'] for row in rows}

        if 'deleted' not in existing_cols:
            backend.execute("ALTER TABLE ledger ADD COLUMN deleted INTEGER DEFAULT 0")
        if 'deleted_date' not in existing_cols:
            backend.execute("ALTER TABLE ledger ADD COLUMN deleted_date TEXT")
    else:
        # PostgreSQL: use IF NOT EXISTS (supported in PG 9.6+)
        backend.execute("ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted INTEGER DEFAULT 0")
        backend.execute("ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted_date TEXT")


def create_tables(backend: DatabaseBackend) -> None:
    """Create all tables if they don't exist.

    This function is idempotent - it can be called multiple times safely.

    Args:
        backend: DatabaseBackend instance to execute DDL on
    """
    for table_ddl in SQLITE_TABLES:
        backend.execute(table_ddl)
    # Migrate existing ledger tables to add soft-delete columns
    _migrate_ledger_soft_delete(backend)
    backend.commit()

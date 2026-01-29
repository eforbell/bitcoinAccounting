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
    transactionid TEXT
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
        ~/.cryptoaccounting/ledger.db
    """
    return os.getenv('SQLITE_DB_PATH', os.path.expanduser('~/.cryptoaccounting/ledger.db'))


def create_tables(backend: DatabaseBackend) -> None:
    """Create all tables if they don't exist.

    This function is idempotent - it can be called multiple times safely.

    Args:
        backend: DatabaseBackend instance to execute DDL on
    """
    for table_ddl in SQLITE_TABLES:
        backend.execute(table_ddl)
    backend.commit()

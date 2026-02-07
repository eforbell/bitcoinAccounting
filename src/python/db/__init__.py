"""Database abstraction layer for CryptoAccounting.

Supports multiple database backends (SQLite, PostgreSQL) with a unified interface.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Look for .env in repository root (3 levels up from this file)
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed

from .backend import DatabaseBackend
from .exceptions import DatabaseError
from .migration import (
    MigrationResult,
    convert_timestamp_to_iso8601,
    migrate_postgres_to_sqlite,
)
from .postgres import PostgresBackend
from .queries.balance import BalanceCalculator
from .queries.basis import BasisCalculator
from .queries.capital_gains import CapitalGainCalculator
from .queries.income import IncomeQuery
from .queries.ledger import LedgerWriter
from .queries.price import PriceLookup
from .queries.trades import TradeQuery
from .queries.transaction import TransactionQuery
from .schema import create_tables, get_sqlite_path
from .sqlite import SqliteBackend


def get_backend(backend_type: str | None = None) -> DatabaseBackend:
    """Factory function to create database backend instances.

    Args:
        backend_type: Backend type ('sqlite' or 'postgres').
                     If None, reads DB_BACKEND environment variable.
                     Defaults to 'sqlite' if not set.

    Returns:
        DatabaseBackend instance

    Raises:
        ValueError: If backend_type is not 'sqlite' or 'postgres'
    """
    if backend_type is None:
        backend_type = os.getenv('DB_BACKEND', 'sqlite')

    backend_type = backend_type.lower()

    if backend_type == 'sqlite':
        return SqliteBackend()
    elif backend_type == 'postgres':
        return PostgresBackend()
    else:
        raise ValueError(f"Unknown backend type: {backend_type}. Must be 'sqlite' or 'postgres'.")


__all__ = [
    'DatabaseBackend',
    'DatabaseError',
    'SqliteBackend',
    'PostgresBackend',
    'get_backend',
    'create_tables',
    'get_sqlite_path',
    'BalanceCalculator',
    'BasisCalculator',
    'CapitalGainCalculator',
    'IncomeQuery',
    'LedgerWriter',
    'PriceLookup',
    'TradeQuery',
    'TransactionQuery',
    'MigrationResult',
    'convert_timestamp_to_iso8601',
    'migrate_postgres_to_sqlite',
]

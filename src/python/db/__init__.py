"""Database abstraction layer for CryptoAccounting.

Supports multiple database backends (SQLite, PostgreSQL) with a unified interface.
"""

from __future__ import annotations

import os

from .backend import DatabaseBackend
from .exceptions import DatabaseError
from .postgres import PostgresBackend
from .queries.balance import BalanceCalculator
from .queries.price import PriceLookup
from .queries.trades import TradeQuery
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
    'PriceLookup',
    'TradeQuery',
]

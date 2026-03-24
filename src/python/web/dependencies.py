"""FastAPI dependency helpers for request-scoped resources."""

from __future__ import annotations

from collections.abc import Generator

from bitcoinAccounts import BitcoinAccounts
from db import DatabaseBackend, get_backend


def get_request_backend() -> Generator[DatabaseBackend, None, None]:
    """Yield a fresh backend for one request and close it afterward.

    This avoids sharing one long-lived app-global database connection across
    concurrent web requests.
    """
    backend = get_backend()
    try:
        yield backend
    finally:
        backend.close()


def get_request_accounts() -> Generator[BitcoinAccounts, None, None]:
    """Yield a fresh BitcoinAccounts service object for one request."""
    backend = get_backend()
    accounts = BitcoinAccounts(backend=backend)
    try:
        yield accounts
    finally:
        accounts.close()

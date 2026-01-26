"""SQLite database backend implementation."""

from __future__ import annotations

import sqlite3
from typing import Any

from .backend import DatabaseBackend
from .exceptions import DatabaseError


class SqliteBackend(DatabaseBackend):
    """SQLite database backend.

    Uses sqlite3 from Python standard library. Supports both file-based
    and in-memory (':memory:') databases. Automatically creates schema
    tables on initialization.
    """

    def __init__(self, db_path: str | None = None, auto_create_tables: bool = True) -> None:
        """Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database file. If None, uses default
                    from get_sqlite_path(). Use ':memory:' for in-memory
                    database (tests).
            auto_create_tables: If True, automatically create schema tables.
                               Set to False in tests that create their own schema.
        """
        if db_path is None:
            from .schema import get_sqlite_path
            db_path = get_sqlite_path()

        self.db_path = db_path

        # Create parent directory if needed (not for :memory:)
        if db_path != ':memory:':
            import os
            parent_dir = os.path.dirname(db_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

        try:
            self.connection = sqlite3.connect(db_path)
            self.connection.row_factory = sqlite3.Row  # Enable column access by name
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to SQLite database at {db_path}: {e}") from e

        # Automatically create tables if requested
        if auto_create_tables:
            from .schema import create_tables
            create_tables(self)

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all results as list of dictionaries.

        Args:
            query: SQL query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            List of row dictionaries with column names as keys

        Raises:
            DatabaseError: On any database error
        """
        if params is None:
            params = {}

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert sqlite3.Row objects to dictionaries
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}") from e

    def execute_one(self, query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Execute a query and return first result or None.

        Args:
            query: SQL query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            Single row dictionary or None if no results

        Raises:
            DatabaseError: On any database error
        """
        if params is None:
            params = {}

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}") from e

    def execute_scalar(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a query and return first column of first row.

        Args:
            query: SQL query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            Scalar value from first column of first row, or None if no results

        Raises:
            DatabaseError: On any database error
        """
        row = self.execute_one(query, params)
        if row is None:
            return None
        # Get first value from the dictionary
        return next(iter(row.values())) if row else None

    def commit(self) -> None:
        """Commit the current transaction.

        Raises:
            DatabaseError: On commit failure
        """
        try:
            self.connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Commit failed: {e}") from e

    def rollback(self) -> None:
        """Rollback the current transaction.

        Raises:
            DatabaseError: On rollback failure
        """
        try:
            self.connection.rollback()
        except sqlite3.Error as e:
            raise DatabaseError(f"Rollback failed: {e}") from e

    def close(self) -> None:
        """Close the database connection.

        Raises:
            DatabaseError: On close failure
        """
        try:
            self.connection.close()
        except sqlite3.Error as e:
            raise DatabaseError(f"Close failed: {e}") from e

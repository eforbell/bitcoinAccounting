"""PostgreSQL database backend implementation."""

from __future__ import annotations

import os
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg2
    import psycopg2.extras
else:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        psycopg2 = None  # type: ignore[assignment]

from .backend import DatabaseBackend
from .exceptions import DatabaseError


def _convert_named_params(query: str) -> str:
    """Convert :named placeholders to %(name)s format for psycopg2.

    Args:
        query: SQL query with :named placeholders

    Returns:
        Query with %(name)s placeholders
    """
    import re
    # Match :name but not ::cast (PostgreSQL cast syntax)
    return re.sub(r'(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)', r'%(\1)s', query)


class PostgresBackend(DatabaseBackend):
    """PostgreSQL database backend.

    Uses psycopg2 library. Connection parameters are read from environment
    variables: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE, PGSSLMODE.
    """

    def __init__(self) -> None:
        """Initialize PostgreSQL backend using environment variables."""
        if psycopg2 is None:
            raise DatabaseError(
                "psycopg2 is not installed. Install with: pip install psycopg2-binary"
            )

        params: dict[str, Any] = {
            'host': os.getenv('PGHOST', '192.0.2.10'),
            'port': os.getenv('PGPORT', '5432'),
            'user': os.getenv('PGUSER', 'bitcoin_accounting'),
            'password': os.getenv('PGPASSWORD', 'REDACTED-ROTATED'),
            'database': os.getenv('PGDATABASE', 'postgres'),
            'connect_timeout': 5
        }

        sslmode = os.getenv('PGSSLMODE')
        if sslmode:
            params['sslmode'] = sslmode

        try:
            self.connection = psycopg2.connect(**params)
        except psycopg2.Error as e:
            raise DatabaseError(f"Failed to connect to PostgreSQL: {e}") from e

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
            cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(_convert_named_params(query), params)
            # Check if query returns results (SELECT) vs no results (INSERT/UPDATE/DELETE)
            if cursor.description is None:
                return []
            rows = cursor.fetchall()
            # Convert RealDictRow objects to regular dictionaries
            return [dict(row) for row in rows]
        except psycopg2.Error as e:
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
            cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(_convert_named_params(query), params)
            # Check if query returns results (SELECT) vs no results (INSERT/UPDATE/DELETE)
            if cursor.description is None:
                return None
            row = cursor.fetchone()
            return dict(row) if row else None
        except psycopg2.Error as e:
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
        except psycopg2.Error as e:
            raise DatabaseError(f"Commit failed: {e}") from e

    def rollback(self) -> None:
        """Rollback the current transaction.

        Raises:
            DatabaseError: On rollback failure
        """
        try:
            self.connection.rollback()
        except psycopg2.Error as e:
            raise DatabaseError(f"Rollback failed: {e}") from e

    def close(self) -> None:
        """Close the database connection.

        Raises:
            DatabaseError: On close failure
        """
        try:
            self.connection.close()
        except psycopg2.Error as e:
            raise DatabaseError(f"Close failed: {e}") from e

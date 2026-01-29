"""Abstract database backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatabaseBackend(ABC):
    """Abstract base class for database backends.

    Provides a unified interface for executing queries and managing
    transactions across different database systems (SQLite, PostgreSQL).

    All query results are returned as dictionaries with column names as keys.
    All queries use :named placeholder syntax for parameters.
    """

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction.

        Raises:
            DatabaseError: On commit failure
        """
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction.

        Raises:
            DatabaseError: On rollback failure
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the database connection.

        Raises:
            DatabaseError: On close failure
        """
        pass

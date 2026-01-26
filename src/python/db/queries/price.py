"""Price lookup queries for pair_price table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backend import DatabaseBackend
    from ..sqlite import SqliteBackend
    from ..postgres import PostgresBackend


class PriceLookup:
    """Query class for looking up cryptocurrency prices from pair_price table.

    Implements fuzzy date matching algorithm that finds the closest price
    on the same calendar day as the requested timestamp.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Initialize PriceLookup with a database backend.

        Args:
            backend: DatabaseBackend instance (SqliteBackend or PostgresBackend)
        """
        self.backend = backend

    def get_price(
        self,
        from_coin: str,
        to_coin: str = 'USD',
        price_date: str | None = None
    ) -> float | None:
        """Get price for a currency pair on a specific date.

        Uses fuzzy matching: if exact timestamp not found, returns the price
        from the same calendar day with the smallest time difference.

        Args:
            from_coin: Source currency code (e.g., 'BTC')
            to_coin: Target currency code (default: 'USD')
            price_date: ISO 8601 timestamp string 'YYYY-MM-DD HH:MM:SS'.
                       If None, uses current datetime.

        Returns:
            Price as float, or None if no price found on that day
        """
        if price_date is None:
            price_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Determine which SQL dialect to use
        from ..sqlite import SqliteBackend

        if isinstance(self.backend, SqliteBackend):
            query = self._get_price_query_sqlite()
        else:
            query = self._get_price_query_postgres()

        result = self.backend.execute_scalar(
            query,
            {
                'from_coin': from_coin,
                'to_coin': to_coin,
                'price_date': price_date
            }
        )

        return float(result) if result is not None else None

    def get_price_date(
        self,
        from_coin: str,
        to_coin: str = 'USD',
        price_date: str | None = None
    ) -> str | None:
        """Get the actual timestamp of the price used for a currency pair.

        Returns the date field from the pair_price row that would be selected
        by get_price(). Useful for auditing which price was actually used.

        Args:
            from_coin: Source currency code (e.g., 'BTC')
            to_coin: Target currency code (default: 'USD')
            price_date: ISO 8601 timestamp string 'YYYY-MM-DD HH:MM:SS'.
                       If None, uses current datetime.

        Returns:
            ISO 8601 timestamp string of the matched price, or None if no match
        """
        if price_date is None:
            price_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Determine which SQL dialect to use
        from ..sqlite import SqliteBackend

        if isinstance(self.backend, SqliteBackend):
            query = self._get_price_date_query_sqlite()
        else:
            query = self._get_price_date_query_postgres()

        result = self.backend.execute_scalar(
            query,
            {
                'from_coin': from_coin,
                'to_coin': to_coin,
                'price_date': price_date
            }
        )

        return str(result) if result is not None else None

    def _get_price_query_sqlite(self) -> str:
        """Generate SQLite-specific price query."""
        return """
            SELECT price FROM pair_price
            WHERE from_curr = :from_coin
                AND to_curr = :to_coin
                AND CAST(strftime('%Y', date) AS INTEGER) = CAST(strftime('%Y', :price_date) AS INTEGER)
                AND CAST(strftime('%m', date) AS INTEGER) = CAST(strftime('%m', :price_date) AS INTEGER)
                AND CAST(strftime('%d', date) AS INTEGER) = CAST(strftime('%d', :price_date) AS INTEGER)
            ORDER BY ABS((julianday(date) - julianday(:price_date)) * 1440)
            LIMIT 1
        """

    def _get_price_date_query_sqlite(self) -> str:
        """Generate SQLite-specific price date query."""
        return """
            SELECT date FROM pair_price
            WHERE from_curr = :from_coin
                AND to_curr = :to_coin
                AND CAST(strftime('%Y', date) AS INTEGER) = CAST(strftime('%Y', :price_date) AS INTEGER)
                AND CAST(strftime('%m', date) AS INTEGER) = CAST(strftime('%m', :price_date) AS INTEGER)
                AND CAST(strftime('%d', date) AS INTEGER) = CAST(strftime('%d', :price_date) AS INTEGER)
            ORDER BY ABS((julianday(date) - julianday(:price_date)) * 1440)
            LIMIT 1
        """

    def _get_price_query_postgres(self) -> str:
        """Generate PostgreSQL-specific price query."""
        return """
            SELECT price FROM pair_price
            WHERE from_curr = :from_coin
                AND to_curr = :to_coin
                AND EXTRACT('year' FROM date) = EXTRACT('year' FROM CAST(:price_date AS TIMESTAMP))
                AND EXTRACT('month' FROM date) = EXTRACT('month' FROM CAST(:price_date AS TIMESTAMP))
                AND EXTRACT('day' FROM date) = EXTRACT('day' FROM CAST(:price_date AS TIMESTAMP))
            ORDER BY ABS((DATE_PART('day', date - CAST(:price_date AS TIMESTAMP)) * 24 +
                          DATE_PART('hour', date - CAST(:price_date AS TIMESTAMP))) * 60 +
                          DATE_PART('minute', date - CAST(:price_date AS TIMESTAMP)))
            LIMIT 1
        """

    def _get_price_date_query_postgres(self) -> str:
        """Generate PostgreSQL-specific price date query."""
        return """
            SELECT date FROM pair_price
            WHERE from_curr = :from_coin
                AND to_curr = :to_coin
                AND EXTRACT('year' FROM date) = EXTRACT('year' FROM CAST(:price_date AS TIMESTAMP))
                AND EXTRACT('month' FROM date) = EXTRACT('month' FROM CAST(:price_date AS TIMESTAMP))
                AND EXTRACT('day' FROM date) = EXTRACT('day' FROM CAST(:price_date AS TIMESTAMP))
            ORDER BY ABS((DATE_PART('day', date - CAST(:price_date AS TIMESTAMP)) * 24 +
                          DATE_PART('hour', date - CAST(:price_date AS TIMESTAMP))) * 60 +
                          DATE_PART('minute', date - CAST(:price_date AS TIMESTAMP)))
            LIMIT 1
        """

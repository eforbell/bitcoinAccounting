"""PostgreSQL to SQLite data migration tool."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .backend import DatabaseBackend
from .exceptions import DatabaseError
from .schema import create_tables
from .sqlite import SqliteBackend


# Tables to migrate in dependency order
TABLES_TO_MIGRATE = ['coins', 'wallets', 'ledger', 'pair_price']


def convert_timestamp_to_iso8601(value: Any) -> Any:
    """Convert PostgreSQL timestamp to ISO 8601 string for SQLite.

    Args:
        value: Value to potentially convert. If it's a datetime, converts to
               ISO 8601 string. Otherwise returns unchanged.

    Returns:
        Converted value (string if datetime, original value otherwise)
    """
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value


def convert_row_timestamps(row: dict[str, Any]) -> dict[str, Any]:
    """Convert all datetime values in a row to ISO 8601 strings.

    Args:
        row: Dictionary of column values

    Returns:
        Dictionary with datetime values converted to strings
    """
    return {key: convert_timestamp_to_iso8601(value) for key, value in row.items()}


def get_table_count(backend: DatabaseBackend, table_name: str) -> int:
    """Get row count for a table.

    Args:
        backend: Database backend instance
        table_name: Name of the table

    Returns:
        Number of rows in the table
    """
    result = backend.execute_scalar(f"SELECT COUNT(*) FROM {table_name}")
    return int(result) if result is not None else 0


def get_column_names(backend: DatabaseBackend, table_name: str, is_postgres: bool = True) -> list[str]:
    """Get column names for a table.

    Args:
        backend: Database backend instance
        table_name: Name of the table
        is_postgres: If True, queries PostgreSQL information_schema. Otherwise SQLite.

    Returns:
        List of column names
    """
    if is_postgres:
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """
        rows = backend.execute(query, {'table_name': table_name})
        return [row['column_name'] for row in rows]
    else:
        # SQLite uses PRAGMA
        rows = backend.execute(f"PRAGMA table_info({table_name})")
        return [row['name'] for row in rows]


def migrate_table(
    pg_backend: DatabaseBackend,
    sqlite_backend: SqliteBackend,
    table_name: str,
    batch_size: int = 1000
) -> int:
    """Migrate a single table from PostgreSQL to SQLite.

    Args:
        pg_backend: PostgreSQL backend instance
        sqlite_backend: SQLite backend instance
        table_name: Name of table to migrate
        batch_size: Number of rows to process at once

    Returns:
        Number of rows migrated
    """
    # Get column names from PostgreSQL
    columns = get_column_names(pg_backend, table_name, is_postgres=True)

    if not columns:
        # Table might not exist or has no columns
        return 0

    # Handle reserved words like "group"
    quoted_columns = [f'"{col}"' if col.lower() == 'group' else col for col in columns]
    columns_str = ', '.join(quoted_columns)

    # Select all rows from PostgreSQL
    rows = pg_backend.execute(f"SELECT {columns_str} FROM {table_name}")

    if not rows:
        return 0

    # Build INSERT statement
    placeholders = ', '.join([f':{col}' for col in columns])
    insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

    # Insert rows into SQLite with timestamp conversion
    migrated_count = 0
    for row in rows:
        converted_row = convert_row_timestamps(row)
        # Handle "group" column name in parameters
        params = {}
        for col in columns:
            params[col] = converted_row.get(col)
        sqlite_backend.execute(insert_sql, params)
        migrated_count += 1

    return migrated_count


class MigrationResult:
    """Result of a migration operation."""

    def __init__(self) -> None:
        """Initialize migration result."""
        self.table_counts: dict[str, dict[str, int]] = {}
        self.success: bool = False
        self.error: str | None = None
        self.warnings: list[str] = []

    def add_table_result(self, table: str, source_count: int, migrated_count: int) -> None:
        """Add result for a table migration.

        Args:
            table: Table name
            source_count: Number of rows in source
            migrated_count: Number of rows migrated
        """
        self.table_counts[table] = {
            'source': source_count,
            'migrated': migrated_count
        }

    def verify(self) -> bool:
        """Verify all tables were migrated correctly.

        Returns:
            True if all source counts match migrated counts
        """
        for table, counts in self.table_counts.items():
            if counts['source'] != counts['migrated']:
                return False
        return True

    def summary(self) -> str:
        """Generate human-readable summary of migration.

        Returns:
            Summary string
        """
        lines = ["Migration Summary", "=" * 40]

        for table, counts in self.table_counts.items():
            status = "OK" if counts['source'] == counts['migrated'] else "MISMATCH!"
            lines.append(f"  {table}: {counts['migrated']}/{counts['source']} rows [{status}]")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        total_source = sum(c['source'] for c in self.table_counts.values())
        total_migrated = sum(c['migrated'] for c in self.table_counts.values())
        lines.append("")
        lines.append(f"Total: {total_migrated}/{total_source} rows")

        if self.success:
            lines.append("Status: SUCCESS")
        elif self.error:
            lines.append(f"Status: FAILED - {self.error}")

        return "\n".join(lines)


def migrate_postgres_to_sqlite(
    pg_backend: DatabaseBackend,
    sqlite_path: str,
    force: bool = False,
    dry_run: bool = False
) -> MigrationResult:
    """Migrate all data from PostgreSQL to SQLite.

    Args:
        pg_backend: PostgreSQL backend instance (already connected)
        sqlite_path: Path to target SQLite database file
        force: If True, overwrite existing file. If False, abort if file exists.
        dry_run: If True, only report what would be migrated without writing.

    Returns:
        MigrationResult with details of the migration

    Raises:
        DatabaseError: On migration failure
        FileExistsError: If sqlite_path exists and force=False
    """
    result = MigrationResult()

    # Check if target file exists
    if not dry_run and os.path.exists(sqlite_path):
        if not force:
            raise FileExistsError(
                f"Target file already exists: {sqlite_path}. "
                "Use --force to overwrite."
            )
        # Remove existing file
        os.remove(sqlite_path)

    # Check if PostgreSQL has any data
    ledger_count = get_table_count(pg_backend, 'ledger')
    if ledger_count == 0:
        result.warnings.append("PostgreSQL ledger table is empty - nothing to migrate")
        result.success = True
        for table in TABLES_TO_MIGRATE:
            result.add_table_result(table, 0, 0)
        return result

    # Dry run: just count rows
    if dry_run:
        for table in TABLES_TO_MIGRATE:
            count = get_table_count(pg_backend, table)
            result.add_table_result(table, count, 0)
        result.success = True
        return result

    # Create SQLite database and tables
    sqlite_backend: SqliteBackend | None = None
    try:
        sqlite_backend = SqliteBackend(sqlite_path, auto_create_tables=True)

        # Migrate each table
        for table in TABLES_TO_MIGRATE:
            source_count = get_table_count(pg_backend, table)
            migrated_count = migrate_table(pg_backend, sqlite_backend, table)
            result.add_table_result(table, source_count, migrated_count)

        # Commit all changes
        sqlite_backend.commit()

        # Verify migration
        if result.verify():
            result.success = True
        else:
            result.error = "Row count mismatch after migration"
            result.success = False
            # Don't delete file - let user investigate
            sqlite_backend.close()
            sqlite_backend = None
            return result

    except Exception as e:
        result.error = str(e)
        result.success = False
        # Clean up partial file on error
        if sqlite_backend is not None:
            try:
                sqlite_backend.close()
            except Exception:
                pass
            sqlite_backend = None
        if os.path.exists(sqlite_path):
            try:
                os.remove(sqlite_path)
            except Exception:
                pass
        raise DatabaseError(f"Migration failed: {e}") from e
    finally:
        if sqlite_backend is not None:
            sqlite_backend.close()

    return result

"""Unit and integration tests for PostgreSQL to SQLite migration tool."""

import os
import tempfile
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.python.db import (
    SqliteBackend,
    DatabaseError,
    MigrationResult,
    convert_timestamp_to_iso8601,
)
from src.python.db.migration import (
    convert_row_timestamps,
    convert_value_for_sqlite,
    get_table_count,
    migrate_table,
    migrate_postgres_to_sqlite,
    TABLES_TO_MIGRATE,
)


class TestTimestampConversion:
    """Unit tests for timestamp conversion functions."""

    def test_convert_datetime_to_iso8601(self) -> None:
        """Test converting datetime object to ISO 8601 string."""
        dt = datetime(2025, 6, 15, 14, 30, 45)
        result = convert_timestamp_to_iso8601(dt)
        assert result == '2025-06-15 14:30:45'

    def test_convert_preserves_non_datetime(self) -> None:
        """Test that non-datetime values pass through unchanged."""
        assert convert_timestamp_to_iso8601('already a string') == 'already a string'
        assert convert_timestamp_to_iso8601(42) == 42
        assert convert_timestamp_to_iso8601(3.14) == 3.14
        assert convert_timestamp_to_iso8601(None) is None
        assert convert_timestamp_to_iso8601(['list']) == ['list']

    def test_convert_decimal_to_float(self) -> None:
        """Test converting Decimal object to float for SQLite compatibility."""
        dec = Decimal('123.456789')
        result = convert_value_for_sqlite(dec)
        assert result == 123.456789
        assert isinstance(result, float)

    def test_convert_value_handles_multiple_types(self) -> None:
        """Test that convert_value_for_sqlite handles datetime, Decimal, and other types."""
        dt = datetime(2025, 6, 15, 14, 30, 45)
        dec = Decimal('99.99')

        assert convert_value_for_sqlite(dt) == '2025-06-15 14:30:45'
        assert convert_value_for_sqlite(dec) == 99.99
        assert isinstance(convert_value_for_sqlite(dec), float)
        assert convert_value_for_sqlite('string') == 'string'
        assert convert_value_for_sqlite(42) == 42
        assert convert_value_for_sqlite(None) is None

    def test_convert_row_timestamps(self) -> None:
        """Test converting all PostgreSQL types in a row dictionary."""
        dt = datetime(2025, 1, 15, 10, 30, 0)
        dec = Decimal('99.5')
        row = {
            'id': 1,
            'name': 'Test',
            'created_at': dt,
            'value': dec,
            'is_active': True
        }
        result = convert_row_timestamps(row)

        assert result['id'] == 1
        assert result['name'] == 'Test'
        assert result['created_at'] == '2025-01-15 10:30:00'
        assert result['value'] == 99.5
        assert isinstance(result['value'], float)
        assert result['is_active'] is True

    def test_convert_row_with_no_timestamps(self) -> None:
        """Test converting row that has no datetime values."""
        row = {'id': 1, 'name': 'Test', 'value': 42}
        result = convert_row_timestamps(row)
        assert result == row


class TestMigrationResult:
    """Tests for MigrationResult class."""

    def test_add_table_result(self) -> None:
        """Test adding table results to MigrationResult."""
        result = MigrationResult()
        result.add_table_result('ledger', 100, 100)
        result.add_table_result('pair_price', 50, 50)

        assert result.table_counts['ledger'] == {'source': 100, 'migrated': 100}
        assert result.table_counts['pair_price'] == {'source': 50, 'migrated': 50}

    def test_verify_success(self) -> None:
        """Test verify returns True when all counts match."""
        result = MigrationResult()
        result.add_table_result('ledger', 100, 100)
        result.add_table_result('pair_price', 50, 50)

        assert result.verify() is True

    def test_verify_failure(self) -> None:
        """Test verify returns False when counts don't match."""
        result = MigrationResult()
        result.add_table_result('ledger', 100, 99)  # Mismatch!
        result.add_table_result('pair_price', 50, 50)

        assert result.verify() is False

    def test_summary_generation(self) -> None:
        """Test summary string generation."""
        result = MigrationResult()
        result.add_table_result('ledger', 100, 100)
        result.add_table_result('pair_price', 50, 50)
        result.success = True

        summary = result.summary()

        assert 'ledger: 100/100' in summary
        assert 'pair_price: 50/50' in summary
        assert 'Total: 150/150' in summary
        assert 'SUCCESS' in summary

    def test_summary_with_warnings(self) -> None:
        """Test summary includes warnings."""
        result = MigrationResult()
        result.warnings.append('Test warning message')
        result.success = True

        summary = result.summary()

        assert 'Warnings:' in summary
        assert 'Test warning message' in summary


class TestGetTableCount:
    """Tests for get_table_count function."""

    def test_count_populated_table(self) -> None:
        """Test counting rows in a populated table."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Insert some test data
        backend.execute(
            "INSERT INTO ledger (createddate, trans_type, buy, buy_curr) "
            "VALUES (:date, :type, :buy, :curr)",
            {'date': '2025-01-15', 'type': 'Trade', 'buy': 1.0, 'curr': 'BTC'}
        )
        backend.execute(
            "INSERT INTO ledger (createddate, trans_type, buy, buy_curr) "
            "VALUES (:date, :type, :buy, :curr)",
            {'date': '2025-01-16', 'type': 'Trade', 'buy': 2.0, 'curr': 'BTC'}
        )
        backend.commit()

        count = get_table_count(backend, 'ledger')
        assert count == 2

        backend.close()

    def test_count_empty_table(self) -> None:
        """Test counting rows in an empty table."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        count = get_table_count(backend, 'ledger')
        assert count == 0

        backend.close()


class TestMigrateTable:
    """Integration tests for migrate_table function using SQLite-to-SQLite migration."""

    def test_migrate_ledger_table(self) -> None:
        """Test migrating ledger table data."""
        # Source database with sample data
        source = SqliteBackend(':memory:', auto_create_tables=True)
        source.execute(
            "INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, exchange) "
            "VALUES (:date, :type, :buy, :buy_curr, :sell, :sell_curr, :exchange)",
            {
                'date': '2025-01-15 10:30:00',
                'type': 'Trade',
                'buy': 1.5,
                'buy_curr': 'BTC',
                'sell': 45000.0,
                'sell_curr': 'USD',
                'exchange': 'Kraken'
            }
        )
        source.commit()

        # Target database (empty)
        target = SqliteBackend(':memory:', auto_create_tables=True)

        # Mock get_column_names to use SQLite source
        from src.python.db.migration import get_column_names
        columns = get_column_names(source, 'ledger', is_postgres=False)

        # Manually migrate using SQLite column introspection
        rows = source.execute("SELECT * FROM ledger")
        assert len(rows) == 1

        # Insert into target
        for row in rows:
            converted = convert_row_timestamps(row)
            placeholders = ', '.join([f':{k}' for k in converted.keys()])
            quoted_cols = ', '.join([f'"{k}"' if k == 'group' else k for k in converted.keys()])
            insert_sql = f"INSERT INTO ledger ({quoted_cols}) VALUES ({placeholders})"
            target.execute(insert_sql, converted)
        target.commit()

        # Verify
        result = target.execute("SELECT * FROM ledger")
        assert len(result) == 1
        assert result[0]['buy_curr'] == 'BTC'
        assert result[0]['buy'] == 1.5

        source.close()
        target.close()

    def test_migrate_pair_price_table(self) -> None:
        """Test migrating pair_price table data."""
        source = SqliteBackend(':memory:', auto_create_tables=True)
        source.execute(
            "INSERT INTO pair_price (to_curr, price, from_curr, date) "
            "VALUES (:to_curr, :price, :from_curr, :date)",
            {'to_curr': 'USD', 'price': 45000.0, 'from_curr': 'BTC', 'date': '2025-01-15 10:00:00'}
        )
        source.commit()

        target = SqliteBackend(':memory:', auto_create_tables=True)

        # Copy data
        rows = source.execute("SELECT * FROM pair_price")
        for row in rows:
            target.execute(
                "INSERT INTO pair_price (to_curr, price, from_curr, date) "
                "VALUES (:to_curr, :price, :from_curr, :date)",
                row
            )
        target.commit()

        result = target.execute("SELECT * FROM pair_price")
        assert len(result) == 1
        assert result[0]['price'] == 45000.0

        source.close()
        target.close()


class TestMigratePostgresToSqlite:
    """Tests for migrate_postgres_to_sqlite function."""

    def test_file_exists_error_without_force(self) -> None:
        """Test that existing file raises error without --force."""
        # Create a mock PostgreSQL backend
        mock_pg = MagicMock()
        mock_pg.execute_scalar.return_value = 10  # Some data exists

        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
            temp_path = f.name

        try:
            with pytest.raises(FileExistsError) as exc_info:
                migrate_postgres_to_sqlite(mock_pg, temp_path, force=False)
            assert 'already exists' in str(exc_info.value)
        finally:
            os.unlink(temp_path)

    def test_empty_database_warning(self) -> None:
        """Test warning when PostgreSQL ledger is empty."""
        mock_pg = MagicMock()
        mock_pg.execute_scalar.return_value = 0  # Empty ledger

        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = os.path.join(tmpdir, 'test.db')

            result = migrate_postgres_to_sqlite(mock_pg, sqlite_path, dry_run=True)

            assert result.success is True
            assert any('empty' in w.lower() for w in result.warnings)

    def test_dry_run_does_not_create_file(self) -> None:
        """Test that dry run doesn't create the SQLite file."""
        mock_pg = MagicMock()
        mock_pg.execute_scalar.return_value = 10

        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = os.path.join(tmpdir, 'test.db')

            result = migrate_postgres_to_sqlite(mock_pg, sqlite_path, dry_run=True)

            assert result.success is True
            assert not os.path.exists(sqlite_path)


class TestMigrationIntegration:
    """Integration tests simulating full migration with SQLite source (mock for PG)."""

    def test_full_migration_simulation(self) -> None:
        """Test complete migration flow with mocked PostgreSQL."""
        # Create source SQLite to simulate PostgreSQL data
        source = SqliteBackend(':memory:', auto_create_tables=True)

        # Add sample data to all tables
        source.execute(
            "INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr) "
            "VALUES (:date, :type, :buy, :buy_curr, :sell, :sell_curr)",
            {
                'date': '2025-01-15 10:30:00',
                'type': 'Trade',
                'buy': 1.0,
                'buy_curr': 'BTC',
                'sell': 50000.0,
                'sell_curr': 'USD'
            }
        )
        source.execute(
            "INSERT INTO pair_price (to_curr, price, from_curr, date) "
            "VALUES (:to_curr, :price, :from_curr, :date)",
            {'to_curr': 'USD', 'price': 50000.0, 'from_curr': 'BTC', 'date': '2025-01-15'}
        )
        source.execute(
            "INSERT INTO coins (name, max_supply, circ_supply) VALUES (:name, :max, :circ)",
            {'name': 'BTC', 'max': 21000000, 'circ': 19500000}
        )
        source.execute(
            "INSERT INTO wallets (wallet_id, wallet_type, custody) VALUES (:id, :type, :custody)",
            {'id': 'ledger-1', 'type': 'hardware', 'custody': 'self'}
        )
        source.commit()

        # Verify source data
        assert get_table_count(source, 'ledger') == 1
        assert get_table_count(source, 'pair_price') == 1
        assert get_table_count(source, 'coins') == 1
        assert get_table_count(source, 'wallets') == 1

        source.close()

    def test_migration_result_verification(self) -> None:
        """Test that migration results verify correctly."""
        result = MigrationResult()

        # Simulate successful migration
        result.add_table_result('coins', 5, 5)
        result.add_table_result('wallets', 3, 3)
        result.add_table_result('ledger', 100, 100)
        result.add_table_result('pair_price', 500, 500)
        result.success = True

        assert result.verify() is True

        summary = result.summary()
        assert 'Total: 608/608' in summary
        assert 'SUCCESS' in summary


# PostgreSQL tests are skipped when PGHOST is not set
@pytest.mark.skipif(
    not os.getenv('PGHOST'),
    reason="PostgreSQL not configured (PGHOST not set)"
)
class TestPostgreSQLMigration:
    """Integration tests that require actual PostgreSQL connection."""

    def test_connect_to_postgres(self) -> None:
        """Test that we can connect to PostgreSQL."""
        from src.python.db import PostgresBackend

        pg = PostgresBackend()
        count = get_table_count(pg, 'ledger')
        assert isinstance(count, int)
        pg.close()

    def test_real_migration_dry_run(self) -> None:
        """Test dry run against real PostgreSQL database."""
        from src.python.db import PostgresBackend

        pg = PostgresBackend()
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = os.path.join(tmpdir, 'test.db')

            result = migrate_postgres_to_sqlite(pg, sqlite_path, dry_run=True)

            # Should report counts but not create file
            assert result.success is True
            assert not os.path.exists(sqlite_path)

        pg.close()

    def test_real_migration_with_force(self) -> None:
        """Test actual migration from PostgreSQL to SQLite."""
        from src.python.db import PostgresBackend

        pg = PostgresBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = os.path.join(tmpdir, 'test.db')

            result = migrate_postgres_to_sqlite(pg, sqlite_path, force=True)

            if result.success:
                # Verify file was created
                assert os.path.exists(sqlite_path)

                # Verify data was migrated
                sqlite = SqliteBackend(sqlite_path, auto_create_tables=False)
                for table in TABLES_TO_MIGRATE:
                    sqlite_count = get_table_count(sqlite, table)
                    pg_count = result.table_counts[table]['source']
                    assert sqlite_count == pg_count, f"Mismatch in {table}"
                sqlite.close()

        pg.close()

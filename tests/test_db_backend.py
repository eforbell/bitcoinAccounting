"""Unit tests for database backend abstraction layer."""

import os
from datetime import datetime
import pytest

from src.python.db import (
    BalanceCalculator,
    BasisCalculator,
    DatabaseBackend,
    DatabaseError,
    IncomeQuery,
    SqliteBackend,
    PostgresBackend,
    get_backend,
    create_tables,
    get_sqlite_path,
    PriceLookup,
    TradeQuery,
)


class TestSqliteBackend:
    """Tests for SQLite backend using in-memory database."""

    def test_init_memory_database(self):
        """Test initialization with :memory: database."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)
        assert backend.db_path == ':memory:'
        backend.close()

    def test_execute_returns_list_of_dicts(self):
        """Test execute returns list of dictionaries with column names."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        # Create test table
        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.execute("INSERT INTO test VALUES (2, 'Bob')")
        backend.commit()

        # Query results
        results = backend.execute("SELECT * FROM test ORDER BY id")

        assert len(results) == 2
        assert isinstance(results[0], dict)
        assert results[0] == {'id': 1, 'name': 'Alice'}
        assert results[1] == {'id': 2, 'name': 'Bob'}

        backend.close()

    def test_execute_with_named_params(self):
        """Test execute with :named placeholder syntax."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.execute("INSERT INTO test VALUES (2, 'Bob')")
        backend.commit()

        # Query with named parameter
        results = backend.execute("SELECT * FROM test WHERE name = :name", {'name': 'Bob'})

        assert len(results) == 1
        assert results[0]['name'] == 'Bob'

        backend.close()

    def test_execute_with_datetime_param(self):
        """Datetime params are normalized before sqlite binding."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)
        backend.execute("CREATE TABLE test (createddate TEXT)")

        backend.execute(
            "INSERT INTO test VALUES (:createddate)",
            {"createddate": datetime(2024, 1, 1, 12, 30, 45)},
        )
        backend.commit()

        row = backend.execute_one("SELECT createddate FROM test")
        assert row is not None
        assert row["createddate"] == "2024-01-01 12:30:45"

        backend.close()

    def test_execute_empty_results(self):
        """Test execute with no matching rows returns empty list."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        results = backend.execute("SELECT * FROM test")

        assert results == []

        backend.close()

    def test_execute_one_returns_dict(self):
        """Test execute_one returns single dictionary."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.commit()

        result = backend.execute_one("SELECT * FROM test WHERE id = :id", {'id': 1})

        assert isinstance(result, dict)
        assert result == {'id': 1, 'name': 'Alice'}

        backend.close()

    def test_execute_one_no_results_returns_none(self):
        """Test execute_one returns None when no rows match."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        result = backend.execute_one("SELECT * FROM test WHERE id = :id", {'id': 999})

        assert result is None

        backend.close()

    def test_execute_scalar_returns_value(self):
        """Test execute_scalar returns first column value."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.commit()

        result = backend.execute_scalar("SELECT name FROM test WHERE id = :id", {'id': 1})

        assert result == 'Alice'

        backend.close()

    def test_execute_scalar_with_count(self):
        """Test execute_scalar with COUNT query."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.execute("INSERT INTO test VALUES (2, 'Bob')")
        backend.commit()

        count = backend.execute_scalar("SELECT COUNT(*) FROM test")

        assert count == 2

        backend.close()

    def test_execute_scalar_no_results_returns_none(self):
        """Test execute_scalar returns None when no rows match."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        result = backend.execute_scalar("SELECT name FROM test WHERE id = :id", {'id': 999})

        assert result is None

        backend.close()

    def test_commit_and_rollback(self):
        """Test commit and rollback behavior."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        # Insert and commit
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.commit()

        count = backend.execute_scalar("SELECT COUNT(*) FROM test")
        assert count == 1

        # Insert and rollback
        backend.execute("INSERT INTO test VALUES (2, 'Bob')")
        backend.rollback()

        count = backend.execute_scalar("SELECT COUNT(*) FROM test")
        assert count == 1  # Bob was rolled back

        backend.close()

    def test_database_error_on_invalid_query(self):
        """Test that DatabaseError is raised on invalid SQL."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)

        with pytest.raises(DatabaseError, match="Query execution failed"):
            backend.execute("INVALID SQL SYNTAX")

        backend.close()

    def test_parent_directory_creation(self, tmp_path):
        """Test that parent directory is created if missing."""
        db_path = tmp_path / "subdir" / "test.db"

        backend = SqliteBackend(str(db_path), auto_create_tables=False)

        assert db_path.exists()

        backend.close()


class TestFactoryFunction:
    """Tests for get_backend() factory function."""

    def test_get_backend_defaults_to_sqlite(self):
        """Test factory defaults to SQLite when no args."""
        # Clear env var to test default
        old_val = os.environ.pop('DB_BACKEND', None)

        try:
            backend = get_backend()
            assert isinstance(backend, SqliteBackend)
            backend.close()
        finally:
            if old_val:
                os.environ['DB_BACKEND'] = old_val

    def test_get_backend_sqlite_explicit(self):
        """Test factory creates SQLite backend when explicitly requested."""
        backend = get_backend('sqlite')
        assert isinstance(backend, SqliteBackend)
        backend.close()

    def test_get_backend_from_env_var(self):
        """Test factory reads DB_BACKEND environment variable."""
        old_val = os.environ.get('DB_BACKEND')

        try:
            os.environ['DB_BACKEND'] = 'sqlite'
            backend = get_backend()
            assert isinstance(backend, SqliteBackend)
            backend.close()
        finally:
            if old_val:
                os.environ['DB_BACKEND'] = old_val
            else:
                os.environ.pop('DB_BACKEND', None)

    def test_get_backend_case_insensitive(self):
        """Test factory handles case-insensitive backend names."""
        backend = get_backend('SQLITE')
        assert isinstance(backend, SqliteBackend)
        backend.close()

    def test_get_backend_invalid_type_raises_error(self):
        """Test factory raises ValueError for unknown backend."""
        with pytest.raises(ValueError, match="Unknown backend type: mysql"):
            get_backend('mysql')


@pytest.mark.skipif(
    os.getenv('PGHOST') is None,
    reason="PostgreSQL not available (PGHOST not set)"
)
class TestPostgresBackend:
    """Tests for PostgreSQL backend (skipped if PostgreSQL unavailable)."""

    def test_postgres_connect(self):
        """Test PostgreSQL connection."""
        backend = PostgresBackend()
        assert backend.connection is not None
        backend.close()

    def test_postgres_execute_with_named_params(self):
        """Test PostgreSQL execute with :named placeholders."""
        backend = PostgresBackend()

        # Simple query that should work on any PostgreSQL
        result = backend.execute_one("SELECT :value AS test_value", {'value': 42})

        assert result is not None
        assert result['test_value'] == 42

        backend.close()

    def test_postgres_get_backend_factory(self):
        """Test factory creates PostgreSQL backend."""
        backend = get_backend('postgres')
        assert isinstance(backend, PostgresBackend)
        backend.close()


class TestSchemaCreation:
    """Tests for schema creation and initialization."""

    def test_auto_create_tables_on_init(self, tmp_path):
        """Test that tables are automatically created when SqliteBackend is initialized."""
        db_path = tmp_path / "test.db"

        # Create backend with auto_create_tables=True (default)
        backend = SqliteBackend(str(db_path))

        # Verify all tables exist
        tables = backend.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [t['name'] for t in tables]

        assert 'ledger' in table_names
        assert 'pair_price' in table_names
        assert 'coins' in table_names
        assert 'wallets' in table_names

        backend.close()

    def test_create_tables_is_idempotent(self, tmp_path):
        """Test that create_tables can be called multiple times without error."""
        db_path = tmp_path / "test.db"
        backend = SqliteBackend(str(db_path), auto_create_tables=False)

        # Create tables first time
        create_tables(backend)

        # Create tables second time - should not error
        create_tables(backend)

        # Verify tables exist
        tables = backend.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        assert len(tables) == 4

        backend.close()

    def test_ledger_table_structure(self, tmp_path):
        """Test ledger table has correct columns and can insert/query data."""
        db_path = tmp_path / "test.db"
        backend = SqliteBackend(str(db_path))

        # Insert a record
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange)
               VALUES (:date, :type, :buy, :buy_curr, :sell, :sell_curr, :fee, :fee_curr, :exchange)""",
            {
                'date': '2025-01-15 10:30:00',
                'type': 'Trade',
                'buy': 0.5,
                'buy_curr': 'BTC',
                'sell': 25000.0,
                'sell_curr': 'USD',
                'fee': 10.0,
                'fee_curr': 'USD',
                'exchange': 'TestExchange'
            }
        )
        backend.commit()

        # Query it back
        result = backend.execute_one("SELECT * FROM ledger WHERE buy_curr = :curr", {'curr': 'BTC'})

        assert result is not None
        assert result['trans_type'] == 'Trade'
        assert result['buy'] == 0.5
        assert result['buy_curr'] == 'BTC'
        assert result['id'] is not None  # Auto-incremented

        backend.close()

    def test_pair_price_table_structure(self, tmp_path):
        """Test pair_price table can store price data."""
        db_path = tmp_path / "test.db"
        backend = SqliteBackend(str(db_path))

        # Insert price data
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15'
            }
        )
        backend.commit()

        # Query it back
        result = backend.execute_one(
            "SELECT * FROM pair_price WHERE from_curr = :from AND to_curr = :to",
            {'from': 'BTC', 'to': 'USD'}
        )

        assert result is not None
        assert result['price'] == 50000.0
        assert result['date'] == '2025-01-15'

        backend.close()

    def test_coins_table_structure(self, tmp_path):
        """Test coins table can store coin metadata."""
        db_path = tmp_path / "test.db"
        backend = SqliteBackend(str(db_path))

        # Insert coin data
        backend.execute(
            """INSERT INTO coins (name, max_supply, circ_supply)
               VALUES (:name, :max, :circ)""",
            {
                'name': 'BTC',
                'max': 21000000,
                'circ': 19000000
            }
        )
        backend.commit()

        # Query it back
        result = backend.execute_one("SELECT * FROM coins WHERE name = :name", {'name': 'BTC'})

        assert result is not None
        assert result['name'] == 'BTC'
        assert result['max_supply'] == 21000000

        backend.close()

    def test_wallets_table_structure(self, tmp_path):
        """Test wallets table can store wallet metadata."""
        db_path = tmp_path / "test.db"
        backend = SqliteBackend(str(db_path))

        # Insert wallet data
        backend.execute(
            """INSERT INTO wallets (wallet_id, wallet_type, custody, description, active)
               VALUES (:id, :type, :custody, :desc, :active)""",
            {
                'id': 'Strike',
                'type': 'exchange',
                'custody': 'custodial',
                'desc': 'Strike account',
                'active': 1
            }
        )
        backend.commit()

        # Query it back
        result = backend.execute_one("SELECT * FROM wallets WHERE wallet_id = :id", {'id': 'Strike'})

        assert result is not None
        assert result['wallet_type'] == 'exchange'
        assert result['custody'] == 'custodial'
        assert result['active'] == 1

        backend.close()

    def test_get_sqlite_path_default(self, tmp_path, monkeypatch):
        """Test get_sqlite_path returns new default path."""
        monkeypatch.delenv('SQLITE_DB_PATH', raising=False)
        monkeypatch.setenv('HOME', str(tmp_path))

        path = get_sqlite_path()
        assert path.endswith('.bitcoinaccounting/ledger.db')
        assert '~' not in path  # Should be expanded

    def test_get_sqlite_path_falls_back_to_legacy(self, tmp_path, monkeypatch):
        """Test get_sqlite_path falls back when legacy DB exists."""
        monkeypatch.delenv('SQLITE_DB_PATH', raising=False)
        monkeypatch.setenv('HOME', str(tmp_path))

        legacy_path = tmp_path / ".cryptoaccounting" / "ledger.db"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("")

        path = get_sqlite_path()
        assert path == str(legacy_path)

    def test_get_sqlite_path_prefers_new_over_legacy(self, tmp_path, monkeypatch):
        """Test get_sqlite_path prefers new path when both exist."""
        monkeypatch.delenv('SQLITE_DB_PATH', raising=False)
        monkeypatch.setenv('HOME', str(tmp_path))

        legacy_path = tmp_path / ".cryptoaccounting" / "ledger.db"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("")

        new_path = tmp_path / ".bitcoinaccounting" / "ledger.db"
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text("")

        path = get_sqlite_path()
        assert path == str(new_path)

    def test_get_sqlite_path_from_env(self):
        """Test get_sqlite_path reads from environment variable."""
        old_val = os.environ.get('SQLITE_DB_PATH')

        try:
            test_path = '/tmp/test.db'
            os.environ['SQLITE_DB_PATH'] = test_path
            path = get_sqlite_path()
            assert path == test_path
        finally:
            if old_val:
                os.environ['SQLITE_DB_PATH'] = old_val
            else:
                os.environ.pop('SQLITE_DB_PATH', None)

    def test_parent_directory_auto_created(self, tmp_path):
        """Test that parent directory is created automatically."""
        db_path = tmp_path / "nested" / "dir" / "test.db"

        # Parent dirs don't exist yet
        assert not db_path.parent.exists()

        # Create backend
        backend = SqliteBackend(str(db_path))

        # Parent dirs should now exist
        assert db_path.parent.exists()
        assert db_path.exists()

        backend.close()


class TestPriceLookup:
    """Tests for PriceLookup query class."""

    def test_exact_timestamp_match(self):
        """Test that exact timestamp match returns correct price."""
        backend = SqliteBackend(':memory:')

        # Insert exact price match
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 14:30:00'
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        price = price_lookup.get_price('BTC', 'USD', '2025-01-15 14:30:00')

        assert price == 50000.0

        backend.close()

    def test_same_day_fuzzy_match_closest_time(self):
        """Test that same-day fuzzy matching returns closest price by minute."""
        backend = SqliteBackend(':memory:')

        # Insert multiple prices on same day at different times
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 49000.0,
                'date': '2025-01-15 08:00:00'  # 6.5 hours before requested
            }
        )
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 14:00:00'  # 30 minutes before requested
            }
        )
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 51000.0,
                'date': '2025-01-15 20:00:00'  # 5.5 hours after requested
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Request price at 14:30 - should match 14:00 (30 min away)
        price = price_lookup.get_price('BTC', 'USD', '2025-01-15 14:30:00')

        assert price == 50000.0

        backend.close()

    def test_no_match_on_day_returns_none(self):
        """Test that no price on requested day returns None."""
        backend = SqliteBackend(':memory:')

        # Insert price on different day
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-14 14:30:00'
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Request price on different day
        price = price_lookup.get_price('BTC', 'USD', '2025-01-15 14:30:00')

        assert price is None

        backend.close()

    def test_empty_table_returns_none(self):
        """Test that empty pair_price table returns None."""
        backend = SqliteBackend(':memory:')

        price_lookup = PriceLookup(backend)
        price = price_lookup.get_price('BTC', 'USD', '2025-01-15 14:30:00')

        assert price is None

        backend.close()

    def test_wrong_currency_pair_returns_none(self):
        """Test that wrong currency pair returns None."""
        backend = SqliteBackend(':memory:')

        # Insert BTC/USD price
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 14:30:00'
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Request ETH/USD (not in table)
        price = price_lookup.get_price('ETH', 'USD', '2025-01-15 14:30:00')

        assert price is None

        backend.close()

    def test_get_price_date_returns_matched_timestamp(self):
        """Test that get_price_date returns the actual timestamp used."""
        backend = SqliteBackend(':memory:')

        # Insert price
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 14:00:00'
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Request at 14:30, should match 14:00
        price_date = price_lookup.get_price_date('BTC', 'USD', '2025-01-15 14:30:00')

        assert price_date == '2025-01-15 14:00:00'

        backend.close()

    def test_get_price_date_no_match_returns_none(self):
        """Test that get_price_date returns None when no match."""
        backend = SqliteBackend(':memory:')

        price_lookup = PriceLookup(backend)
        price_date = price_lookup.get_price_date('BTC', 'USD', '2025-01-15 14:30:00')

        assert price_date is None

        backend.close()

    def test_default_price_date_uses_current_time(self):
        """Test that None price_date defaults to current datetime."""
        backend = SqliteBackend(':memory:')

        from datetime import datetime

        # Insert price for today
        today = datetime.now().strftime('%Y-%m-%d 12:00:00')
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': today
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Don't specify price_date - should default to today
        price = price_lookup.get_price('BTC', 'USD', None)

        # Should find the price if today matches
        assert price == 50000.0

        backend.close()

    def test_default_to_currency_is_usd(self):
        """Test that to_coin defaults to USD."""
        backend = SqliteBackend(':memory:')

        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 14:30:00'
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Don't specify to_coin - should default to USD
        price = price_lookup.get_price('BTC', price_date='2025-01-15 14:30:00')

        assert price == 50000.0

        backend.close()

    def test_multiple_prices_returns_absolute_closest(self):
        """Test that when multiple prices exist, the absolute closest by time is returned."""
        backend = SqliteBackend(':memory:')

        # Insert prices: one 15 min before, one 10 min after
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 49500.0,
                'date': '2025-01-15 14:15:00'  # 15 min before 14:30
            }
        )
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from, :to, :price, :date)""",
            {
                'from': 'BTC',
                'to': 'USD',
                'price': 50500.0,
                'date': '2025-01-15 14:40:00'  # 10 min after 14:30
            }
        )
        backend.commit()

        price_lookup = PriceLookup(backend)
        # Request at 14:30 - should match 14:40 (10 min away vs 15 min)
        price = price_lookup.get_price('BTC', 'USD', '2025-01-15 14:30:00')

        assert price == 50500.0

        backend.close()


class TestBalanceCalculator:
    """Tests for BalanceCalculator class."""

    def test_balance_with_only_buys(self):
        """Test balance calculation with only buy transactions."""
        backend = SqliteBackend(':memory:')

        # Insert some buy transactions
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase'
            }
        )
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 25000.0,
                'fee_curr': 'USD',
                'fee': 5.0,
                'exchange': 'Coinbase'
            }
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        balance = balance_calc.get_balance('BTC')

        assert balance == 1.5

        backend.close()

    def test_balance_with_buys_and_sells(self):
        """Test balance calculation with both buy and sell transactions."""
        backend = SqliteBackend(':memory:')

        # Buy 1.0 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
}
        )
        # Sell 0.3 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 15000.0,
                'sell_curr': 'BTC',
                'sell': 0.3,
                'fee_curr': 'USD',
                'fee': 5.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        balance = balance_calc.get_balance('BTC')

        assert balance == 0.7  # 1.0 - 0.3

        backend.close()

    def test_balance_excluding_stakes(self):
        """Test that Stake transactions are excluded from buy sum."""
        backend = SqliteBackend(':memory:')

        # Regular buy
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'ETH',
                'buy': 10.0,
                'sell_curr': 'USD',
                'sell': 30000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
}
        )
        # Stake transaction - should be excluded from balance
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Stake',
                'buy_curr': 'ETH',
                'buy': 5.0,
                'sell_curr': 'ETH',
                'sell': 5.0,
                'fee_curr': 'ETH',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        balance = balance_calc.get_balance('ETH')

        # Should be 10.0 (regular buy) - 5.0 (stake sell) = 5.0
        # The stake buy of 5.0 is excluded
        assert balance == 5.0

        backend.close()

    def test_zero_balance_no_transactions(self):
        """Test that balance returns 0.0 when no transactions exist."""
        backend = SqliteBackend(':memory:')

        balance_calc = BalanceCalculator(backend)
        balance = balance_calc.get_balance('BTC')

        assert balance == 0.0

        backend.close()

    def test_negative_balance(self):
        """Test that balance can be negative (sold more than bought)."""
        backend = SqliteBackend(':memory:')

        # Buy 0.5 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 25000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
}
        )
        # Sell 1.0 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 50000.0,
                'sell_curr': 'BTC',
                'sell': 1.0,
                'fee_curr': 'USD',
                'fee': 5.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        balance = balance_calc.get_balance('BTC')

        assert balance == -0.5  # 0.5 - 1.0

        backend.close()

    def test_transfer_sum_with_mixed_transaction_types(self):
        """Test transfer sum with deposits, withdrawals, and other transaction types."""
        backend = SqliteBackend(':memory:')

        # Deposit: buy BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Deposit',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': '',
                'sell': 0.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        # Withdrawal: sell BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Withdrawal',
                'buy_curr': '',
                'buy': 0.0,
                'sell_curr': 'BTC',
                'sell': 0.3,
                'fee_curr': 'BTC',
                'fee': 0.001,
                'exchange': 'Coinbase',
}
        )
        # Trade: should be excluded from transfer sum
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-17 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 25000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        transfer_sum = balance_calc.get_sum_of_all_transfers('BTC')

        # Should be 1.0 (deposit) - 0.3 (withdrawal) = 0.7
        # Trade of 0.5 should be excluded
        assert transfer_sum == 0.7

        backend.close()

    def test_transfer_sum_zero_when_no_transfers(self):
        """Test transfer sum returns 0.0 when no transfers exist."""
        backend = SqliteBackend(':memory:')

        # Add a trade (not a transfer)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        transfer_sum = balance_calc.get_sum_of_all_transfers('BTC')

        # Should be 0.0 because no deposits/withdrawals
        assert transfer_sum == 0.0

        backend.close()

    def test_transfer_sum_only_deposits(self):
        """Test transfer sum with only deposits."""
        backend = SqliteBackend(':memory:')

        # Deposit 1.0 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Deposit',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': '',
                'sell': 0.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        # Deposit 0.5 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Deposit',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': '',
                'sell': 0.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        transfer_sum = balance_calc.get_sum_of_all_transfers('BTC')

        assert transfer_sum == 1.5

        backend.close()

    def test_transfer_sum_negative_with_more_withdrawals(self):
        """Test transfer sum can be negative when withdrawals exceed deposits."""
        backend = SqliteBackend(':memory:')

        # Deposit 0.5 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Deposit',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': '',
                'sell': 0.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        # Withdraw 1.0 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 10:00:00',
                'trans_type': 'Withdrawal',
                'buy_curr': '',
                'buy': 0.0,
                'sell_curr': 'BTC',
                'sell': 1.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
}
        )
        backend.commit()

        balance_calc = BalanceCalculator(backend)
        transfer_sum = balance_calc.get_sum_of_all_transfers('BTC')

        assert transfer_sum == -0.5  # 0.5 - 1.0

        backend.close()


class TestTradeQuery:
    """Tests for TradeQuery class."""

    def test_buy_trade_positive_quantity(self):
        """Test buy trade (USD -> BTC) shows positive to_quantity."""
        backend = SqliteBackend(':memory:')

        # Buy BTC with USD
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        assert len(trades) == 1
        trade = trades[0]
        assert trade['date'] == '2025-01-15 10:00:00'
        assert trade['to_curr'] == 'BTC'
        assert trade['to_quantity'] == 1.0  # Positive for buy
        assert trade['from_curr'] == 'USD'
        assert trade['from_quantity'] == 50000.0
        assert trade['price'] == 50000.0  # USD per BTC

        backend.close()

    def test_sell_trade_negative_quantity(self):
        """Test sell trade (BTC -> USD) shows negative to_quantity."""
        backend = SqliteBackend(':memory:')

        # Sell BTC for USD
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 15:30:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 51000.0,
                'sell_curr': 'BTC',
                'sell': 1.0,
                'fee_curr': 'USD',
                'fee': 5.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        assert len(trades) == 1
        trade = trades[0]
        assert trade['date'] == '2025-01-16 15:30:00'
        assert trade['to_curr'] == 'BTC'
        assert trade['to_quantity'] == -1.0  # Negative for sell
        assert trade['from_curr'] == 'USD'
        assert trade['from_quantity'] == 51000.0
        assert trade['price'] == 51000.0  # USD per BTC

        backend.close()

    def test_multiple_trades_ordered_by_date(self):
        """Test multiple trades are returned in ascending date order."""
        backend = SqliteBackend(':memory:')

        # First trade: buy 0.5 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 25000.0,
                'fee_curr': 'USD',
                'fee': 5.0,
                'exchange': 'Coinbase',
            }
        )
        # Third trade: sell 0.3 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-17 14:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 16000.0,
                'sell_curr': 'BTC',
                'sell': 0.3,
                'fee_curr': 'USD',
                'fee': 3.0,
                'exchange': 'Kraken',
            }
        )
        # Second trade: buy 1.0 BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 12:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 51000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        # Should be ordered by date ascending
        assert len(trades) == 3
        assert trades[0]['date'] == '2025-01-15 10:00:00'
        assert trades[0]['to_quantity'] == 0.5
        assert trades[1]['date'] == '2025-01-16 12:00:00'
        assert trades[1]['to_quantity'] == 1.0
        assert trades[2]['date'] == '2025-01-17 14:00:00'
        assert trades[2]['to_quantity'] == -0.3

        backend.close()

    def test_no_trades_returns_empty_list(self):
        """Test get_trades returns empty list when no trades exist."""
        backend = SqliteBackend(':memory:')

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        assert trades == []

        backend.close()

    def test_trades_for_different_coin_not_included(self):
        """Test trades for other coins are not included in results."""
        backend = SqliteBackend(':memory:')

        # BTC trade
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        # ETH trade (should not appear in BTC results)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 11:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'ETH',
                'buy': 10.0,
                'sell_curr': 'USD',
                'sell': 30000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        btc_trades = trade_query.get_trades('BTC')

        # Should only have 1 trade (BTC)
        assert len(btc_trades) == 1
        assert btc_trades[0]['to_curr'] == 'BTC'

        backend.close()

    def test_non_trade_transactions_excluded(self):
        """Test that non-Trade transactions are excluded from results."""
        backend = SqliteBackend(':memory:')

        # Trade transaction
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        # Deposit transaction (should be excluded)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 11:00:00',
                'trans_type': 'Deposit',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': '',
                'sell': 0.0,
                'fee_curr': '',
                'fee': 0.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        # Should only include the Trade transaction
        assert len(trades) == 1
        assert trades[0]['to_quantity'] == 1.0

        backend.close()

    def test_price_calculation_accuracy(self):
        """Test that price is calculated correctly as counter_amount / coin_amount."""
        backend = SqliteBackend(':memory:')

        # Buy 0.02 BTC for 1000 USD (price should be 1000/0.02 = 50000)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.02,
                'sell_curr': 'USD',
                'sell': 1000.0,
                'fee_curr': 'USD',
                'fee': 2.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        trades = trade_query.get_trades('BTC')

        assert len(trades) == 1
        # Price should be USD/BTC = 1000/0.02 = 50000
        assert trades[0]['price'] == 50000.0

        backend.close()

    def test_trade_cost_direct_usd(self):
        """Test get_trade_cost with direct USD trade (no price lookup needed)."""
        backend = SqliteBackend(':memory:')

        # Buy 1.0 BTC for 50000 USD
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        cost_data = trade_query.get_trade_cost('BTC', 'USD')

        assert len(cost_data) == 1
        trade = cost_data[0]
        assert trade['date'] == '2025-01-15 10:00:00'
        assert trade['curr'] == 'BTC'
        assert trade['quantity'] == 1.0
        assert trade['trade_curr'] == 'USD'
        assert trade['trade_quantity'] == 50000.0
        assert trade['cost_curr'] == 'USD'
        assert trade['unit_cost'] == 50000.0  # Direct price, no conversion
        assert trade['total_cost'] == 50000.0  # 50000 * 1.0
        assert trade['cost_curr_quote_date'] == '2025-01-15 10:00:00'  # Trade date

        backend.close()

    def test_trade_cost_cross_currency_with_price(self):
        """Test get_trade_cost with cross-currency trade requiring price lookup."""
        backend = SqliteBackend(':memory:')

        # Buy 1.0 BTC for 45000 EUR
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'EUR',
                'sell': 45000.0,
                'fee_curr': 'EUR',
                'fee': 10.0,
                'exchange': 'Kraken',
            }
        )

        # Add EUR/USD price for conversion
        backend.execute(
            """INSERT INTO pair_price (date, from_curr, to_curr, price)
               VALUES (:date, :from_curr, :to_curr, :price)""",
            {
                'date': '2025-01-15 10:05:00',  # Close to trade time
                'from_curr': 'EUR',
                'to_curr': 'USD',
                'price': 1.10,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        cost_data = trade_query.get_trade_cost('BTC', 'USD')

        assert len(cost_data) == 1
        trade = cost_data[0]
        assert trade['date'] == '2025-01-15 10:00:00'
        assert trade['curr'] == 'BTC'
        assert trade['quantity'] == 1.0
        assert trade['trade_curr'] == 'EUR'
        assert trade['trade_quantity'] == 45000.0
        assert trade['cost_curr'] == 'USD'
        # unit_cost = trade_price * eur_usd_price = 45000 * 1.10 = 49500
        assert trade['unit_cost'] == pytest.approx(49500.0)
        assert trade['total_cost'] == pytest.approx(49500.0)  # 49500 * 1.0
        assert trade['cost_curr_quote_date'] == '2025-01-15 10:05:00'  # Price date

        backend.close()

    def test_trade_cost_missing_price(self):
        """Test get_trade_cost when price lookup returns None."""
        backend = SqliteBackend(':memory:')

        # Buy 1.0 BTC for 45000 EUR, but no EUR/USD price available
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'EUR',
                'sell': 45000.0,
                'fee_curr': 'EUR',
                'fee': 10.0,
                'exchange': 'Kraken',
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        cost_data = trade_query.get_trade_cost('BTC', 'USD')

        assert len(cost_data) == 1
        trade = cost_data[0]
        assert trade['date'] == '2025-01-15 10:00:00'
        assert trade['curr'] == 'BTC'
        assert trade['quantity'] == 1.0
        assert trade['trade_curr'] == 'EUR'
        assert trade['trade_quantity'] == 45000.0
        assert trade['cost_curr'] == 'USD'
        assert trade['unit_cost'] is None  # No price available
        assert trade['total_cost'] is None  # No price available
        assert trade['cost_curr_quote_date'] is None  # No price available

        backend.close()

    def test_trade_cost_multiple_mixed_currencies(self):
        """Test get_trade_cost with multiple trades in different currencies."""
        backend = SqliteBackend(':memory:')

        # Trade 1: Buy 1.0 BTC for 50000 USD (direct)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
                'fee_curr': 'USD',
                'fee': 10.0,
                'exchange': 'Coinbase',
            }
        )

        # Trade 2: Buy 0.5 BTC for 22500 EUR (requires conversion)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-16 12:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'EUR',
                'sell': 22500.0,
                'fee_curr': 'EUR',
                'fee': 5.0,
                'exchange': 'Kraken',
            }
        )

        # Trade 3: Sell 0.3 BTC for 15600 USD (direct, negative quantity)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell, fee_curr, fee, exchange)
               VALUES (:createddate, :trans_type, :buy_curr, :buy, :sell_curr, :sell, :fee_curr, :fee, :exchange)""",
            {
                'createddate': '2025-01-17 14:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 15600.0,
                'sell_curr': 'BTC',
                'sell': 0.3,
                'fee_curr': 'USD',
                'fee': 3.0,
                'exchange': 'Coinbase',
            }
        )

        # Add EUR/USD price for second trade
        backend.execute(
            """INSERT INTO pair_price (date, from_curr, to_curr, price)
               VALUES (:date, :from_curr, :to_curr, :price)""",
            {
                'date': '2025-01-16 12:05:00',
                'from_curr': 'EUR',
                'to_curr': 'USD',
                'price': 1.12,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        cost_data = trade_query.get_trade_cost('BTC', 'USD')

        assert len(cost_data) == 3

        # First trade: direct USD
        assert cost_data[0]['date'] == '2025-01-15 10:00:00'
        assert cost_data[0]['quantity'] == 1.0
        assert cost_data[0]['unit_cost'] == 50000.0
        assert cost_data[0]['total_cost'] == 50000.0

        # Second trade: EUR converted to USD (45000 EUR/BTC * 1.12 = 50400 USD/BTC)
        assert cost_data[1]['date'] == '2025-01-16 12:00:00'
        assert cost_data[1]['quantity'] == 0.5
        assert cost_data[1]['trade_curr'] == 'EUR'
        assert cost_data[1]['unit_cost'] == pytest.approx(50400.0)  # 45000 * 1.12
        assert cost_data[1]['total_cost'] == pytest.approx(25200.0)  # 50400 * 0.5

        # Third trade: sell (negative quantity), direct USD
        assert cost_data[2]['date'] == '2025-01-17 14:00:00'
        assert cost_data[2]['quantity'] == -0.3
        assert cost_data[2]['unit_cost'] == 52000.0  # 15600 / 0.3
        assert cost_data[2]['total_cost'] == 15600.0  # 52000 * abs(-0.3)

        backend.close()

    def test_trade_cost_empty_trades(self):
        """Test get_trade_cost returns empty list when no trades exist."""
        backend = SqliteBackend(':memory:')

        trade_query = TradeQuery(backend)
        cost_data = trade_query.get_trade_cost('BTC', 'USD')

        assert cost_data == []

        backend.close()


class TestBasisCalculator:
    """Tests for BasisCalculator class."""

    def test_single_purchase_returns_that_price(self):
        """Test average price with single purchase returns that price."""
        backend = SqliteBackend(':memory:')

        # Insert a single purchase trade
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        assert avg_price == 50000.0

        backend.close()

    def test_multiple_purchases_returns_weighted_average(self):
        """Test average price with multiple purchases returns weighted average."""
        backend = SqliteBackend(':memory:')

        # Insert multiple purchase trades
        # Purchase 1: 1.0 BTC @ 50000 USD/BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
            }
        )

        # Purchase 2: 0.5 BTC @ 52000 USD/BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 26000.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        # Weighted average: (50000 * 1.0 + 52000 * 0.5) / (1.0 + 0.5)
        # = (50000 + 26000) / 1.5 = 76000 / 1.5 = 50666.67
        expected = (50000.0 * 1.0 + 52000.0 * 0.5) / 1.5
        assert avg_price == pytest.approx(expected)

        backend.close()

    def test_no_purchases_returns_none(self):
        """Test average price with only sales returns None."""
        backend = SqliteBackend(':memory:')

        # Insert a sale trade (BTC -> USD)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 52000.0,
                'sell_curr': 'BTC',
                'sell': 1.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        assert avg_price is None

        backend.close()

    def test_mixed_purchases_and_sales(self):
        """Test average price calculates only from purchases, ignoring sales."""
        backend = SqliteBackend(':memory:')

        # Purchase 1: 1.0 BTC @ 50000 USD/BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
            }
        )

        # Sale: 0.5 BTC @ 60000 USD/BTC (should be ignored)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'USD',
                'buy': 30000.0,
                'sell_curr': 'BTC',
                'sell': 0.5,
            }
        )

        # Purchase 2: 0.5 BTC @ 52000 USD/BTC
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-17 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'USD',
                'sell': 26000.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        # Should only average the two purchases: (50000 * 1.0 + 52000 * 0.5) / 1.5
        expected = (50000.0 * 1.0 + 52000.0 * 0.5) / 1.5
        assert avg_price == pytest.approx(expected)

        backend.close()

    def test_purchases_with_missing_price_data(self):
        """Test average price handles missing price data gracefully."""
        backend = SqliteBackend(':memory:')

        # Purchase 1: 1.0 BTC in USD (has price)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'USD',
                'sell': 50000.0,
            }
        )

        # Purchase 2: 0.5 BTC in EUR (will have missing price because no EUR/USD price)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-16 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 0.5,
                'sell_curr': 'EUR',
                'sell': 45000.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        # Should only average the purchase with available price data
        assert avg_price == 50000.0

        backend.close()

    def test_all_purchases_missing_price_data_returns_none(self):
        """Test average price returns None when all purchases lack price data."""
        backend = SqliteBackend(':memory:')

        # Purchase in EUR (no EUR/USD price available)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Trade',
                'buy_curr': 'BTC',
                'buy': 1.0,
                'sell_curr': 'EUR',
                'sell': 45000.0,
            }
        )
        backend.commit()

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        assert avg_price is None

        backend.close()

    def test_empty_ledger_returns_none(self):
        """Test average price returns None when no trades exist."""
        backend = SqliteBackend(':memory:')

        trade_query = TradeQuery(backend)
        basis_calc = BasisCalculator(trade_query)

        avg_price = basis_calc.get_avg_purchase_price('BTC', 'USD')

        assert avg_price is None

        backend.close()


class TestIncomeQuery:
    """Tests for IncomeQuery class."""

    def test_interest_income_with_price_data(self):
        """Test interest income with available price data."""
        backend = SqliteBackend(':memory:')

        # Add interest income transaction
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.001,
                'sell_curr': '',
                'sell': 0.0,
            }
        )

        # Add price data for BTC/USD
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from_curr, :to_curr, :price, :date)""",
            {
                'from_curr': 'BTC',
                'to_curr': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 10:05:00',
            }
        )
        backend.commit()

        income_query = IncomeQuery(backend)
        income = income_query.get_interest_income('BTC', 'USD')

        assert len(income) == 1
        assert income[0]['date'] == '2025-01-15 10:00:00'
        assert income[0]['to_curr'] == 'BTC'
        assert income[0]['to_quantity'] == 0.001
        assert income[0]['cost_curr'] == 'USD'
        assert income[0]['unit_cost'] == pytest.approx(50000.0)
        assert income[0]['total_cost'] == pytest.approx(50.0)
        assert income[0]['cost_curr_quote_date'] == '2025-01-15 10:05:00'

        backend.close()

    def test_interest_income_without_price_data(self):
        """Test interest income without price data returns None for costs."""
        backend = SqliteBackend(':memory:')

        # Add interest income transaction
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.001,
                'sell_curr': '',
                'sell': 0.0,
            }
        )
        # No price data available
        backend.commit()

        income_query = IncomeQuery(backend)
        income = income_query.get_interest_income('BTC', 'USD')

        assert len(income) == 1
        assert income[0]['date'] == '2025-01-15 10:00:00'
        assert income[0]['to_curr'] == 'BTC'
        assert income[0]['to_quantity'] == 0.001
        assert income[0]['cost_curr'] == 'USD'
        assert income[0]['unit_cost'] is None
        assert income[0]['total_cost'] is None
        assert income[0]['cost_curr_quote_date'] is None

        backend.close()

    def test_multiple_interest_income_entries(self):
        """Test multiple interest income transactions are returned in date order."""
        backend = SqliteBackend(':memory:')

        # Add multiple interest income transactions
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-10 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.001,
                'sell_curr': '',
                'sell': 0.0,
            }
        )
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-20 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.002,
                'sell_curr': '',
                'sell': 0.0,
            }
        )

        # Add price data
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from_curr, :to_curr, :price, :date)""",
            {
                'from_curr': 'BTC',
                'to_curr': 'USD',
                'price': 50000.0,
                'date': '2025-01-10 10:00:00',
            }
        )
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from_curr, :to_curr, :price, :date)""",
            {
                'from_curr': 'BTC',
                'to_curr': 'USD',
                'price': 52000.0,
                'date': '2025-01-20 10:00:00',
            }
        )
        backend.commit()

        income_query = IncomeQuery(backend)
        income = income_query.get_interest_income('BTC', 'USD')

        assert len(income) == 2
        # Verify ordered by date
        assert income[0]['date'] == '2025-01-10 10:00:00'
        assert income[0]['to_quantity'] == 0.001
        assert income[0]['unit_cost'] == pytest.approx(50000.0)
        assert income[0]['total_cost'] == pytest.approx(50.0)

        assert income[1]['date'] == '2025-01-20 10:00:00'
        assert income[1]['to_quantity'] == 0.002
        assert income[1]['unit_cost'] == pytest.approx(52000.0)
        assert income[1]['total_cost'] == pytest.approx(104.0)

        backend.close()

    def test_no_interest_income_returns_empty_list(self):
        """Test no interest income returns empty list."""
        backend = SqliteBackend(':memory:')

        income_query = IncomeQuery(backend)
        income = income_query.get_interest_income('BTC', 'USD')

        assert income == []

        backend.close()

    def test_interest_income_filters_by_coin(self):
        """Test interest income filters to specified coin only."""
        backend = SqliteBackend(':memory:')

        # Add BTC interest income
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.001,
                'sell_curr': '',
                'sell': 0.0,
            }
        )

        # Add ETH interest income
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'ETH',
                'buy': 0.01,
                'sell_curr': '',
                'sell': 0.0,
            }
        )
        backend.commit()

        income_query = IncomeQuery(backend)
        income = income_query.get_interest_income('BTC', 'USD')

        # Should only return BTC income
        assert len(income) == 1
        assert income[0]['to_curr'] == 'BTC'

        backend.close()

    def test_dividend_cost_delegates_to_interest_income(self):
        """Test get_dividend_cost returns same results as get_interest_income."""
        backend = SqliteBackend(':memory:')

        # Add interest income transaction
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy_curr, buy, sell_curr, sell)
               VALUES (:date, :trans_type, :buy_curr, :buy, :sell_curr, :sell)""",
            {
                'date': '2025-01-15 10:00:00',
                'trans_type': 'Interest Income',
                'buy_curr': 'BTC',
                'buy': 0.001,
                'sell_curr': '',
                'sell': 0.0,
            }
        )

        # Add price data
        backend.execute(
            """INSERT INTO pair_price (from_curr, to_curr, price, date)
               VALUES (:from_curr, :to_curr, :price, :date)""",
            {
                'from_curr': 'BTC',
                'to_curr': 'USD',
                'price': 50000.0,
                'date': '2025-01-15 10:05:00',
            }
        )
        backend.commit()

        income_query = IncomeQuery(backend)
        interest = income_query.get_interest_income('BTC', 'USD')
        dividends = income_query.get_dividend_cost('BTC', 'USD')

        # Should be identical
        assert interest == dividends

        backend.close()

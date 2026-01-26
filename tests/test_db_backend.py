"""Unit tests for database backend abstraction layer."""

import os
import pytest

from src.python.db import (
    BalanceCalculator,
    DatabaseBackend,
    DatabaseError,
    SqliteBackend,
    PostgresBackend,
    get_backend,
    create_tables,
    get_sqlite_path,
    PriceLookup,
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

    def test_get_sqlite_path_default(self):
        """Test get_sqlite_path returns default path."""
        # Clear env var to test default
        old_val = os.environ.pop('SQLITE_DB_PATH', None)

        try:
            path = get_sqlite_path()
            assert path.endswith('.cryptoaccounting/ledger.db')
            assert '~' not in path  # Should be expanded
        finally:
            if old_val:
                os.environ['SQLITE_DB_PATH'] = old_val

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

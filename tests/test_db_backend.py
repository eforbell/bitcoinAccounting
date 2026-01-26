"""Unit tests for database backend abstraction layer."""

import os
import pytest

from src.python.db import (
    DatabaseBackend,
    DatabaseError,
    SqliteBackend,
    PostgresBackend,
    get_backend,
)


class TestSqliteBackend:
    """Tests for SQLite backend using in-memory database."""

    def test_init_memory_database(self):
        """Test initialization with :memory: database."""
        backend = SqliteBackend(':memory:')
        assert backend.db_path == ':memory:'
        backend.close()

    def test_execute_returns_list_of_dicts(self):
        """Test execute returns list of dictionaries with column names."""
        backend = SqliteBackend(':memory:')

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
        backend = SqliteBackend(':memory:')

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
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        results = backend.execute("SELECT * FROM test")

        assert results == []

        backend.close()

    def test_execute_one_returns_dict(self):
        """Test execute_one returns single dictionary."""
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.commit()

        result = backend.execute_one("SELECT * FROM test WHERE id = :id", {'id': 1})

        assert isinstance(result, dict)
        assert result == {'id': 1, 'name': 'Alice'}

        backend.close()

    def test_execute_one_no_results_returns_none(self):
        """Test execute_one returns None when no rows match."""
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        result = backend.execute_one("SELECT * FROM test WHERE id = :id", {'id': 999})

        assert result is None

        backend.close()

    def test_execute_scalar_returns_value(self):
        """Test execute_scalar returns first column value."""
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.commit()

        result = backend.execute_scalar("SELECT name FROM test WHERE id = :id", {'id': 1})

        assert result == 'Alice'

        backend.close()

    def test_execute_scalar_with_count(self):
        """Test execute_scalar with COUNT query."""
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.execute("INSERT INTO test VALUES (1, 'Alice')")
        backend.execute("INSERT INTO test VALUES (2, 'Bob')")
        backend.commit()

        count = backend.execute_scalar("SELECT COUNT(*) FROM test")

        assert count == 2

        backend.close()

    def test_execute_scalar_no_results_returns_none(self):
        """Test execute_scalar returns None when no rows match."""
        backend = SqliteBackend(':memory:')

        backend.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        backend.commit()

        result = backend.execute_scalar("SELECT name FROM test WHERE id = :id", {'id': 999})

        assert result is None

        backend.close()

    def test_commit_and_rollback(self):
        """Test commit and rollback behavior."""
        backend = SqliteBackend(':memory:')

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
        backend = SqliteBackend(':memory:')

        with pytest.raises(DatabaseError, match="Query execution failed"):
            backend.execute("INVALID SQL SYNTAX")

        backend.close()

    def test_parent_directory_creation(self, tmp_path):
        """Test that parent directory is created if missing."""
        db_path = tmp_path / "subdir" / "test.db"

        backend = SqliteBackend(str(db_path))

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

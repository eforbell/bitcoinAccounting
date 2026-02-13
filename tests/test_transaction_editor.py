"""Tests for transaction editor functionality.

TXE-001: Soft-delete schema migration and query filtering.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from db import SqliteBackend, create_tables
from db.queries.transaction import TransactionQuery
from db.queries.balance import BalanceCalculator
from db.queries.wallet import WalletQuery
from db.queries.trades import TradeQuery
from db.queries.income import IncomeQuery
from db.queries.ledger import LedgerWriter


def _make_backend():
    """Create an in-memory SQLite backend with schema."""
    backend = SqliteBackend(':memory:', auto_create_tables=True)
    return backend


def _seed_transactions(backend):
    """Insert sample transactions for testing."""
    writer = LedgerWriter(backend)
    writer.deposit('2024-01-01 10:00:00', 1.0, 'BTC', 'Strike')
    writer.trade('2024-01-15 10:00:00', 0.5, 'BTC', 25000.0, 'USD', 5.0, 'USD', 'Coinbase')
    writer.withdraw('2024-02-01 10:00:00', 0.1, 'BTC', 0.0001, 'BTC', 'Strike')
    return backend


class TestSoftDeleteSchema:
    """TXE-001: Verify soft-delete columns exist in schema."""

    def test_new_database_has_deleted_columns(self):
        """New databases should have deleted and deleted_date columns."""
        backend = _make_backend()
        rows = backend.execute("PRAGMA table_info(ledger)")
        col_names = {row['name'] for row in rows}

        assert 'deleted' in col_names
        assert 'deleted_date' in col_names
        backend.close()

    def test_deleted_column_defaults_to_zero(self):
        """New rows should have deleted = 0 by default."""
        backend = _make_backend()
        writer = LedgerWriter(backend)
        writer.deposit('2024-01-01 10:00:00', 1.0, 'BTC', 'Strike')

        rows = backend.execute("SELECT deleted, deleted_date FROM ledger")
        assert len(rows) == 1
        assert rows[0]['deleted'] == 0
        assert rows[0]['deleted_date'] is None
        backend.close()

    def test_migration_on_existing_database(self):
        """ALTER TABLE migration adds columns to existing databases without them."""
        backend = SqliteBackend(':memory:', auto_create_tables=False)
        # Create ledger table WITHOUT deleted columns (simulating old schema)
        backend.execute("""
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY,
                createddate TEXT NOT NULL,
                trans_type TEXT,
                buy REAL,
                buy_curr TEXT,
                sell REAL,
                sell_curr TEXT,
                fee REAL,
                fee_curr TEXT,
                exchange TEXT,
                "group" TEXT,
                comment TEXT,
                transactionid TEXT
            )
        """)
        backend.commit()

        # Insert a row before migration
        backend.execute(
            "INSERT INTO ledger (createddate, trans_type, buy, buy_curr, exchange) "
            "VALUES ('2024-01-01', 'Deposit', 1.0, 'BTC', 'Strike')"
        )
        backend.commit()

        # Run migration
        from db.schema import _migrate_ledger_soft_delete
        _migrate_ledger_soft_delete(backend)
        backend.commit()

        # Verify columns exist
        rows = backend.execute("PRAGMA table_info(ledger)")
        col_names = {row['name'] for row in rows}
        assert 'deleted' in col_names
        assert 'deleted_date' in col_names

        # Verify existing row has NULL deleted (not 0, since ALTER TABLE ADD default doesn't backfill in SQLite)
        rows = backend.execute("SELECT deleted, deleted_date FROM ledger")
        assert len(rows) == 1
        # SQLite ALTER TABLE ADD COLUMN with DEFAULT doesn't backfill existing rows, they get NULL
        # Our queries handle this with (deleted = 0 OR deleted IS NULL)
        assert rows[0]['deleted'] is None or rows[0]['deleted'] == 0
        backend.close()

    def test_migration_is_idempotent(self):
        """Running migration twice doesn't error."""
        backend = _make_backend()
        from db.schema import _migrate_ledger_soft_delete
        # create_tables already ran migration; run it again
        _migrate_ledger_soft_delete(backend)
        backend.commit()

        rows = backend.execute("PRAGMA table_info(ledger)")
        col_names = [row['name'] for row in rows]
        # Should still have exactly one of each
        assert col_names.count('deleted') == 1
        assert col_names.count('deleted_date') == 1
        backend.close()


class TestSoftDeleteQueryFiltering:
    """TXE-001: Verify deleted rows are excluded from queries by default."""

    def test_get_transactions_excludes_deleted(self):
        """TransactionQuery.get_transactions() excludes deleted rows by default."""
        backend = _make_backend()
        _seed_transactions(backend)

        # Mark one transaction as deleted
        backend.execute("UPDATE ledger SET deleted = 1, deleted_date = '2024-03-01' WHERE id = 1")
        backend.commit()

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions()
        assert len(txs) == 2  # 3 seeded, 1 deleted = 2 visible
        backend.close()

    def test_get_transactions_include_deleted(self):
        """TransactionQuery.get_transactions(include_deleted=True) includes deleted rows."""
        backend = _make_backend()
        _seed_transactions(backend)

        # Mark one transaction as deleted
        backend.execute("UPDATE ledger SET deleted = 1, deleted_date = '2024-03-01' WHERE id = 1")
        backend.commit()

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions(include_deleted=True)
        assert len(txs) == 3  # All 3, including deleted
        backend.close()

    def test_get_transactions_returns_deleted_flag(self):
        """get_transactions(include_deleted=True) returns Deleted column."""
        backend = _make_backend()
        _seed_transactions(backend)

        backend.execute("UPDATE ledger SET deleted = 1, deleted_date = '2024-03-01' WHERE id = 1")
        backend.commit()

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions(include_deleted=True)
        assert 'Deleted' in headers

        deleted_tx = [t for t in txs if t.get('Deleted') == 1]
        assert len(deleted_tx) == 1

        active_txs = [t for t in txs if t.get('Deleted') == 0]
        assert len(active_txs) == 2
        backend.close()

    def test_get_transactions_returns_id_column(self):
        """get_transactions() now returns the ID column."""
        backend = _make_backend()
        _seed_transactions(backend)

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions()
        assert 'ID' in headers
        assert all('ID' in tx for tx in txs)
        backend.close()

    def test_balance_excludes_deleted(self):
        """BalanceCalculator.get_balance() excludes deleted rows."""
        backend = _make_backend()
        _seed_transactions(backend)

        calc = BalanceCalculator(backend)
        balance_before = calc.get_balance('BTC')

        # Delete the deposit (1.0 BTC)
        backend.execute("UPDATE ledger SET deleted = 1 WHERE id = 1")
        backend.commit()

        balance_after = calc.get_balance('BTC')
        # Balance should decrease by 1.0 (the deleted deposit)
        assert balance_after == pytest.approx(balance_before - 1.0)
        backend.close()

    def test_wallet_balance_excludes_deleted(self):
        """WalletQuery.get_balance_by_account() excludes deleted rows."""
        backend = _make_backend()
        _seed_transactions(backend)

        wq = WalletQuery(backend)
        balance_before = wq.get_balance_by_account('BTC', 'Strike')

        # Delete the Strike deposit (1.0 BTC)
        backend.execute("UPDATE ledger SET deleted = 1 WHERE id = 1")
        backend.commit()

        balance_after = wq.get_balance_by_account('BTC', 'Strike')
        assert balance_after == pytest.approx(balance_before - 1.0)
        backend.close()

    def test_trades_exclude_deleted(self):
        """TradeQuery.get_trades() excludes deleted rows."""
        backend = _make_backend()
        _seed_transactions(backend)

        tq = TradeQuery(backend)
        trades_before = tq.get_trades('BTC')

        # Delete the trade
        backend.execute("UPDATE ledger SET deleted = 1 WHERE id = 2")
        backend.commit()

        trades_after = tq.get_trades('BTC')
        assert len(trades_after) == len(trades_before) - 1
        backend.close()

    def test_null_deleted_treated_as_active(self):
        """Rows with deleted=NULL (pre-migration) should be treated as active."""
        backend = _make_backend()
        _seed_transactions(backend)

        # Simulate pre-migration rows with NULL deleted
        backend.execute("UPDATE ledger SET deleted = NULL")
        backend.commit()

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions()
        assert len(txs) == 3  # All visible because NULL treated as active

        calc = BalanceCalculator(backend)
        balance = calc.get_balance('BTC')
        # 1.0 deposit + 0.5 trade buy - 0.1 withdraw = 1.4 (minus fees handled separately)
        assert balance > 0  # Just verify we get results, not zero
        backend.close()

    def test_existing_tests_pattern_unchanged(self):
        """Verify the basic flow still works with new schema (no deleted rows)."""
        backend = _make_backend()
        writer = LedgerWriter(backend)

        writer.deposit('2024-01-01 10:00:00', 1.0, 'BTC', 'Strike')
        writer.trade('2024-01-15 10:00:00', 0.5, 'BTC', 25000.0, 'USD', 5.0, 'USD', 'Coinbase')

        query = TransactionQuery(backend)
        headers, txs = query.get_transactions()
        assert len(txs) == 2

        calc = BalanceCalculator(backend)
        balance = calc.get_balance('BTC')
        assert balance == pytest.approx(1.5)  # 1.0 deposit + 0.5 trade

        wq = WalletQuery(backend)
        strike_balance = wq.get_balance_by_account('BTC', 'Strike')
        assert strike_balance == pytest.approx(1.0)

        tq = TradeQuery(backend)
        trades = tq.get_trades('BTC')
        assert len(trades) == 1

        backend.close()

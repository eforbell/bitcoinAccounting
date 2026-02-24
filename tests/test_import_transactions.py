"""Comprehensive tests for CryptoAccounts.import_transactions() method.

Tests cover all transaction types, error handling, type normalization,
and USD equivalent price pair storage.

REFACTOR-007: Add comprehensive test coverage for import_transactions()
"""
import sys
import os
from datetime import datetime
import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from bitcoinAccounts import CryptoAccounts
from db import SqliteBackend


class TestImportTransactionsBasic:
    """Test basic import_transactions functionality with valid data."""

    def test_import_deposit(self) -> None:
        """Test importing a Deposit transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 10:00:00',
                'buy': 1000.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Test deposit'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert crypto.get_balance('USD') == 1000.0

        crypto.close()

    def test_import_withdrawal(self) -> None:
        """Test importing a Withdrawal transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add initial balance
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')

        # Note: Fees are included in sell amount (see transfer_funds implementation)
        # To withdraw 0.5 BTC with 0.0001 fee, pass sell=0.5001
        transactions = [
            {
                'trans_type': 'Withdrawal',
                'created_date': '2025-01-02 10:00:00',
                'sell': 0.5001,  # Amount including fee
                'sell_curr': 'BTC',
                'fee': 0.0001,
                'fee_curr': 'BTC',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Test withdrawal'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        # Balance should be 1.0 - 0.5001 (withdrawal including fee) = 0.4999
        assert crypto.get_balance('BTC') == pytest.approx(0.4999)

        crypto.close()

    def test_import_spend(self) -> None:
        """Test importing a Spend transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add initial balance
        crypto.deposit(exchange='Coldcard', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')

        # Note: Fees are included in sell amount
        transactions = [
            {
                'trans_type': 'Spend',
                'created_date': '2025-01-02 10:00:00',
                'sell': 0.10005,  # Amount including fee
                'sell_curr': 'BTC',
                'fee': 0.00005,
                'fee_curr': 'BTC',
                'exchange': 'Coldcard',
                'group': '',
                'comment': 'Payment for services'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        # Balance should be 0.5 - 0.10005 (spend including fee) = 0.39995
        assert crypto.get_balance('BTC') == pytest.approx(0.39995)

        crypto.close()

    def test_import_trade(self) -> None:
        """Test importing a Trade transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add initial USD balance
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=50000, buy_curr='USD')

        # Note: For trades, the fee is in the buy currency and reduces the received amount
        # If you buy 1.0 BTC with 0.0001 BTC fee, you receive net 0.9999 BTC
        # But the buy amount should include the gross amount before fee
        transactions = [
            {
                'trans_type': 'Trade',
                'created_date': '2025-01-01 12:00:00',
                'buy': 0.9999,  # Net amount after fee
                'buy_curr': 'BTC',
                'sell': 50000,
                'sell_curr': 'USD',
                'fee': 0.0001,
                'fee_curr': 'BTC',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Test trade'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        # BTC balance should be 0.9999 (what we bought)
        assert crypto.get_balance('BTC') == pytest.approx(0.9999)
        assert crypto.get_balance('USD') == 0.0

        crypto.close()

    def test_import_mining(self) -> None:
        """Test importing a Mining transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Mining',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.01,
                'buy_curr': 'BTC',
                'exchange': 'Mining Pool',
                'group': '',
                'comment': 'Block reward',
                'transactionid': 'abc123'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert crypto.get_balance('BTC') == 0.01

        crypto.close()

    def test_import_interest_income(self) -> None:
        """Test importing an Interest Income transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest Income',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.001,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Staking rewards'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert crypto.get_balance('BTC') == 0.001

        crypto.close()


class TestImportTransactionsAliases:
    """Test transaction type alias normalization."""

    def test_interest_alias_normalized(self) -> None:
        """Test that 'Interest' is normalized to 'Interest Income'."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.002,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Interest payment'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert crypto.get_balance('BTC') == 0.002

        crypto.close()

    def test_staking_alias_normalized(self) -> None:
        """Test that 'Staking' is normalized to 'Interest Income'."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Staking',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.003,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Staking rewards'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert crypto.get_balance('BTC') == 0.003

        crypto.close()


class TestImportTransactionsUSDEquivalent:
    """Test USD equivalent price pair storage for interest income."""

    def test_usd_equivalent_stored_for_interest_income(self) -> None:
        """Test that USD equivalent is stored as price pair for Interest Income."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest Income',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.001,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Staking rewards',
                'usd_equivalent': 50.0  # $50 for 0.001 BTC = $50000/BTC
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0

        # Check that price pair was stored
        price_query = "SELECT * FROM pair_price WHERE from_curr = 'BTC' AND to_curr = 'USD' AND date = '2025-01-01 10:00:00'"
        prices = backend.execute(price_query)

        assert len(prices) == 1
        assert prices[0]['price'] == 50000.0  # $50 / 0.001 BTC

        crypto.close()

    def test_usd_equivalent_with_dollar_sign(self) -> None:
        """Test USD equivalent parsing with dollar sign and comma."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest Income',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.01,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Interest',
                'usd_equivalent': '$1,000.50'  # $1000.50 for 0.01 BTC
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 0

        # Check that price pair was stored correctly
        price_query = "SELECT * FROM pair_price WHERE from_curr = 'BTC' AND to_curr = 'USD'"
        prices = backend.execute(price_query)

        assert len(prices) == 1
        assert prices[0]['price'] == pytest.approx(100050.0)  # $1000.50 / 0.01 BTC

        crypto.close()

    def test_usd_equivalent_for_interest_alias(self) -> None:
        """Test USD equivalent works with 'Interest' alias."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.002,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Interest',
                'usd_equivalent': 100.0
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        # Check price pair stored
        price_query = "SELECT COUNT(*) as count FROM pair_price WHERE from_curr = 'BTC'"
        count = backend.execute_scalar(price_query)
        assert count == 1

        crypto.close()

    def test_usd_equivalent_zero_buy_amount_skipped(self) -> None:
        """Test that USD equivalent is skipped when buy amount is zero."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Interest Income',
                'created_date': '2025-01-01 10:00:00',
                'buy': 0.0,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Zero amount test',
                'usd_equivalent': 100.0
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        # Check NO price pair stored (division by zero avoided)
        price_query = "SELECT COUNT(*) as count FROM pair_price WHERE from_curr = 'BTC'"
        count = backend.execute_scalar(price_query)
        assert count == 0

        crypto.close()


class TestImportTransactionsSkipped:
    """Test skipped transaction handling."""

    def test_unknown_transaction_type_skipped(self) -> None:
        """Test that unknown transaction types increment skipped counter."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'UnknownType',
                'created_date': '2025-01-01 10:00:00',
                'exchange': 'Test'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 0
        assert result['skipped'] == 1

        crypto.close()

    def test_mixed_valid_and_unknown(self) -> None:
        """Test batch with both valid and unknown transaction types."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 10:00:00',
                'buy': 1000.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Valid'
            },
            {
                'trans_type': 'InvalidType',
                'created_date': '2025-01-01 11:00:00',
                'exchange': 'Test'
            },
            {
                'trans_type': 'Mining',
                'created_date': '2025-01-01 12:00:00',
                'buy': 0.01,
                'buy_curr': 'BTC',
                'exchange': 'Pool',
                'group': '',
                'comment': 'Valid',
                'transactionid': 'abc'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 2
        assert result['skipped'] == 1
        assert crypto.get_balance('USD') == 1000.0
        assert crypto.get_balance('BTC') == 0.01

        crypto.close()


class TestImportTransactionsErrorHandling:
    """Test error handling during import (REFACTOR-006 feature)."""

    def test_error_handling_prevents_batch_failure(self) -> None:
        """Test that error handling exists and batch continues after errors."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Create a transaction that will cause a database constraint error
        # by having None for required fields (backend will reject)
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 10:00:00',
                'buy': 100.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Valid #1'
            },
            {
                'trans_type': 'Deposit',
                'created_date': None,  # None will cause issues
                'buy': None,
                'buy_curr': None,
                'exchange': None,
                'group': '',
                'comment': 'Malformed - should be caught'
            },
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 12:00:00',
                'buy': 300.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Valid #2'
            }
        ]

        result = crypto.import_transactions(transactions)

        # With error handling, first and third succeed, second fails gracefully
        # (Without error handling, the entire batch would fail)
        assert result['imported'] == 2
        assert result['skipped'] == 1
        assert crypto.get_balance('USD') == 400.0  # 100 + 300

        crypto.close()


class TestImportTransactionsBatch:
    """Test batch import functionality."""

    def test_import_multiple_transaction_types(self) -> None:
        """Test importing a batch with multiple transaction types."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 10:00:00',
                'buy': 50000.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Initial deposit'
            },
            {
                'trans_type': 'Trade',
                'created_date': '2025-01-01 11:00:00',
                'buy': 0.9999,  # Net BTC received (after fee)
                'buy_curr': 'BTC',
                'sell': 50000.0,
                'sell_curr': 'USD',
                'fee': 0.0001,
                'fee_curr': 'BTC',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Buy BTC'
            },
            {
                'trans_type': 'Withdrawal',
                'created_date': '2025-01-01 12:00:00',
                'sell': 0.50005,  # Including fee
                'sell_curr': 'BTC',
                'fee': 0.00005,
                'fee_curr': 'BTC',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Move to cold storage'
            },
            {
                'trans_type': 'Deposit',
                'created_date': '2025-01-01 12:10:00',
                'buy': 0.5,
                'buy_curr': 'BTC',
                'exchange': 'Coldcard',
                'group': '',
                'comment': 'Cold storage'
            },
            {
                'trans_type': 'Interest',
                'created_date': '2025-01-02 10:00:00',
                'buy': 0.001,
                'buy_curr': 'BTC',
                'exchange': 'River',
                'group': '',
                'comment': 'Interest rewards'
            }
        ]

        result = crypto.import_transactions(transactions)

        assert result['imported'] == 5
        assert result['skipped'] == 0

        # Calculate expected balance:
        # Trade: 0.9999 BTC received (net after fee in buy amount)
        # Withdrawal: -0.50005 BTC (including fee in sell amount)
        # Deposit: +0.5 BTC
        # Interest: +0.001 BTC
        # Total: 0.9999 - 0.50005 + 0.5 + 0.001 = 1.00085 BTC
        expected_btc = 0.9999 - 0.50005 + 0.5 + 0.001
        assert crypto.get_balance('BTC') == pytest.approx(expected_btc)

        crypto.close()

    def test_empty_batch(self) -> None:
        """Test importing empty transaction list."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        result = crypto.import_transactions([])

        assert result['imported'] == 0
        assert result['skipped'] == 0

        crypto.close()

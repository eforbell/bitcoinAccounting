"""Tests for CLI entry point and import workflow (IMP-003)."""

import sys
import pytest
import tempfile
import os
import subprocess
import csv as csv_mod
from pathlib import Path

from imports.base import BaseImporter
from imports.registry import register, get_parser, clear_registry
from imports.validation import validate_batch, detect_duplicates
from db import SqliteBackend
from cryptoAccounts import CryptoAccounts


SCRIPT_PATH = Path(__file__).parent.parent / "src" / "scripts" / "import_csv"


class _TestExchangeImporter(BaseImporter):
    """Test exchange parser for IMP-003 integration tests.

    Reads a simple CSV with columns: date, type, amount, currency, usd_amount, fee, comment, txid
    Transaction types: buy, deposit, send, interest, mining
    """
    name = "TestExchange"
    source_type = "exchange"
    description = "Simple test parser for integration tests"
    expected_columns = ["date", "type", "amount", "currency"]

    def parse(self, file_path, wallet_name=None, withdraw_to=None):
        transactions = []
        with open(file_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                tx_type = row['type']
                if tx_type == 'buy':
                    transactions.append({
                        'trans_type': 'Trade',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'sell': float(row.get('usd_amount') or 0),
                        'sell_curr': 'USD',
                        'fee': float(row.get('fee') or 0),
                        'fee_curr': 'USD',
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'deposit':
                    transactions.append({
                        'trans_type': 'Deposit',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'send':
                    transactions.append({
                        'trans_type': 'Withdrawal',
                        'created_date': row['date'],
                        'exchange': self._get_withdrawal_exchange(withdraw_to),
                        'sell': float(row['amount']),
                        'sell_curr': row['currency'],
                        'fee': float(row.get('fee') or 0),
                        'fee_curr': row['currency'],
                        'comment': self._get_withdrawal_comment(withdraw_to, row.get('comment', '')),
                        'group': '',
                    })
                elif tx_type == 'interest':
                    transactions.append({
                        'trans_type': 'Interest Income',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'mining':
                    transactions.append({
                        'trans_type': 'Mining',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                        'transactionid': row.get('txid', ''),
                    })
        colnames = ['trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
                    'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment', 'transactionid']
        return colnames, transactions


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestImportCSVCli:
    """CLI behavior tests for import_csv script via subprocess."""

    def test_help_flag(self):
        """--help exits 0 and shows all flags."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0
        assert "--list" in result.stdout
        assert "--source" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--withdraw-to" in result.stdout
        assert "--format" in result.stdout

    def test_list_flag_exits_0(self):
        """--list exits 0 even with no parsers registered."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--list"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0

    def test_no_args_exits_1(self):
        """No arguments prints FILE required error and exits 1."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH)],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "FILE is required" in result.stderr

    def test_file_not_found_exits_1(self):
        """Nonexistent file path exits 1 with not found message."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "/no/such/file.csv"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_unknown_source_exits_1(self):
        """--source with unregistered parser name exits 1."""
        csv_path = _make_csv("a,b\n1,2\n")
        try:
            result = subprocess.run(
                [".venv/bin/python", str(SCRIPT_PATH), "--source", "bogus", csv_path],
                capture_output=True, text=True,
                cwd=Path(__file__).parent.parent
            )
            assert result.returncode == 1
            assert "Unknown parser" in result.stderr
        finally:
            os.unlink(csv_path)

    def test_format_unknown_parser_exits_1(self):
        """--format with unregistered parser name exits 1."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--format", "bogus"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "Unknown parser" in result.stderr


class TestImportWorkflow:
    """Integration tests for the full import pipeline (IMP-003).

    Uses _TestExchangeImporter with in-memory SQLite to exercise the same
    code paths the import_csv script orchestrates.
    """

    def setup_method(self):
        clear_registry()
        register(_TestExchangeImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_import_deposit(self):
        """Parse deposit CSV, validate, import, verify in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[0]['buy'] == 0.5

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['buy'] == 0.5
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['exchange'] == 'TestExchange'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_trade(self):
        """Parse trade CSV, import, verify Trade row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Trade'

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Trade'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.1)
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['sell'] == pytest.approx(5000.0)
            assert rows[0]['sell_curr'] == 'USD'
            assert rows[0]['fee'] == pytest.approx(25.0)
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_withdrawal_with_withdraw_to(self):
        """Withdrawal with withdraw_to sets exchange to wallet name, no review comment."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
            assert transactions[0]['exchange'] == 'Ledger'
            assert transactions[0]['comment'] == ''

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert rows[0]['exchange'] == 'Ledger'
            assert rows[0]['sell'] == pytest.approx(0.2)
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_withdrawal_without_withdraw_to(self):
        """Withdrawal without withdraw_to uses placeholder exchange and adds review comment."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to=None)

            assert transactions[0]['exchange'] == 'TestExchange-Withdrawal'
            assert 'Review: Verify destination wallet' in transactions[0]['comment']
        finally:
            os.unlink(csv_path)

    def test_import_interest_income(self):
        """Parse interest CSV, import, verify Interest Income row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,interest,0.001,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert transactions[0]['trans_type'] == 'Interest Income'

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Interest Income'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.001)
            assert rows[0]['buy_curr'] == 'BTC'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_duplicate_detection(self):
        """Second parse of same deposit detected as duplicate."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            # Re-parse same CSV — should now be detected as duplicate
            _, transactions2 = parser.parse(csv_path)
            duplicates = detect_duplicates(transactions2, backend)
            assert len(duplicates) == 1
            assert duplicates[0]['trans_type'] == 'Deposit'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_validation_catches_missing_fields(self):
        """validate_batch rejects transactions missing required fields."""
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-03-15',
                'exchange': 'TestExchange',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                # Missing trans_type, created_date, exchange
            },
        ]
        result = validate_batch(transactions)
        assert not result.is_valid
        assert result.valid_count == 1
        assert result.error_count == 1

    def test_empty_csv_produces_no_transactions(self):
        """CSV with only a header row produces zero transactions."""
        csv_path = _make_csv("date,type,amount,currency\n")
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_multiple_transaction_types_in_one_file(self):
        """Mixed transaction types all import correctly."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25\n"
            "2024-03-16 11:00:00,deposit,0.05,BTC,,\n"
            "2024-03-17 12:00:00,interest,0.001,BTC,,\n"
            "2024-03-18 13:00:00,send,0.02,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to="ColdStorage")

            assert len(transactions) == 4
            types = {tx['trans_type'] for tx in transactions}
            assert types == {'Trade', 'Deposit', 'Interest Income', 'Withdrawal'}

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger")
            assert len(rows) == 4
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_mining(self):
        """Parse mining CSV, import, verify Mining row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment,txid\n"
            "2024-03-15 10:00:00,mining,0.00001,BTC,,,,abc123def\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Mining'
            assert transactions[0]['transactionid'] == 'abc123def'

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.00001)
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['transactionid'] == 'abc123def'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_mining_without_txid(self):
        """Mining without transactionid still imports (empty string)."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,mining,0.00002,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['transactionid'] == ''
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_returns_counts(self):
        """import_transactions returns dict with imported and skipped counts."""
        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)

        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-03-15',
                'exchange': 'Test',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                'trans_type': 'UnknownType',  # Will be skipped
                'created_date': '2024-03-16',
                'exchange': 'Test',
            },
        ]
        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 1
        crypto.close()


class TestCommentPreservation:
    """Tests verifying comments are stored in DB for all transaction types."""

    def setup_method(self):
        clear_registry()
        register(_TestExchangeImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_trade_comment_stored(self):
        """Trade transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25,DCA purchase\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Trade'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'DCA purchase'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_deposit_comment_stored(self):
        """Deposit transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC,,,Transfer from cold storage\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Transfer from cold storage'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_withdrawal_comment_stored(self):
        """Withdrawal transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001,To Ledger Nano\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'To Ledger Nano'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_withdrawal_review_comment_stored(self):
        """Withdrawal without withdraw_to stores review comment in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001,\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert 'Review: Verify destination wallet' in rows[0]['comment']
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_interest_income_comment_stored(self):
        """Interest Income transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,interest,0.001,BTC,,,Gemini Earn reward\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Interest Income'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Gemini Earn reward'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_mining_comment_stored(self):
        """Mining transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment,txid\n"
            "2024-03-15 10:00:00,mining,0.00001,BTC,,,Pool payout,block123\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Pool payout'
            crypto.close()
        finally:
            os.unlink(csv_path)



class TestWalletImportRequirements:
    """Tests for wallet import --wallet-name requirement."""

    def setup_method(self):
        clear_registry()

    def teardown_method(self):
        clear_registry()

    def test_wallet_import_without_wallet_name_exits_1(self):
        """Wallet imports without --wallet-name should fail with exit code 1."""
        # Create a temporary Ledger CSV
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.01,0,abc123,Bitcoin 1,xpub123,USD,500.00,51000.00\n"
        )
        
        try:
            # Import the Ledger parser
            from imports.wallets.ledger import LedgerImporter
            register(LedgerImporter)
            
            # Run import_csv without --wallet-name
            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--source", "ledger", csv_path],
                capture_output=True,
                text=True,
            )
            
            assert result.returncode == 1
            assert "require --wallet-name" in result.stderr
        finally:
            os.unlink(csv_path)

    def test_wallet_import_with_wallet_name_succeeds(self):
        """Wallet imports with --wallet-name should succeed via programmatic import."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.01,0,abc123,Bitcoin 1,xpub123,USD,500.00,51000.00\n"
        )

        try:
            from imports.wallets.ledger import LedgerImporter
            register(LedgerImporter)

            parser = get_parser("ledger")
            _, transactions = parser.parse(csv_path, wallet_name="MyLedger")

            assert len(transactions) == 1
            assert transactions[0]['exchange'] == 'MyLedger'
            assert transactions[0]['trans_type'] == 'Deposit'

            # Verify it imports to database correctly
            backend = SqliteBackend(':memory:', auto_create_tables=True)
            crypto = CryptoAccounts(backend=backend)
            result = crypto.import_transactions(transactions)

            assert result['imported'] == 1
            rows = backend.execute("SELECT exchange FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['exchange'] == 'MyLedger'

            crypto.close()
        finally:
            os.unlink(csv_path)

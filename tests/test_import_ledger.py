"""Tests for the Ledger Live parser (WAL-002)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.wallets.ledger import LedgerImporter
from imports.registry import register, get_parser, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from cryptoAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestLedgerImporterDetection:
    """Tests for LedgerImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(LedgerImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_ledger_format(self):
        """detect() returns True for a file with Ledger Live columns."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.01,0,abc123,Bitcoin 1,xpub123,USD,500.00,51000.00\n"
        )
        try:
            parser = LedgerImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = LedgerImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_exchange_format(self):
        """detect() returns False for exchange format CSV."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD\n"
        )
        try:
            parser = LedgerImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "OPERATION DATE,CURRENCY,OPERATION TYPE,AMOUNT,FEES,HASH,ACCOUNT NAME,XPUB,"
            "COST CURRENCY,COST,COST AT EXPORT\n"
            "2024-01-15 10:30:00,BTC,IN,0.01,0,abc123,Bitcoin 1,xpub123,USD,500.00,51000.00\n"
        )
        try:
            parser = LedgerImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)


class TestLedgerImporterParsing:
    """Tests for LedgerImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(LedgerImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped ledger_sample.csv fixture end-to-end."""
        parser = LedgerImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "ledger_sample.csv"))

        # Should have 4 BTC transactions (the ETH one is filtered out)
        assert len(transactions) == 4

        # Verify first IN transaction
        deposit_tx = transactions[0]
        assert deposit_tx['trans_type'] == 'Deposit'
        assert deposit_tx['buy'] == pytest.approx(0.01)
        assert deposit_tx['buy_curr'] == 'BTC'
        assert deposit_tx['exchange'] == 'Ledger'

        # Verify first OUT transaction
        withdrawal_tx = transactions[1]
        assert withdrawal_tx['trans_type'] == 'Withdrawal'
        assert withdrawal_tx['sell'] == pytest.approx(0.005)
        assert withdrawal_tx['sell_curr'] == 'BTC'
        assert withdrawal_tx['fee'] == pytest.approx(0.00001)
        assert withdrawal_tx['fee_curr'] == 'BTC'

    def test_parse_incoming_transaction(self):
        """IN operation maps to Deposit."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.025,0,hash123,Bitcoin 1,xpub123,USD,1250.00,50000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.025)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Ledger'
            assert tx['created_date'] == '2024-01-15 10:30:00'
        finally:
            os.unlink(csv_path)

    def test_parse_incoming_with_wallet_name(self):
        """IN operation with wallet_name uses specified name."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.025,0,hash123,Bitcoin 1,xpub123,USD,1250.00,50000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path, wallet_name="MyLedger")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'MyLedger'
        finally:
            os.unlink(csv_path)

    def test_parse_outgoing_transaction(self):
        """OUT operation maps to Withdrawal."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-01 14:00:00,BTC,OUT,-0.01,0.00001,hash456,Bitcoin 1,xpub123,USD,520.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.01)  # abs() applied
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.00001)
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_parse_outgoing_with_withdraw_to(self):
        """OUT transaction with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-15 09:00:00,BTC,OUT,-0.005,0.000005,hash789,Bitcoin 1,xpub123,USD,260.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Coldcard")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard'
            assert tx['comment'] == ''  # No review note when withdraw_to specified
        finally:
            os.unlink(csv_path)

    def test_parse_outgoing_without_withdraw_to(self):
        """OUT transaction without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-15 09:00:00,BTC,OUT,-0.005,0.000005,hash789,Bitcoin 1,xpub123,USD,260.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Ledger-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_filters_non_btc_transactions(self):
        """Non-BTC transactions are filtered out."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,ETH,IN,1.0,0,hash1,Ethereum 1,xpub456,USD,3000.00,3000.00\n"
            "2024-01-16 10:30:00,BTC,IN,0.01,0,hash2,Bitcoin 1,xpub123,USD,500.00,50000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_skips_zero_amount_transactions(self):
        """Transactions with zero amount are skipped."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0,0,hash1,Bitcoin 1,xpub123,USD,0.00,50000.00\n"
            "2024-01-16 10:30:00,BTC,IN,0.01,0,hash2,Bitcoin 1,xpub123,USD,500.00,50000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.01)
        finally:
            os.unlink(csv_path)

    def test_handles_zero_fee_withdrawal(self):
        """Withdrawal with zero fee has empty fee_curr."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-01 14:00:00,BTC,OUT,-0.01,0,hash456,Bitcoin 1,xpub123,USD,520.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_missing_fees_column(self):
        """Gracefully handles CSV with missing Fees column."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-01 14:00:00,BTC,OUT,-0.01,hash456,Bitcoin 1,xpub123,USD,520.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)


class TestLedgerImporterRegistration:
    """Tests for LedgerImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(LedgerImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """LedgerImporter is retrievable by name 'ledger'."""
        parser = get_parser("ledger")
        assert parser is not None
        assert isinstance(parser, LedgerImporter)

    def test_source_type_is_wallet(self):
        """source_type is 'wallet'."""
        parser = LedgerImporter()
        assert parser.source_type == "wallet"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Ledger columns."""
        parser = LedgerImporter()
        help_text = parser.get_format_help()
        assert "Ledger" in help_text
        assert "Operation Date" in help_text
        assert "Operation Type" in help_text
        assert "xpub" in help_text


class TestLedgerImporterIntegration:
    """Integration tests for Ledger parser with database import."""

    def setup_method(self):
        clear_registry()
        register(LedgerImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Ledger CSV and import all transactions to database."""
        parser = LedgerImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "ledger_sample.csv"), withdraw_to="Coldcard")

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 4
        assert import_result['skipped'] == 0

        # Verify all types imported
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Deposit', 0) == 2
        assert type_counts.get('Withdrawal', 0) == 2

        crypto.close()

    def test_withdrawal_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-02-15 09:00:00,BTC,OUT,-0.005,0.000005,hash789,Bitcoin 1,xpub123,USD,260.00,52000.00\n"
        )
        try:
            parser = LedgerImporter()
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

"""Tests for the Trezor Suite parser (WAL-003)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.wallets.trezor import TrezorImporter
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


class TestTrezorImporterDetection:
    """Tests for TrezorImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(TrezorImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_trezor_format(self):
        """detect() returns True for a file with Trezor Suite columns."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,recv,0.01,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,abc123\n"
        )
        try:
            parser = TrezorImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = TrezorImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_ledger_format(self):
        """detect() returns False for Ledger format (uses 'hash' not 'tx id')."""
        csv_path = _make_csv(
            "Operation Date,Currency,Operation Type,Amount,Fees,Hash,Account Name,xpub,"
            "Cost Currency,Cost,Cost at Export\n"
            "2024-01-15 10:30:00,BTC,IN,0.01,0,abc123,Bitcoin 1,xpub123,USD,500.00,51000.00\n"
        )
        try:
            parser = TrezorImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "DATE,TIME,TYPE,AMOUNT,FEE,ADDRESS,TX ID\n"
            "2024-01-15,10:30:00,recv,0.01,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,abc123\n"
        )
        try:
            parser = TrezorImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)


class TestTrezorImporterParsing:
    """Tests for TrezorImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(TrezorImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped trezor_sample.csv fixture end-to-end."""
        parser = TrezorImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "trezor_sample.csv"))

        # Should have 5 transactions (2 recv, 1 received, 2 sent)
        assert len(transactions) == 5

        # Verify first recv transaction
        deposit_tx = transactions[0]
        assert deposit_tx['trans_type'] == 'Deposit'
        assert deposit_tx['buy'] == pytest.approx(0.5)
        assert deposit_tx['buy_curr'] == 'BTC'
        assert deposit_tx['exchange'] == 'Trezor'
        assert deposit_tx['created_date'] == '2024-01-15 14:30:00'

        # Verify first sent transaction
        withdrawal_tx = transactions[1]
        assert withdrawal_tx['trans_type'] == 'Withdrawal'
        assert withdrawal_tx['sell'] == pytest.approx(0.2)
        assert withdrawal_tx['sell_curr'] == 'BTC'
        assert withdrawal_tx['fee'] == pytest.approx(0.0001)
        assert withdrawal_tx['fee_curr'] == 'BTC'

    def test_parse_recv_transaction(self):
        """'recv' type maps to Deposit."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,recv,0.025,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash123\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.025)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Trezor'
            assert tx['created_date'] == '2024-01-15 10:30:00'
        finally:
            os.unlink(csv_path)

    def test_parse_received_transaction(self):
        """'received' type maps to Deposit."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,received,0.03,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash123\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.03)
        finally:
            os.unlink(csv_path)

    def test_parse_recv_with_wallet_name(self):
        """recv transaction with wallet_name uses specified name."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,recv,0.025,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash123\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path, wallet_name="MyTrezor")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'MyTrezor'
        finally:
            os.unlink(csv_path)

    def test_parse_sent_transaction(self):
        """'sent' type maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-01,14:00:00,sent,0.01,0.00001,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash456\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.01)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.00001)
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_parse_send_transaction(self):
        """'send' type maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-01,14:00:00,send,0.02,0.00002,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash456\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.02)
        finally:
            os.unlink(csv_path)

    def test_parse_sent_with_withdraw_to(self):
        """sent transaction with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-15,09:00:00,sent,0.005,0.000005,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash789\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Coldcard")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard'
            assert tx['comment'] == ''  # No review note when withdraw_to specified
        finally:
            os.unlink(csv_path)

    def test_parse_sent_without_withdraw_to(self):
        """sent transaction without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-15,09:00:00,sent,0.005,0.000005,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash789\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Trezor-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_skips_zero_amount_transactions(self):
        """Transactions with zero amount are skipped."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,recv,0,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash1\n"
            "2024-01-16,10:30:00,recv,0.01,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash2\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.01)
        finally:
            os.unlink(csv_path)

    def test_handles_zero_fee_withdrawal(self):
        """Withdrawal with zero fee has empty fee_curr."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-01,14:00:00,sent,0.01,0,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash456\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_handles_negative_amount(self):
        """Negative amount is converted to absolute value."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-01,14:00:00,sent,-0.01,0.00001,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash456\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['sell'] == pytest.approx(0.01)  # abs() applied
        finally:
            os.unlink(csv_path)

    def test_date_time_combination(self):
        """Date and Time columns are combined into created_date."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-03-15,16:45:30,recv,0.1,0,bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,hash123\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['created_date'] == '2024-03-15 16:45:30'
        finally:
            os.unlink(csv_path)

    def test_handles_missing_time_column(self):
        """Date without Time uses just the date."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,Address,TX ID\n"
            "2024-03-15,recv,0.1,0,bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,hash123\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['created_date'] == '2024-03-15'
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_missing_fee_column(self):
        """Gracefully handles CSV with missing Fee column."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Address,TX ID\n"
            "2024-02-01,14:00:00,sent,0.01,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash456\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)

    def test_type_case_insensitive(self):
        """Transaction type is case-insensitive."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,10:30:00,RECV,0.01,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,hash1\n"
            "2024-02-01,14:00:00,SENT,0.01,0.00001,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash2\n"
        )
        try:
            parser = TrezorImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 2
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[1]['trans_type'] == 'Withdrawal'
        finally:
            os.unlink(csv_path)


class TestTrezorImporterRegistration:
    """Tests for TrezorImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(TrezorImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """TrezorImporter is retrievable by name 'trezor'."""
        parser = get_parser("trezor")
        assert parser is not None
        assert isinstance(parser, TrezorImporter)

    def test_source_type_is_wallet(self):
        """source_type is 'wallet'."""
        parser = TrezorImporter()
        assert parser.source_type == "wallet"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Trezor columns."""
        parser = TrezorImporter()
        help_text = parser.get_format_help()
        assert "Trezor" in help_text
        assert "Date" in help_text
        assert "Type" in help_text
        assert "TX ID" in help_text


class TestTrezorImporterIntegration:
    """Integration tests for Trezor parser with database import."""

    def setup_method(self):
        clear_registry()
        register(TrezorImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Trezor CSV and import all transactions to database."""
        parser = TrezorImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "trezor_sample.csv"), withdraw_to="Coldcard")

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 5
        assert import_result['skipped'] == 0

        # Verify all types imported
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Deposit', 0) == 3  # 2 recv + 1 received
        assert type_counts.get('Withdrawal', 0) == 2  # 2 sent

        crypto.close()

    def test_withdrawal_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-02-15,09:00:00,sent,0.005,0.000005,bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,hash789\n"
        )
        try:
            parser = TrezorImporter()
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

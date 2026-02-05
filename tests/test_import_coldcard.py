"""Tests for the Coldcard parser (WAL-005)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.wallets.coldcard import ColdcardImporter
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


class TestColdcardImporterDetection:
    """Tests for ColdcardImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(ColdcardImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_coldcard_format(self):
        """detect() returns True for a file with Coldcard columns."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,0.5,0,abc123def456\n"
        )
        try:
            parser = ColdcardImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = ColdcardImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_trezor_format(self):
        """detect() returns False for Trezor format (has 'address' and 'tx id')."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,14:30:00,recv,0.5,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_sparrow_format(self):
        """detect() returns False for Sparrow format (has 'label' and 'balance')."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Deposit,50000000,50000000,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "DATE,TYPE,AMOUNT,FEE,TXID\n"
            "2024-01-15,receive,0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)


class TestColdcardImporterParsing:
    """Tests for ColdcardImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(ColdcardImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped coldcard_sample.csv fixture end-to-end."""
        parser = ColdcardImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coldcard_sample.csv"))

        # Should have 5 transactions (3 deposits, 2 withdrawals)
        assert len(transactions) == 5

        # Verify first deposit
        deposit_tx = transactions[0]
        assert deposit_tx['trans_type'] == 'Deposit'
        assert deposit_tx['buy'] == pytest.approx(0.5)
        assert deposit_tx['buy_curr'] == 'BTC'
        assert deposit_tx['exchange'] == 'Coldcard'
        assert deposit_tx['created_date'] == '2024-01-15'

        # Verify first withdrawal
        withdrawal_tx = transactions[1]
        assert withdrawal_tx['trans_type'] == 'Withdrawal'
        assert withdrawal_tx['sell'] == pytest.approx(0.1)
        assert withdrawal_tx['sell_curr'] == 'BTC'
        assert withdrawal_tx['fee'] == pytest.approx(0.00005)
        assert withdrawal_tx['fee_curr'] == 'BTC'

    def test_parse_receive_as_deposit(self):
        """'receive' type maps to Deposit."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.5)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Coldcard'
        finally:
            os.unlink(csv_path)

    def test_parse_received_as_deposit(self):
        """'received' type also maps to Deposit."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,received,0.25,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[0]['buy'] == pytest.approx(0.25)
        finally:
            os.unlink(csv_path)

    def test_parse_in_as_deposit(self):
        """'in' type maps to Deposit."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,in,0.1,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
        finally:
            os.unlink(csv_path)

    def test_parse_send_as_withdrawal(self):
        """'send' type maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-20,send,-0.1,0.00005,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.1)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.00005)
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_parse_sent_as_withdrawal(self):
        """'sent' type also maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-20,sent,-0.05,0.00003,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
            assert transactions[0]['sell'] == pytest.approx(0.05)
        finally:
            os.unlink(csv_path)

    def test_parse_out_as_withdrawal(self):
        """'out' type maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-20,out,-0.2,0.0001,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
        finally:
            os.unlink(csv_path)

    def test_sign_based_detection_positive(self):
        """Positive amount with empty type detected as Deposit."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,,0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[0]['buy'] == pytest.approx(0.5)
        finally:
            os.unlink(csv_path)

    def test_sign_based_detection_negative(self):
        """Negative amount with empty type detected as Withdrawal."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-20,,-0.1,0.00005,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
            assert transactions[0]['sell'] == pytest.approx(0.1)
        finally:
            os.unlink(csv_path)

    def test_type_case_insensitive(self):
        """Type values are matched case-insensitively."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,RECEIVE,0.5,0,abc123\n"
            "2024-02-20,SEND,-0.1,0.00005,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 2
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[1]['trans_type'] == 'Withdrawal'
        finally:
            os.unlink(csv_path)

    def test_parse_deposit_with_wallet_name(self):
        """Deposit transaction with wallet_name uses specified name."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path, wallet_name="MyColdcard")

            assert len(transactions) == 1
            assert transactions[0]['exchange'] == 'MyColdcard'
        finally:
            os.unlink(csv_path)

    def test_parse_withdrawal_with_withdraw_to(self):
        """Withdrawal with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-15,send,-0.1,0.00005,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Sparrow")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Sparrow'
            assert 'Review:' not in (tx.get('comment') or '')
        finally:
            os.unlink(csv_path)

    def test_parse_withdrawal_without_withdraw_to(self):
        """Withdrawal without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-15,send,-0.1,0.00005,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Coldcard-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_skips_zero_amount_transactions(self):
        """Transactions with zero amount are skipped."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,0,0,hash1\n"
            "2024-01-16,receive,0.5,0,hash2\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.5)
        finally:
            os.unlink(csv_path)

    def test_handles_zero_fee_withdrawal(self):
        """Withdrawal with zero fee has empty fee_curr."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-01,send,-0.1,0,hash456\n"
        )
        try:
            parser = ColdcardImporter()
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
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_case_insensitive_column_matching(self):
        """Column names are matched case-insensitively."""
        csv_path = _make_csv(
            "DATE,TYPE,AMOUNT,FEE,TXID\n"
            "2024-01-15,receive,0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.5)
        finally:
            os.unlink(csv_path)

    def test_invalid_amount_skipped(self):
        """Rows with non-numeric amounts are skipped."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,invalid,0,abc123\n"
            "2024-01-16,receive,0.5,0,def456\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.5)
        finally:
            os.unlink(csv_path)

    def test_abs_applied_to_amounts(self):
        """Absolute value is applied to amounts for both deposits and withdrawals."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-01-15,receive,-0.5,0,abc123\n"
        )
        try:
            parser = ColdcardImporter()
            _, transactions = parser.parse(csv_path)

            # 'receive' with negative amount: type takes priority, abs() applied
            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.5)
        finally:
            os.unlink(csv_path)


class TestColdcardImporterRegistration:
    """Tests for ColdcardImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(ColdcardImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """ColdcardImporter is retrievable by name 'coldcard'."""
        parser = get_parser("coldcard")
        assert parser is not None
        assert isinstance(parser, ColdcardImporter)

    def test_source_type_is_wallet(self):
        """source_type is 'wallet'."""
        parser = ColdcardImporter()
        assert parser.source_type == "wallet"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Coldcard columns."""
        parser = ColdcardImporter()
        help_text = parser.get_format_help()
        assert "Coldcard" in help_text
        assert "Date" in help_text
        assert "Type" in help_text
        assert "Amount" in help_text


class TestColdcardImporterIntegration:
    """Integration tests for Coldcard parser with database import."""

    def setup_method(self):
        clear_registry()
        register(ColdcardImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Coldcard CSV and import all transactions to database."""
        parser = ColdcardImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "coldcard_sample.csv"),
            wallet_name="MyColdcard",
            withdraw_to="Sparrow"
        )

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

        assert type_counts.get('Deposit', 0) == 3  # 3 receive
        assert type_counts.get('Withdrawal', 0) == 2  # 2 send

        crypto.close()

    def test_withdrawal_review_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Date,Type,Amount,Fee,TXID\n"
            "2024-02-15,send,-0.1,0.00005,hash789\n"
        )
        try:
            parser = ColdcardImporter()
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

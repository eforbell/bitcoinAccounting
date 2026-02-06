"""Tests for the Sparrow Wallet parser (WAL-004)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.wallets.sparrow import SparrowImporter
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


class TestSparrowImporterDetection:
    """Tests for SparrowImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(SparrowImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_sparrow_format(self):
        """detect() returns True for a file with Sparrow columns."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Deposit,50000000,50000000,0,abc123def456\n"
        )
        try:
            parser = SparrowImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = SparrowImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_trezor_format(self):
        """detect() returns False for Trezor format (missing 'balance' and 'label' columns)."""
        csv_path = _make_csv(
            "Date,Time,Type,Amount,Fee,Address,TX ID\n"
            "2024-01-15,14:30:00,recv,0.5,0,bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh,abc123\n"
        )
        try:
            parser = SparrowImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "DATE,LABEL,VALUE,BALANCE,FEE,TXID\n"
            "2024-01-15,Deposit,50000000,50000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)


class TestSparrowImporterParsing:
    """Tests for SparrowImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(SparrowImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped sparrow_sample.csv fixture end-to-end."""
        parser = SparrowImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "sparrow_sample.csv"))

        # Should have 5 transactions (3 positive, 2 negative)
        assert len(transactions) == 5

        # Verify first deposit transaction (50,000,000 sats = 0.5 BTC)
        deposit_tx = transactions[0]
        assert deposit_tx['trans_type'] == 'Deposit'
        assert deposit_tx['buy'] == pytest.approx(0.5)
        assert deposit_tx['buy_curr'] == 'BTC'
        assert deposit_tx['exchange'] == 'Sparrow'
        assert deposit_tx['created_date'] == '2024-01-15'
        assert deposit_tx['comment'] == 'Initial deposit'

        # Verify first withdrawal transaction (-20,000,000 sats = -0.2 BTC)
        withdrawal_tx = transactions[1]
        assert withdrawal_tx['trans_type'] == 'Withdrawal'
        assert withdrawal_tx['sell'] == pytest.approx(0.2)
        assert withdrawal_tx['sell_curr'] == 'BTC'
        assert withdrawal_tx['fee'] == pytest.approx(0.0001)  # 10,000 sats
        assert withdrawal_tx['fee_curr'] == 'BTC'
        assert 'DCA purchase' in withdrawal_tx['comment']

    def test_parse_positive_value_as_deposit(self):
        """Positive value maps to Deposit."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Stack sats,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.1)  # 10M sats
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Sparrow'
            assert tx['comment'] == 'Stack sats'
        finally:
            os.unlink(csv_path)

    def test_parse_negative_value_as_withdrawal(self):
        """Negative value maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-02-20,Send to cold storage,-5000000,5000000,5000,def456\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.05)  # 5M sats (absolute value)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.00005)  # 5k sats
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_parse_deposit_with_wallet_name(self):
        """Deposit transaction with wallet_name uses specified name."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Initial,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, wallet_name="MySparrow")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'MySparrow'
        finally:
            os.unlink(csv_path)

    def test_parse_withdrawal_with_withdraw_to(self):
        """Withdrawal with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-02-15,Move to Coldcard,-5000000,5000000,5000,ghi789\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Coldcard")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard'
            assert 'Move to Coldcard' in tx['comment']
            assert 'Review:' not in tx['comment']  # No review note when withdraw_to specified
        finally:
            os.unlink(csv_path)

    def test_parse_withdrawal_without_withdraw_to(self):
        """Withdrawal without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-02-15,Outgoing payment,-5000000,5000000,5000,ghi789\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Sparrow-Withdrawal'
            assert 'Outgoing payment' in tx['comment']
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_parse_withdrawal_with_label_and_review_comment(self):
        """Withdrawal combines label and review comment with semicolon."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-03-10,To cold storage,-2500000,2500000,2500,jkl012\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert 'To cold storage' in tx['comment']
            assert '; Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_skips_zero_value_transactions(self):
        """Transactions with zero value are skipped."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Zero,0,10000000,0,hash1\n"
            "2024-01-16,Valid,10000000,10000000,0,hash2\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.1)
        finally:
            os.unlink(csv_path)

    def test_handles_zero_fee_withdrawal(self):
        """Withdrawal with zero fee has empty fee_curr."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-02-01,Send,-5000000,5000000,0,hash456\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_handles_empty_label(self):
        """Empty label results in None comment for deposits."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['comment'] is None
        finally:
            os.unlink(csv_path)

    def test_satoshi_to_btc_conversion(self):
        """Satoshi values are correctly converted to BTC."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,One BTC,100000000,100000000,0,hash1\n"
            "2024-01-16,Half BTC,50000000,150000000,0,hash2\n"
            "2024-01-17,1000 sats,1000,150001000,0,hash3\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 3
            assert transactions[0]['buy'] == pytest.approx(1.0)
            assert transactions[1]['buy'] == pytest.approx(0.5)
            assert transactions[2]['buy'] == pytest.approx(0.00001)
        finally:
            os.unlink(csv_path)

    def test_fallback_to_decimal_btc(self):
        """If satoshi parsing fails, fallback to decimal BTC."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,Decimal,0.25,0.25,0,hash1\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.25)
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_missing_fee_column(self):
        """Gracefully handles CSV with missing Fee column."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,TXID\n"
            "2024-02-01,Send,-5000000,5000000,hash456\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)

    def test_handles_missing_label_column(self):
        """Gracefully handles CSV with missing Label column."""
        csv_path = _make_csv(
            "Date,Value,Balance,Fee,TXID\n"
            "2024-01-15,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['comment'] is None
        finally:
            os.unlink(csv_path)

    def test_case_insensitive_column_matching(self):
        """Column names are matched case-insensitively."""
        csv_path = _make_csv(
            "DATE,LABEL,VALUE,BALANCE,FEE,TXID\n"
            "2024-01-15,Test,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy'] == pytest.approx(0.1)
        finally:
            os.unlink(csv_path)


class TestSparrowImporterRegistration:
    """Tests for SparrowImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(SparrowImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """SparrowImporter is retrievable by name 'sparrow'."""
        parser = get_parser("sparrow")
        assert parser is not None
        assert isinstance(parser, SparrowImporter)

    def test_source_type_is_wallet(self):
        """source_type is 'wallet'."""
        parser = SparrowImporter()
        assert parser.source_type == "wallet"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Sparrow columns."""
        parser = SparrowImporter()
        help_text = parser.get_format_help()
        assert "Sparrow" in help_text
        assert "Date" in help_text
        assert "Label" in help_text
        assert "Value" in help_text


class TestSparrowImporterIntegration:
    """Integration tests for Sparrow parser with database import."""

    def setup_method(self):
        clear_registry()
        register(SparrowImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Sparrow CSV and import all transactions to database."""
        parser = SparrowImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "sparrow_sample.csv"),
            wallet_name="MySparrow",
            withdraw_to="Coldcard"
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

        assert type_counts.get('Deposit', 0) == 3  # 3 positive values
        assert type_counts.get('Withdrawal', 0) == 2  # 2 negative values

        crypto.close()

    def test_label_preserved_in_comment(self):
        """Label field is preserved in database comment column."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-01-15,My custom label,10000000,10000000,0,abc123\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, wallet_name="MySparrow")

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'My custom label'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_withdrawal_review_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Date,Label,Value,Balance,Fee,TXID\n"
            "2024-02-15,Transfer out,-5000000,5000000,5000,hash789\n"
        )
        try:
            parser = SparrowImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert 'Transfer out' in rows[0]['comment']
            assert 'Review: Verify destination wallet' in rows[0]['comment']
            crypto.close()
        finally:
            os.unlink(csv_path)

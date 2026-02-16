"""Tests for the Coinbase parser (IMP-005)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.exchanges.coinbase import CoinbaseImporter
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


class TestCoinbaseImporterDetection:
    """Tests for CoinbaseImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_coinbase_format(self):
        """detect() returns True for a file with Coinbase columns."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,Test\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_native_format(self):
        """detect() returns False for native format CSV."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
            "Trade,0.05,BTC,2500.00,USD,10.00,USD,Coinbase,,Purchase,2024-01-15\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "TIMESTAMP,TRANSACTION TYPE,ASSET,QUANTITY TRANSACTED,SPOT PRICE CURRENCY,"
            "SPOT PRICE AT TRANSACTION,SUBTOTAL,TOTAL,FEES,NOTES\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,Test\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_detects_standard_export_with_metadata_rows(self):
        """detect() returns True for standard Coinbase account exports with preamble lines."""
        parser = CoinbaseImporter()
        assert parser.detect(str(FIXTURES_DIR / "coinbase_standard_sample.csv")) is True


class TestCoinbaseImporterParsing:
    """Tests for CoinbaseImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped coinbase_sample.csv fixture end-to-end."""
        parser = CoinbaseImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_sample.csv"))

        # Should have 7 BTC transactions (the ETH one is filtered out)
        assert len(transactions) == 7

        # Verify Buy transaction
        buy_tx = transactions[0]
        assert buy_tx['trans_type'] == 'Trade'
        assert buy_tx['buy'] == pytest.approx(0.05)
        assert buy_tx['buy_curr'] == 'BTC'
        assert buy_tx['sell'] == pytest.approx(2510.0)  # Total includes fees
        assert buy_tx['sell_curr'] == 'USD'
        assert buy_tx['fee'] == pytest.approx(10.0)
        assert buy_tx['exchange'] == 'Coinbase'
        assert buy_tx['comment'] == 'DCA purchase'

    def test_parse_standard_fixture_with_metadata_rows(self):
        """Parse standard Coinbase account export format with leading metadata rows."""
        parser = CoinbaseImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_standard_sample.csv"))

        assert colnames
        assert len(transactions) == 4  # ETH row filtered out

        # Timestamps should normalize from "... UTC" to app-friendly format.
        assert transactions[0]['created_date'] == "2022-01-05 10:00:00"

        # Buy row (total includes fees/spread).
        buy_tx = transactions[0]
        assert buy_tx['trans_type'] == 'Trade'
        assert buy_tx['buy'] == pytest.approx(0.01)
        assert buy_tx['sell'] == pytest.approx(424.20)
        assert buy_tx['fee'] == pytest.approx(4.20)

        # Pro Withdrawal row should map as Withdrawal.
        withdrawal_tx = transactions[2]
        assert withdrawal_tx['trans_type'] == 'Withdrawal'
        assert withdrawal_tx['sell'] == pytest.approx(0.001)
        assert withdrawal_tx['sell_curr'] == 'BTC'

        # Reward Income should map to Interest Income.
        reward_tx = transactions[3]
        assert reward_tx['trans_type'] == 'Interest Income'
        assert reward_tx['buy'] == pytest.approx(0.00001)

    def test_parse_buy_transaction(self):
        """Buy transaction maps to Trade with BTC buy side."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.1,USD,50000.00,5000.00,5025.00,25.00,My purchase\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.1)
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == pytest.approx(5025.0)
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == pytest.approx(25.0)
            assert tx['fee_curr'] == 'USD'
            assert tx['comment'] == 'My purchase'
        finally:
            os.unlink(csv_path)

    def test_parse_sell_transaction(self):
        """Sell transaction maps to Trade with BTC sell side."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-01T14:00:00Z,Sell,BTC,0.02,USD,52000.00,1040.00,1030.00,10.00,Profit taking\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(1040.0)  # Subtotal (before fees)
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == pytest.approx(0.02)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(10.0)
        finally:
            os.unlink(csv_path)

    def test_parse_send_with_withdraw_to(self):
        """Send transaction with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,To ledger\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Ledger'
            assert tx['sell'] == pytest.approx(0.01)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.0001)
            assert tx['comment'] == 'To ledger'  # No review note when withdraw_to specified
        finally:
            os.unlink(csv_path)

    def test_parse_send_without_withdraw_to(self):
        """Send transaction without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Coinbase-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_parse_receive_transaction(self):
        """Receive transaction maps to Deposit."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-03-01T00:00:00Z,Receive,BTC,0.005,USD,48000.00,240.00,240.00,0.00,From friend\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.005)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Coinbase'
            assert tx['comment'] == 'From friend'
        finally:
            os.unlink(csv_path)

    def test_parse_rewards_income(self):
        """Rewards Income maps to Interest Income."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-03-15T12:00:00Z,Rewards Income,BTC,0.0001,USD,55000.00,5.50,5.50,0.00,Staking\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.0001)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Coinbase'
            assert 'usd_equivalent' in tx
            assert tx['usd_equivalent'] == pytest.approx(5.50)
        finally:
            os.unlink(csv_path)

    def test_parse_learning_reward(self):
        """Learning Reward maps to Interest Income."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-04-01T08:00:00Z,Learning Reward,BTC,0.00005,USD,60000.00,3.00,3.00,0.00,\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.00005)
            # When no notes, should include original type
            assert 'Learning Reward' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_parse_convert_transaction(self):
        """Convert transaction maps to Trade."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-04-15T16:00:00Z,Convert,BTC,0.001,USD,62000.00,62.00,62.00,0.50,From ETH\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.001)
            assert tx['buy_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.50)
        finally:
            os.unlink(csv_path)

    def test_filters_non_btc_transactions(self):
        """Non-BTC transactions are filtered out."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,ETH,1.0,USD,3000.00,3000.00,3015.00,15.00,ETH purchase\n"
            "2024-01-16T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,BTC purchase\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)


class TestCoinbaseImporterRegistration:
    """Tests for CoinbaseImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """CoinbaseImporter is retrievable by name 'coinbase'."""
        parser = get_parser("coinbase")
        assert parser is not None
        assert isinstance(parser, CoinbaseImporter)

    def test_source_type_is_exchange(self):
        """source_type is 'exchange'."""
        parser = CoinbaseImporter()
        assert parser.source_type == "exchange"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Coinbase columns."""
        parser = CoinbaseImporter()
        help_text = parser.get_format_help()
        assert "Coinbase" in help_text
        assert "Timestamp" in help_text
        assert "Transaction Type" in help_text
        assert "Quantity Transacted" in help_text


class TestCoinbaseImporterIntegration:
    """Integration tests for Coinbase parser with database import."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Coinbase CSV and import all transactions to database."""
        parser = CoinbaseImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_sample.csv"), withdraw_to="Ledger")

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 7
        assert import_result['skipped'] == 0

        # Verify all types imported
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Trade', 0) == 3  # 1 Buy + 1 Sell + 1 Convert (ETH Buy filtered)
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Interest Income', 0) == 2  # Rewards + Learning

        crypto.close()

    def test_withdrawal_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,\n"
        )
        try:
            parser = CoinbaseImporter()
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

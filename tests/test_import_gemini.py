"""Tests for the Gemini parser (IMP-011)."""

import tempfile
import os
from pathlib import Path

import pytest

from imports.exchanges.gemini import GeminiImporter, _parse_number
from imports.registry import register, get_parser, get_all_parsers, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from cryptoAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"

# Shared header — hyphenated column names match Gemini's export
_HDR = "time,base-asset,quote-asset,type,price,quantity,total,fee,fee-currency,trade-id\n"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestGeminiImporterDetection:
    """Detection logic for Gemini CSV exports."""

    def test_detects_gemini_export(self):
        """File with base-asset, quote-asset, trade-id is detected."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,BTC,USD,Buy,29500,0.01,295,2.95,USD,t-1\n"
        )
        try:
            parser = GeminiImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_cashapp_export(self):
        """Cash App CSV (no hyphenated columns) is not detected as Gemini."""
        csv_path = _make_csv(
            "Date,Transaction Type,Amount (BTC),Market Price ($),"
            "Cost Basis ($),Proceeds ($),Gain/Loss ($),Note\n"
            "2024-01-10 10:30:00,Purchase,0.01,29500.00,295.00,,,\n"
        )
        try:
            parser = GeminiImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV lacks Gemini-specific hyphenated columns."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = GeminiImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = GeminiImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestGeminiParseNumber:
    """Unit tests for the _parse_number helper."""

    def test_plain_number(self):
        assert _parse_number("0.01") == 0.01

    def test_dollar_sign_and_commas(self):
        assert _parse_number("$29,500.00") == 29500.0

    def test_empty_string(self):
        assert _parse_number("") == 0.0

    def test_whitespace_only(self):
        assert _parse_number("   ") == 0.0

    def test_non_numeric(self):
        assert _parse_number("abc") == 0.0

    def test_dollar_sign_only(self):
        assert _parse_number("$") == 0.0


class TestGeminiImporterParsing:
    """Row-level parsing for each Gemini transaction type."""

    def test_parse_fixture_file(self):
        """Fixture: 1 Buy + 1 Sell = 2 Trade, 1 Deposit, 1 Withdrawal, 1 Earn; ETH row filtered."""
        parser = GeminiImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "gemini_sample.csv"))

        assert len(colnames) == 11
        # 6 rows - 1 ETH = 5 transactions
        assert len(transactions) == 5

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Interest Income', 0) == 1

    def test_buy_maps_to_trade(self):
        """Buy row: BTC is bought, USD (quote-asset) is sold; fee in USD."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,BTC,USD,Buy,29500.00,0.01,295.00,2.95,USD,trade-001\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'Gemini'
            assert tx['buy'] == 0.01
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 295.00      # total
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 2.95
            assert tx['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_buy_falls_back_to_price_times_quantity(self):
        """Buy with empty total computes sell from price * quantity."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,BTC,USD,Buy,29500.00,0.01,,0,USD,t-1\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            # 29500 * 0.01 = 295.0
            assert txs[0]['sell'] == pytest.approx(295.0)
        finally:
            os.unlink(csv_path)

    def test_sell_maps_to_trade(self):
        """Sell row: BTC is sold, USD (proceeds) is bought."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-20 14:30:00,BTC,USD,Sell,30000.00,0.005,150.00,1.50,USD,trade-002\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == 150.00       # proceeds (total)
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.005       # BTC sold
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == 1.50
            assert tx['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_sell_falls_back_to_price_times_quantity(self):
        """Sell with empty total computes buy from price * quantity."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-20 14:30:00,BTC,USD,Sell,30000.00,0.005,,0,USD,t-2\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            # 30000 * 0.005 = 150.0
            assert txs[0]['buy'] == pytest.approx(150.0)
        finally:
            os.unlink(csv_path)

    def test_deposit_maps_correctly(self):
        """Deposit row: BTC received, zero fee when fee field is empty."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-01 09:00:00,BTC,USD,Deposit,,0.02,,,,\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'Gemini'
            assert tx['buy'] == 0.02
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_withdrawal_default_exchange(self):
        """Withdrawal with withdraw_to=None uses 'Gemini-Withdrawal' + review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 16:00:00,BTC,USD,Withdrawal,,0.01,,0.0001,BTC,\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Gemini-Withdrawal'
            assert tx['sell'] == 0.01
            assert tx['sell_curr'] == 'BTC'
            assert 'Review' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_withdrawal_with_withdraw_to(self):
        """Withdrawal with explicit withdraw_to sets exchange; no review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 16:00:00,BTC,USD,Withdrawal,,0.01,,0.0001,BTC,\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path, withdraw_to="ColdCard")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'ColdCard'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_withdrawal_btc_fee_tracked(self):
        """Withdrawal with a BTC network fee is recorded correctly."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 16:00:00,BTC,USD,Withdrawal,,0.01,,0.0001,BTC,\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert txs[0]['fee'] == 0.0001
            assert txs[0]['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_earn_maps_to_interest_income(self):
        """Earn row maps to Interest Income with 'Gemini Earn' comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-20 12:00:00,BTC,USD,Earn,,0.001,,,,trade-003\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Interest Income'
            assert tx['exchange'] == 'Gemini'
            assert tx['buy'] == 0.001
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['comment'] == 'Gemini Earn'
        finally:
            os.unlink(csv_path)

    def test_earn_interest_alias(self):
        """'Earn Interest' type (alternate label) also maps to Interest Income."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-20 12:00:00,BTC,USD,Earn Interest,,0.0005,,,,\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            assert txs[0]['trans_type'] == 'Interest Income'
        finally:
            os.unlink(csv_path)

    def test_non_btc_filtered_out(self):
        """ETH and other non-BTC base-assets are silently dropped."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-15 11:00:00,ETH,USD,Buy,2200.00,1.5,3300.00,3.30,USD,t-4\n"
            "2024-01-16 11:00:00,SOL,USD,Buy,100.00,10,1000.00,1.00,USD,t-5\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_row_missing_time_is_skipped(self):
        """Row where time is empty is silently dropped."""
        csv_path = _make_csv(
            _HDR +
            ",BTC,USD,Buy,29500.00,0.01,295.00,2.95,USD,t-1\n"
        )
        try:
            parser = GeminiImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """File with only a header row yields an empty transaction list."""
        csv_path = _make_csv(_HDR)
        try:
            parser = GeminiImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)


class TestGeminiImporterRegistration:
    """Gemini parser registration and discovery."""

    def setup_method(self):
        clear_registry()
        register(GeminiImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_by_name(self):
        assert get_parser("Gemini") is not None

    def test_registered_parser_is_gemini_importer(self):
        assert isinstance(get_parser("Gemini"), GeminiImporter)

    def test_appears_in_all_parsers(self):
        names = [p.name for p in get_all_parsers()]
        assert "Gemini" in names


class TestGeminiImporterIntegration:
    """End-to-end import from Gemini CSV into in-memory SQLite."""

    def setup_method(self):
        clear_registry()
        register(GeminiImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse fixture, import all; verify counts and types."""
        parser = GeminiImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "gemini_sample.csv"), withdraw_to="Ledger"
        )

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 5
        assert import_result['skipped'] == 0

        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Interest Income', 0) == 1

    def test_earn_comment_persists(self):
        """Earn transactions retain 'Gemini Earn' comment after import."""
        parser = GeminiImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "gemini_sample.csv"), withdraw_to="Ledger"
        )

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        crypto.import_transactions(transactions)

        rows = backend.execute(
            "SELECT comment FROM ledger WHERE trans_type = 'Interest Income'"
        )
        assert len(rows) == 1
        assert rows[0]['comment'] == 'Gemini Earn'

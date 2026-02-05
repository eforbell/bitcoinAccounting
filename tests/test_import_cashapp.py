"""Tests for the Cash App parser (IMP-010)."""

import tempfile
import os
import warnings
from pathlib import Path

import pytest

from imports.exchanges.cashapp import CashAppImporter, _parse_number
from imports.registry import register, get_parser, get_all_parsers, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from cryptoAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"

# Shared header constant
_HDR = "Date,Transaction Type,Amount (BTC),Market Price ($),Cost Basis ($),Proceeds ($),Gain/Loss ($),Note\n"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestCashAppImporterDetection:
    """Detection logic for Cash App gain/loss CSV exports."""

    def test_detects_cashapp_export(self):
        """File with Cost Basis ($), Gain/Loss ($), Amount (BTC) is detected."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-10 10:30:00,Purchase,0.01,29500.00,295.00,,,DCA\n"
        )
        try:
            parser = CashAppImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_swan_export(self):
        """Swan CSV (no Gain/Loss column) is not detected as Cash App."""
        csv_path = _make_csv(
            "Date,Type,Amount (BTC),Price (USD),Total (USD),Fee (USD),Status\n"
            "2024-01-05 10:00:00,Purchase,0.003,28950.00,100.00,2.50,Completed\n"
        )
        try:
            parser = CashAppImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV lacks Cash App-specific columns."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = CashAppImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = CashAppImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestCashAppParseNumber:
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


class TestCashAppImporterParsing:
    """Row-level parsing for each Cash App transaction type."""

    def test_parse_fixture_file(self):
        """Fixture: 2 Purchase + 1 Sale = 3 Trade, 1 Receive = Deposit, 1 Send = Withdrawal."""
        parser = CashAppImporter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Receive row has no basis
            colnames, transactions = parser.parse(str(FIXTURES_DIR / "cashapp_sample.csv"))

        assert len(colnames) == 11
        assert len(transactions) == 5

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 3
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Withdrawal', 0) == 1

    def test_purchase_maps_to_trade(self):
        """Purchase uses Cost Basis as USD sell amount."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-10 10:30:00,Purchase,0.01,29500.00,295.00,,,DCA January\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'CashApp'
            assert tx['buy'] == 0.01
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 295.00
            assert tx['sell_curr'] == 'USD'
            assert tx['comment'] == 'DCA January'
        finally:
            os.unlink(csv_path)

    def test_purchase_falls_back_to_market_price(self):
        """Purchase with empty Cost Basis computes sell from Market Price * Amount."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-10 10:30:00,Purchase,0.01,29500.00,,,,\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            # 0.01 * 29500 = 295.0
            assert txs[0]['sell'] == pytest.approx(295.0)
        finally:
            os.unlink(csv_path)

    def test_sale_maps_to_trade(self):
        """Sale uses Proceeds as USD buy amount; BTC is the sell side."""
        csv_path = _make_csv(
            _HDR +
            "2024-03-01 11:00:00,Sale,0.005,43000.00,210.00,215.00,5.00,Sold for expenses\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'CashApp'
            assert tx['buy'] == 215.00       # Proceeds
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.005       # BTC sold
            assert tx['sell_curr'] == 'BTC'
            assert tx['comment'] == 'Sold for expenses'
        finally:
            os.unlink(csv_path)

    def test_sale_falls_back_to_market_price(self):
        """Sale with empty Proceeds computes buy from Market Price * Amount."""
        csv_path = _make_csv(
            _HDR +
            "2024-03-01 11:00:00,Sale,0.005,43000.00,,,,,\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            # 0.005 * 43000 = 215.0
            assert txs[0]['buy'] == pytest.approx(215.0)
            assert txs[0]['buy_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_send_maps_to_withdrawal_default(self):
        """Send with withdraw_to=None uses 'CashApp-Withdrawal' and review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-03-10 16:45:00,Send,0.01,45000.00,,,,To Ledger\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'CashApp-Withdrawal'
            assert tx['sell'] == 0.01
            assert tx['sell_curr'] == 'BTC'
            assert 'Review' in tx['comment']
            assert 'To Ledger' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_withdraw_to(self):
        """Send with explicit withdraw_to sets exchange; no review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-03-10 16:45:00,Send,0.01,45000.00,,,,To Ledger\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'Ledger'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_receive_without_cost_basis_warns(self):
        """Receive with empty Cost Basis emits UserWarning about external transfer."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-20 09:00:00,Receive,0.02,41500.00,,,,\n"
        )
        try:
            parser = CashAppImporter()
            with pytest.warns(UserWarning, match="cost basis is \\$0"):
                _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            assert txs[0]['trans_type'] == 'Deposit'
            assert txs[0]['buy'] == 0.02
            assert "Cost basis $0" in txs[0]['comment']
        finally:
            os.unlink(csv_path)

    def test_receive_with_cost_basis_no_warning(self):
        """Receive with a non-zero Cost Basis does NOT warn."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-20 09:00:00,Receive,0.02,41500.00,830.00,,,Re-deposited\n"
        )
        try:
            parser = CashAppImporter()
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # any warning becomes an error
                _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            assert txs[0]['trans_type'] == 'Deposit'
            assert txs[0]['comment'] == 'Re-deposited'
        finally:
            os.unlink(csv_path)

    def test_receive_zero_basis_explicit_warns(self):
        """Receive with Cost Basis literally '0.00' also warns ($0 is $0)."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-20 09:00:00,Receive,0.02,41500.00,0.00,,,\n"
        )
        try:
            parser = CashAppImporter()
            with pytest.warns(UserWarning, match="cost basis is \\$0"):
                _, txs = parser.parse(csv_path)
            assert "Cost basis $0" in txs[0]['comment']
        finally:
            os.unlink(csv_path)

    def test_unknown_type_is_skipped(self):
        """Rows with an unrecognized Transaction Type are dropped."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-10 10:30:00,Conversion,0.01,29500.00,295.00,,,\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_row_missing_date_is_skipped(self):
        """Rows where date is empty are silently dropped."""
        csv_path = _make_csv(
            _HDR +
            ",Purchase,0.01,29500.00,295.00,,,\n"
        )
        try:
            parser = CashAppImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """File with only a header row yields an empty transaction list."""
        csv_path = _make_csv(_HDR)
        try:
            parser = CashAppImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)


class TestCashAppImporterRegistration:
    """CashApp parser registration and discovery."""

    def setup_method(self):
        clear_registry()
        register(CashAppImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_by_name(self):
        assert get_parser("CashApp") is not None

    def test_registered_parser_is_cashapp_importer(self):
        assert isinstance(get_parser("CashApp"), CashAppImporter)

    def test_appears_in_all_parsers(self):
        names = [p.name for p in get_all_parsers()]
        assert "CashApp" in names


class TestCashAppImporterIntegration:
    """End-to-end import from Cash App CSV into in-memory SQLite."""

    def setup_method(self):
        clear_registry()
        register(CashAppImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse fixture and import; verify transaction counts and types."""
        parser = CashAppImporter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, transactions = parser.parse(
                str(FIXTURES_DIR / "cashapp_sample.csv"), withdraw_to="Ledger"
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

        assert type_counts.get('Trade', 0) == 3
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Withdrawal', 0) == 1

    def test_missing_basis_comment_persists(self):
        """Receive with no cost basis gets the warning comment stored in ledger."""
        parser = CashAppImporter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, transactions = parser.parse(
                str(FIXTURES_DIR / "cashapp_sample.csv"), withdraw_to="Ledger"
            )

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        crypto.import_transactions(transactions)

        rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Deposit'")
        assert len(rows) == 1
        assert "Cost basis $0" in rows[0]['comment']

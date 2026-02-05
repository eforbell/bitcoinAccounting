"""Tests for the Strike parser (IMP-007)."""

import tempfile
import os
from pathlib import Path

from imports.exchanges.strike import StrikeImporter, _parse_number
from imports.registry import register, get_parser, get_all_parsers, clear_registry
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


class TestStrikeImporterDetection:
    """Detection logic for Strike CSV exports."""

    def test_detects_strike_export(self):
        """File with Date, Type, BTC Amount, USD Amount columns is detected."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-01-10 09:00:00,Purchase,DCA,0.05,2450.00,2.50,0\n"
        )
        try:
            parser = StrikeImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV (no 'BTC Amount' column) is not detected as Strike."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = StrikeImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = StrikeImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestStrikeParseNumber:
    """Unit tests for the _parse_number helper."""

    def test_plain_number(self):
        assert _parse_number("0.05") == 0.05

    def test_dollar_sign(self):
        assert _parse_number("$2,450.00") == 2450.0

    def test_empty_string(self):
        assert _parse_number("") == 0.0

    def test_whitespace_only(self):
        assert _parse_number("   ") == 0.0

    def test_non_numeric(self):
        assert _parse_number("abc") == 0.0

    def test_dollar_sign_only(self):
        assert _parse_number("$") == 0.0


class TestStrikeImporterParsing:
    """Row-level parsing for each Strike transaction type."""

    def test_parse_fixture_file(self):
        """Full fixture file parses without error and returns expected counts."""
        parser = StrikeImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "strike_sample.csv"))

        assert len(colnames) == 11
        assert 'trans_type' in colnames

        # Fixture: 2 Purchase, 1 Send, 1 Receive, 1 Payment → 5 transactions
        assert len(transactions) == 5

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Withdrawal', 0) == 2  # Send + Payment
        assert type_counts.get('Deposit', 0) == 1

    def test_purchase_maps_to_trade(self):
        """Purchase row maps to Trade with correct buy/sell/fee fields."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-01-10 09:00:00,Purchase,DCA January,0.05,2450.00,2.50,0\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'Strike'
            assert tx['buy'] == 0.05
            assert tx['buy_curr'] == 'BTC'
            # sell = usd_amount + fee_usd (total out of pocket)
            assert tx['sell'] == 2452.50
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 2.50
            assert tx['fee_curr'] == 'USD'
            assert tx['comment'] == 'DCA January'
        finally:
            os.unlink(csv_path)

    def test_send_maps_to_withdrawal(self):
        """Send row maps to Withdrawal; default exchange when withdraw_to is None."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-02-05 11:00:00,Send,To Ledger Nano,0.02,0,0,0.00005\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Strike-Withdrawal'
            assert tx['sell'] == 0.02
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == 0.00005
            assert tx['fee_curr'] == 'BTC'
            # Review comment injected when withdraw_to is None
            assert 'Review' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_withdraw_to(self):
        """Send with withdraw_to sets exchange to that wallet name."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-02-05 11:00:00,Send,To Ledger Nano,0.02,0,0,0.00005\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Ledger'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_receive_maps_to_deposit(self):
        """Receive row maps to Deposit with zero fees."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-02-20 10:00:00,Receive,From savings wallet,0.1,0,0,0\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'Strike'
            assert tx['buy'] == 0.1
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
            assert tx['comment'] == 'From savings wallet'
        finally:
            os.unlink(csv_path)

    def test_payment_maps_to_withdrawal(self):
        """Payment (Lightning) row maps to Withdrawal."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-03-01 08:00:00,Payment,Lightning payment,0.001,0,0,0.0001\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Lightning")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Lightning'
            assert tx['sell'] == 0.001
            assert tx['fee'] == 0.0001
            assert tx['fee_curr'] == 'BTC'
            assert 'Lightning payment' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_unknown_type_is_skipped(self):
        """Rows with an unrecognized type are dropped (return None)."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-03-01 08:00:00,Staking,Staking reward,0.001,0,0,0\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """File with only a header row yields an empty transaction list."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
        )
        try:
            parser = StrikeImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)

    def test_row_missing_date_or_type_is_skipped(self):
        """Rows where date or type is empty are silently dropped."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            ",Purchase,No date,0.01,500.00,0.50,0\n"
            "2024-01-10 09:00:00,,No type,0.01,500.00,0.50,0\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_fee_falls_back_to_usd_when_btc_fee_is_zero(self):
        """For withdrawals, if fee_btc is 0 the parser uses fee_usd instead."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-02-05 11:00:00,Send,USD fee withdrawal,0.02,0,1.50,0\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Wallet")
            assert len(txs) == 1
            assert txs[0]['fee'] == 1.50
            assert txs[0]['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)


class TestStrikeImporterRegistration:
    """Strike parser registration and discovery."""

    def setup_method(self):
        clear_registry()
        register(StrikeImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_by_name(self):
        assert get_parser("Strike") is not None

    def test_registered_parser_is_strike_importer(self):
        assert isinstance(get_parser("Strike"), StrikeImporter)

    def test_appears_in_all_parsers(self):
        names = [p.name for p in get_all_parsers()]
        assert "Strike" in names


class TestStrikeImporterIntegration:
    """End-to-end import from Strike CSV into in-memory SQLite."""

    def setup_method(self):
        clear_registry()
        register(StrikeImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Strike fixture and import all transactions; verify counts and types."""
        parser = StrikeImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "strike_sample.csv"), withdraw_to="Ledger"
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
        assert type_counts.get('Withdrawal', 0) == 2  # Send + Payment
        assert type_counts.get('Deposit', 0) == 1


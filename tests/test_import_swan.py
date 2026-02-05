"""Tests for the Swan Bitcoin parser (IMP-009)."""

import tempfile
import os
from pathlib import Path

from imports.exchanges.swan import SwanImporter, _parse_number
from imports.registry import register, get_parser, get_all_parsers, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from cryptoAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"

# Shared header constant — avoids repeating across every test method
_HDR = "Date,Type,Amount (BTC),Price (USD),Total (USD),Fee (USD),Status\n"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestSwanImporterDetection:
    """Detection logic for Swan Bitcoin CSV exports."""

    def test_detects_swan_export(self):
        """File with Amount (BTC), Price (USD), Total (USD) columns is detected."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003368,28950.00,100.00,2.50,Completed\n"
        )
        try:
            parser = SwanImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_strike_export(self):
        """Strike CSV (no 'Amount (BTC)' or 'Price (USD)') is not detected as Swan."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-01-10 09:00:00,Purchase,DCA,0.05,2450.00,2.50,0\n"
        )
        try:
            parser = SwanImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV lacks Swan-specific columns."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = SwanImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = SwanImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestSwanParseNumber:
    """Unit tests for the _parse_number helper."""

    def test_plain_number(self):
        assert _parse_number("0.003368") == 0.003368

    def test_dollar_sign_and_commas(self):
        assert _parse_number("$28,950.00") == 28950.0

    def test_empty_string(self):
        assert _parse_number("") == 0.0

    def test_whitespace_only(self):
        assert _parse_number("   ") == 0.0

    def test_non_numeric(self):
        assert _parse_number("abc") == 0.0

    def test_dollar_sign_only(self):
        assert _parse_number("$") == 0.0


class TestSwanImporterParsing:
    """Row-level parsing for each Swan transaction type."""

    def test_parse_fixture_file(self):
        """Full fixture: 3 Purchase + 1 Withdrawal + 1 Deposit = 5; USD Deposit skipped."""
        parser = SwanImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "swan_sample.csv"))

        assert len(colnames) == 11
        assert 'trans_type' in colnames

        assert len(transactions) == 5

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 3
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Deposit', 0) == 1

    def test_purchase_maps_to_trade(self):
        """Purchase row maps to Trade with correct DCA fields."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003368,28950.00,100.00,2.50,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'Swan'
            assert tx['buy'] == 0.003368
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 100.00
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 2.50
            assert tx['fee_curr'] == 'USD'
            assert tx['group'] == 'DCA'
        finally:
            os.unlink(csv_path)

    def test_multiple_purchases_all_tagged_dca(self):
        """Every Purchase row gets group='DCA' regardless of amount."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003368,28950.00,100.00,2.50,Completed\n"
            "2024-01-12 10:00:00,Purchase,0.01338,29300.00,400.00,5.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 2
            assert all(tx['group'] == 'DCA' for tx in txs)
        finally:
            os.unlink(csv_path)

    def test_withdrawal_default_exchange(self):
        """Withdrawal with withdraw_to=None uses 'Swan-Withdrawal' and injects review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 14:30:00,Withdrawal,0.005,,,0.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Swan-Withdrawal'
            assert tx['sell'] == 0.005
            assert tx['sell_curr'] == 'BTC'
            assert tx['buy'] == 0.0
            assert 'Review' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_withdrawal_with_withdraw_to(self):
        """Withdrawal with withdraw_to sets exchange; no review comment."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 14:30:00,Withdrawal,0.005,,,0.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'Ledger'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_withdrawal_with_fee(self):
        """Withdrawal with a non-zero USD fee is tracked correctly."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 14:30:00,Withdrawal,0.005,,,5.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            assert txs[0]['fee'] == 5.00
            assert txs[0]['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_withdrawal_zero_fee_has_empty_fee_curr(self):
        """Withdrawal with fee=0 yields empty fee_curr."""
        csv_path = _make_csv(
            _HDR +
            "2024-02-15 14:30:00,Withdrawal,0.005,,,0.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert txs[0]['fee'] == 0.0
            assert txs[0]['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_deposit_maps_correctly(self):
        """Deposit (BTC received) maps to Deposit with zero fees."""
        csv_path = _make_csv(
            _HDR +
            "2024-03-01 09:00:00,Deposit,0.01,,,0.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'Swan'
            assert tx['buy'] == 0.01
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)

    def test_usd_deposit_is_skipped(self):
        """USD Deposit (no BTC) is silently dropped."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-20 12:00:00,USD Deposit,,,250.00,0.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_pending_transaction_is_skipped(self):
        """Rows with Status=Pending are silently dropped."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003,28000.00,84.00,2.00,Pending\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_failed_transaction_is_skipped(self):
        """Rows with Status=Failed are silently dropped."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003,28000.00,84.00,2.00,Failed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_completed_case_insensitive(self):
        """Status matching is case-insensitive: 'completed' and 'COMPLETED' both pass."""
        csv_path = _make_csv(
            _HDR +
            "2024-01-05 10:00:00,Purchase,0.003,28000.00,84.00,2.00,completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
        finally:
            os.unlink(csv_path)

    def test_row_missing_date_is_skipped(self):
        """Rows where date is empty are silently dropped."""
        csv_path = _make_csv(
            _HDR +
            ",Purchase,0.003,28000.00,84.00,2.00,Completed\n"
        )
        try:
            parser = SwanImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """File with only a header row yields an empty transaction list."""
        csv_path = _make_csv(_HDR)
        try:
            parser = SwanImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)


class TestSwanImporterRegistration:
    """Swan parser registration and discovery."""

    def setup_method(self):
        clear_registry()
        register(SwanImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_by_name(self):
        assert get_parser("Swan") is not None

    def test_registered_parser_is_swan_importer(self):
        assert isinstance(get_parser("Swan"), SwanImporter)

    def test_appears_in_all_parsers(self):
        names = [p.name for p in get_all_parsers()]
        assert "Swan" in names


class TestSwanImporterIntegration:
    """End-to-end import from Swan CSV into in-memory SQLite."""

    def setup_method(self):
        clear_registry()
        register(SwanImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Swan fixture and import all transactions; verify counts and types."""
        parser = SwanImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "swan_sample.csv"), withdraw_to="Ledger"
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
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Deposit', 0) == 1

    def test_dca_group_persisted(self):
        """Purchase transactions retain group='DCA' after import."""
        parser = SwanImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "swan_sample.csv"), withdraw_to="Ledger"
        )

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        crypto.import_transactions(transactions)

        rows = backend.execute(
            "SELECT \"group\" FROM ledger WHERE trans_type = 'Trade'"
        )
        for row in rows:
            assert row['group'] == 'DCA'

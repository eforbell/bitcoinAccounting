"""Tests for the River parser (IMP-008).

Fixture values are synthetic: addresses are BIP-173 test vectors and
transaction IDs are placeholder patterns.
"""

import tempfile
import os
from pathlib import Path

from imports.exchanges.river import RiverImporter, _parse_number as river_parse_number, _detect_river_format
from imports.registry import register, get_parser, get_all_parsers, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from bitcoinAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class TestRiverImporterDetection:
    """Detection logic for River CSV exports."""

    def test_detects_account_activity(self):
        """File with River Account Activity columns is detected."""
        csv_path = _make_csv(
            "Date,Reference Code,Transaction Type,Sent Amount,Sent Currency,"
            "Received Amount,Received Currency,Fee Amount,Fee Currency,"
            "Total Amount,Total Currency,Method,Source,Destination,"
            "Cost Basis,Cost Basis Currency,Bitcoin Price Amount,Bitcoin Price Currency,"
            "Transaction ID,Recurring,Tag\n"
            "2024-03-04 09:05:00,RBUY0001,Buy,990.10,USD,0.01500000,BTC,9.90,USD,"
            "1000.00,USD,Cash Balance,Cash Balance,Bitcoin Balance,"
            "1000.00,USD,66000.00,USD,,False,\n"
        )
        try:
            parser = RiverImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_detects_btc_activity(self):
        """File with River Bitcoin Activity columns is detected."""
        csv_path = _make_csv(
            "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
            "Fee Amount,Fee Currency,Tag\n"
            "2024-03-04 09:05:00,990.10,USD,0.01500000,BTC,9.90,USD,Buy\n"
        )
        try:
            parser = RiverImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV is not detected as River."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = RiverImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = RiverImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# _detect_river_format helper
# ---------------------------------------------------------------------------

class TestRiverDetectFormat:
    """Unit tests for the _detect_river_format helper."""

    def test_account_activity_format(self):
        header = {
            'date', 'reference code', 'transaction type', 'sent amount',
            'sent currency', 'received amount', 'received currency',
            'fee amount', 'fee currency', 'total amount', 'total currency',
            'method', 'source', 'destination', 'cost basis', 'cost basis currency',
            'bitcoin price amount', 'bitcoin price currency',
            'transaction id', 'recurring', 'tag',
        }
        assert _detect_river_format(header) == 'account'

    def test_btc_activity_format(self):
        header = {
            'date', 'sent amount', 'sent currency', 'received amount',
            'received currency', 'fee amount', 'fee currency', 'tag',
        }
        assert _detect_river_format(header) == 'btc'

    def test_unknown_format_returns_none(self):
        assert _detect_river_format({'name', 'amount', 'date'}) is None

    def test_account_takes_priority_over_btc(self):
        """Account markers present alongside btc cols -> 'account'."""
        header = {
            'date', 'sent amount', 'sent currency', 'received amount',
            'received currency', 'fee amount', 'fee currency', 'tag',
            'reference code', 'transaction type', 'bitcoin price amount',
        }
        assert _detect_river_format(header) == 'account'


# ---------------------------------------------------------------------------
# _parse_number helper
# ---------------------------------------------------------------------------

class TestRiverParseNumber:
    """Unit tests for River's _parse_number helper."""

    def test_plain_number(self):
        assert river_parse_number("0.05") == 0.05

    def test_dollar_sign(self):
        assert river_parse_number("$2,450.00") == 2450.0

    def test_empty_string(self):
        assert river_parse_number("") == 0.0

    def test_whitespace_only(self):
        assert river_parse_number("   ") == 0.0

    def test_non_numeric(self):
        assert river_parse_number("abc") == 0.0

    def test_dollar_sign_only(self):
        assert river_parse_number("$") == 0.0


# ---------------------------------------------------------------------------
# Account Activity parsing
# ---------------------------------------------------------------------------

# Shared header string for Account Activity test CSVs
_ACCT_HDR = (
    "Date,Reference Code,Transaction Type,Sent Amount,Sent Currency,"
    "Received Amount,Received Currency,Fee Amount,Fee Currency,"
    "Total Amount,Total Currency,Method,Source,Destination,"
    "Cost Basis,Cost Basis Currency,Bitcoin Price Amount,Bitcoin Price Currency,"
    "Transaction ID,Recurring,Tag\n"
)


class TestRiverAccountActivityParsing:
    """Row-level parsing for River Account Activity format."""

    def test_parse_fixture_file(self):
        """Full Account Activity fixture: 1 Cash Deposit + 5 BTC txns = 6 total."""
        parser = RiverImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "river_account_sample.csv"))

        assert len(colnames) == 11
        assert 'trans_type' in colnames
        assert len(transactions) == 6

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Withdrawal', 0) == 2
        assert type_counts.get('Interest Income', 0) == 1
        assert type_counts.get('Deposit', 0) == 1

    def test_buy_maps_to_trade(self):
        """Buy row: sell comes from Total Amount (includes fee)."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-04 09:05:00,RBUY0001,Buy,990.10,USD,0.01500000,BTC,9.90,USD,"
            "1000.00,USD,Cash Balance,Cash Balance,Bitcoin Balance,"
            "1000.00,USD,66000.00,USD,,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'River'
            assert tx['buy'] == 0.01500000
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 1000.00       # Total Amount, not Sent Amount
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 9.90
            assert tx['fee_curr'] == 'USD'
            assert tx['comment'] == 'RBUY0001'
        finally:
            os.unlink(csv_path)

    def test_buy_zero_fee(self):
        """Buy with zero fee: fee_curr is empty string."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-11 09:00:00,RBUY000002,Buy,250.00,USD,0.00380000,BTC,0.00,,"
            "250.00,USD,Cash Balance,Cash Balance,Bitcoin Balance,"
            "250.00,USD,65800.00,USD,,True,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['sell'] == 250.00
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_send_maps_to_withdrawal_default(self):
        """Send without withdraw_to: exchange is River-Withdrawal, review comment added."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-15 18:30:00,RSND000001,Send,0.01880000,BTC,,,,"
            ",0.01880000,BTC,On Chain,Bitcoin Balance,"
            "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,"
            "2000.00,USD,67000.00,USD,"
            "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'River-Withdrawal'
            assert tx['sell'] == 0.01880000
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == 0.0
            assert 'Review' in tx['comment']
            assert 'RSND000001' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_withdraw_to(self):
        """Send with withdraw_to: exchange overridden, no review comment."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-15 18:30:00,RSND000001,Send,0.01880000,BTC,,,,"
            ",0.01880000,BTC,On Chain,Bitcoin Balance,"
            "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,"
            "2000.00,USD,67000.00,USD,"
            "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'Ledger'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_fee(self):
        """Send with on-chain fee: sell is sent amount only, fee tracked separately."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-25 10:15:00,RSND000002,Send,0.00500000,BTC,,,0.00000300,BTC,"
            "0.00500300,BTC,On Chain,Bitcoin Balance,"
            "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq,"
            "340.00,USD,68000.00,USD,"
            "cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['sell'] == 0.00500000    # NOT 0.00500300 (Total)
            assert tx['fee'] == 0.00000300
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_interest_payout_maps_to_interest_income(self):
        """Interest Payout row produces Interest Income with ref code comment."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-16 12:00:00,RINT000001,Interest Payout,,,0.00001200,BTC,,,"
            "0.00001200,BTC,Interest Earned,Cash Balance,Bitcoin Balance,"
            "1.05,USD,67250.00,USD,,False,Interest\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Interest Income'
            assert tx['exchange'] == 'River'
            assert tx['buy'] == 0.00001200
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
            assert tx['comment'] == 'RINT000001'
        finally:
            os.unlink(csv_path)

    def test_cash_deposit_maps_to_deposit(self):
        """Cash Deposit (USD) maps to Deposit with reference code in comment."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2024-03-04 09:00:00,RDEP0001,Cash Deposit,,,1000.00,USD,,,"
            "1000.00,USD,Cash Deposit,Checking ··0000,Cash Balance,"
            ",,,,,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'River'
            assert tx['buy'] == 1000.00
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
            assert tx['comment'] == 'RDEP0001'
        finally:
            os.unlink(csv_path)

    def test_altcoin_only_transaction_filtered(self):
        """Altcoin-only transactions (no BTC, no fiat) are filtered out."""
        csv_path = _make_csv(
            _ACCT_HDR +
            "2025-01-20 10:00:00,ABC123,Buy,100.00,ETH,5.0,LTC,0.50,ETH,"
            "100.50,ETH,Cash Balance,Cash Balance,Altcoin Balance,"
            "100.50,ETH,20.10,ETH,,False,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """Header-only file yields empty transaction list but valid colnames."""
        csv_path = _make_csv(_ACCT_HDR)
        try:
            parser = RiverImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Bitcoin Activity parsing
# ---------------------------------------------------------------------------

_BTC_HDR = (
    "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
    "Fee Amount,Fee Currency,Tag\n"
)


class TestRiverBtcActivityParsing:
    """Row-level parsing for River Bitcoin Activity format."""

    def test_parse_fixture_file(self):
        """Full Bitcoin Activity fixture: 2 Buy, 2 Send, 1 Interest."""
        parser = RiverImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "river_btc_sample.csv"))

        assert len(colnames) == 11
        assert len(transactions) == 5

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Withdrawal', 0) == 2
        assert type_counts.get('Interest Income', 0) == 1

    def test_buy_maps_to_trade(self):
        """Buy: sell = sent + fee (both USD -> total out of pocket)."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-04 09:05:00,990.10,USD,0.01500000,BTC,9.90,USD,Buy\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'River'
            assert tx['buy'] == 0.01500000
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 1000.00       # 990.10 + 9.90
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 9.90
            assert tx['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_buy_zero_fee(self):
        """Buy with empty fee: sell equals sent amount, fee fields zeroed."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-11 09:00:00,250.00,USD,0.00380000,BTC,,,Buy\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['sell'] == 250.00        # no fee to add
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_send_maps_to_withdrawal(self):
        """Empty-tag BTC send: Withdrawal with review comment."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-15 18:30:00,0.01880000,BTC,,,,,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'River-Withdrawal'
            assert tx['sell'] == 0.01880000
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == 0.0
            assert 'Review' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_withdraw_to(self):
        """Send with withdraw_to: exchange overridden, review comment suppressed."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-15 18:30:00,0.01880000,BTC,,,,,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to="ColdCard")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'ColdCard'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_send_with_fee(self):
        """Send with on-chain fee: sell is sent amount, fee tracked separately."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-25 10:15:00,0.00500000,BTC,,,0.00000300,BTC,\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Ledger")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['sell'] == 0.00500000
            assert tx['fee'] == 0.00000300
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_interest_maps_to_interest_income(self):
        """Tag=Interest row produces Interest Income transaction."""
        csv_path = _make_csv(
            _BTC_HDR +
            "2024-03-16 12:00:00,,,0.00001200,BTC,,,Interest\n"
        )
        try:
            parser = RiverImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Interest Income'
            assert tx['exchange'] == 'River'
            assert tx['buy'] == 0.00001200
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)

    def test_empty_file_returns_no_transactions(self):
        """Header-only Bitcoin Activity file yields empty list."""
        csv_path = _make_csv(_BTC_HDR)
        try:
            parser = RiverImporter()
            colnames, txs = parser.parse(csv_path)
            assert len(txs) == 0
            assert len(colnames) == 11
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRiverImporterRegistration:
    """River parser registration and discovery."""

    def setup_method(self):
        clear_registry()
        register(RiverImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_by_name(self):
        assert get_parser("River") is not None

    def test_registered_parser_is_river_importer(self):
        assert isinstance(get_parser("River"), RiverImporter)

    def test_appears_in_all_parsers(self):
        names = [p.name for p in get_all_parsers()]
        assert "River" in names


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestRiverImporterIntegration:
    """End-to-end import from River CSV into in-memory SQLite."""

    def setup_method(self):
        clear_registry()
        register(RiverImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_account_activity(self):
        """Account Activity fixture: parse, validate, import, verify counts."""
        parser = RiverImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "river_account_sample.csv"), withdraw_to="Ledger"
        )

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 6
        assert import_result['skipped'] == 0

        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}
        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Withdrawal', 0) == 2
        assert type_counts.get('Interest Income', 0) == 1
        assert type_counts.get('Deposit', 0) == 1

    def test_full_import_btc_activity(self):
        """Bitcoin Activity fixture: parse, validate, import, verify counts."""
        parser = RiverImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "river_btc_sample.csv"), withdraw_to="Ledger"
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
        assert type_counts.get('Withdrawal', 0) == 2
        assert type_counts.get('Interest Income', 0) == 1

        crypto.close()

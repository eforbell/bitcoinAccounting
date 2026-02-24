"""Tests for the Strike parser (IMP-007)."""

import tempfile
import os
from pathlib import Path

from imports.exchanges.strike import StrikeImporter, _parse_number
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


class TestStrikeImporterDetection:
    """Detection logic for Strike CSV exports."""

    def test_detects_strike_v2_export(self):
        """File with real Strike v2 columns is detected."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "ref123,Mar 15 2024 14:30:22,Deposit,850.00,,,,,,,,,\n"
        )
        try:
            parser = StrikeImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_old_strike_format(self):
        """Old assumed Strike format is NOT detected (needs real format)."""
        csv_path = _make_csv(
            "Date,Type,Description,BTC Amount,USD Amount,Fee (USD),Fee (BTC)\n"
            "2024-01-10 09:00:00,Purchase,DCA,0.05,2450.00,2.50,0\n"
        )
        try:
            parser = StrikeImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_coinbase_export(self):
        """Coinbase CSV is not detected as Strike."""
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
        """Full v2 fixture file parses without error and returns expected counts."""
        parser = StrikeImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "strike_sample.csv"))

        assert len(colnames) == 11
        assert 'trans_type' in colnames

        # Fixture v2: 7 USD Deposits, 5 Purchases, 2 on-chain BTC Sends,
        # 3 Lightning USD Sends, 1 reversal → 18 total transactions
        assert len(transactions) == 18

        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1
        assert type_counts.get('Deposit', 0) == 7  # 7 USD deposits
        assert type_counts.get('Trade', 0) == 5  # 5 Purchases
        assert type_counts.get('Withdrawal', 0) == 6  # 2 BTC + 3 Lightning USD + 1 reversal

    def test_purchase_maps_to_trade(self):
        """Purchase row maps to Trade with correct buy/sell/fee fields."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "ref123,Mar 15 2024 14:31:05,Purchase,-850.00,7.99,0.01234567,,68250.00,850.00,,,,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'Strike'
            assert tx['buy'] == 0.01234567
            assert tx['buy_curr'] == 'BTC'
            # sell = abs(usd_amount) — USD is negative in CSV
            assert tx['sell'] == 850.00
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 7.99
            assert tx['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_usd_deposit(self):
        """Deposit with positive USD amount maps to USD Deposit."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "ref456,Mar 15 2024 14:30:22,Deposit,850.00,,,,,,,,,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'Strike'
            assert tx['buy'] == 850.00
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.0
            assert tx['fee'] == 0.0
        finally:
            os.unlink(csv_path)

    def test_deposit_reversal(self):
        """Deposit with negative USD and 'Reversal' description maps to USD Withdrawal."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "ref789,Apr 10 2024 11:22:45,Deposit,-62.00,,,,,,,Reversal,,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Strike'
            assert tx['sell'] == 62.00
            assert tx['sell_curr'] == 'USD'
            assert 'Deposit reversal' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_onchain_btc_send_maps_to_withdrawal(self):
        """Send with BTC amount and bc1 destination maps to on-chain BTC Withdrawal."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refabc,Mar 23 2024 18:45:12,Send,,,-0.01963691,,,,bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,,"
            "a1a2a3a4a5a6a7a8b1b2b3b4b5b6b7b8c1c2c3c4c5c6c7c8d1d2d3d4d5d6d7d8,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to=None)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Strike-Withdrawal'
            assert tx['sell'] == 0.01963691
            assert tx['sell_curr'] == 'BTC'
            assert 'Destination:' in tx['comment']
            assert 'TxHash:' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_onchain_btc_send_with_withdraw_to(self):
        """On-chain BTC send with withdraw_to sets exchange to that wallet name."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refdef,Mar 23 2024 18:45:12,Send,,,-0.01963691,,,,bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,,"
            "a1a2a3a4a5a6a7a8b1b2b3b4b5b6b7b8c1c2c3c4c5c6c7c8d1d2d3d4d5d6d7d8,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Coldcard")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard'
            assert tx['sell'] == 0.01963691
            assert tx['sell_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_lightning_btc_send(self):
        """Lightning BTC send uses different target than on-chain (appends -Lightning)."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refghi,May 20 2024 08:45:22,Send,,,-0.00132500,,,,lnbc1325u1pnfake03dqqnp4qfakedata03,,"
            "d3d4d5d6d7d8e1e2e3e4e5e6e7e8f1f2f3f4a1a2a3a4a5a6a7a8b1b2b3b4b5b6,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Coldcard")
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard-Lightning'  # Different from on-chain
            assert tx['sell'] == 0.00132500
            assert tx['sell_curr'] == 'BTC'
            assert 'Lightning:' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_lightning_usd_send_with_fee(self):
        """Lightning USD send produces USD Withdrawal with fee."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refjkl,Apr 01 2024 20:10:15,Send,-35.50,0.07,,,,,lnbc355u1pnfake01dqqnp4qfakedata01,,"
            "e1e2e3e4e5e6e7e8f1f2f3f4f5f6f7f8a1a2a3a4a5a6a7a8b1b2b3b4b5b6b7b8,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Strike'  # USD stays at Strike
            assert tx['sell'] == 35.50
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 0.07
            assert tx['fee_curr'] == 'USD'
            assert 'Lightning USD:' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_lightning_usd_send_without_fee(self):
        """Lightning USD send without fee produces USD Withdrawal with empty fee_curr."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refmno,Apr 10 2024 11:25:30,Send,-61.75,,,,,,lnbc618u1pnfake02dqqnp4qfakedata02,,"
            "c1c2c3c4c5c6c7c8d1d2d3d4d5d6d7d8e1e2e3e4e5e6e7e8f1f2f3f4f5f6f7f8,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Strike'
            assert tx['sell'] == 61.75
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_receive_maps_to_btc_deposit(self):
        """Receive row maps to BTC Deposit with zero fees."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refpqr,Feb 20 2024 10:00:00,Receive,,,0.1,,,,,From savings wallet,,\n"
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

    def test_unknown_type_is_skipped(self):
        """Rows with an unrecognized type are dropped (return None)."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refstu,Mar 01 2024 08:00:00,Staking,,,0.001,,,,,Staking reward,,\n"
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
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
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
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "ref001,,Purchase,-500.00,0.50,0.01,,,,,,\n"
            "ref002,Jan 10 2024 09:00:00,,,,0.01,,,,,,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_onchain_btc_send_fee_preference(self):
        """On-chain BTC send prefers BTC fee, falls back to USD if BTC fee is zero."""
        csv_path = _make_csv(
            "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,"
            "Fee BTC,BTC Price,Cost Basis (USD),Destination,Description,Transaction Hash,Note\n"
            "refusd,Mar 23 2024 18:45:12,Send,,-1.50,-0.02,,,,bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4,,"
            "a1a2a3a4a5a6a7a8b1b2b3b4b5b6b7b8c1c2c3c4c5c6c7c8d1d2d3d4d5d6d7d8,\n"
        )
        try:
            parser = StrikeImporter()
            _, txs = parser.parse(csv_path, withdraw_to="Wallet")
            assert len(txs) == 1
            # Fee BTC is zero, so it should use Fee USD
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
        """Parse Strike v2 fixture and import all transactions; verify counts and types."""
        parser = StrikeImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "strike_sample.csv"), withdraw_to="Coldcard"
        )

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 18
        assert import_result['skipped'] == 0

        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Trade', 0) == 5
        assert type_counts.get('Withdrawal', 0) == 6  # 2 BTC + 3 Lightning USD + 1 reversal
        assert type_counts.get('Deposit', 0) == 7  # 7 USD deposits

    def test_integration_mixed_fiat_and_btc(self):
        """Full import with USD deposits, BTC purchases, and mixed withdrawals."""
        parser = StrikeImporter()
        _, transactions = parser.parse(
            str(FIXTURES_DIR / "strike_sample.csv"), withdraw_to="Coldcard"
        )

        # Verify currency diversity
        currencies = set()
        for tx in transactions:
            if tx['buy_curr']:
                currencies.add(tx['buy_curr'])
            if tx['sell_curr']:
                currencies.add(tx['sell_curr'])

        assert 'BTC' in currencies
        assert 'USD' in currencies

        # Verify Lightning BTC sends use different target
        lightning_btc_txs = [
            tx for tx in transactions
            if tx['trans_type'] == 'Withdrawal' and
            tx['sell_curr'] == 'BTC' and
            'Lightning:' in tx.get('comment', '')
        ]
        # Fixture has no Lightning BTC sends, only Lightning USD, so this should be 0
        assert len(lightning_btc_txs) == 0

        # Verify on-chain BTC sends go to withdraw_to
        onchain_btc_txs = [
            tx for tx in transactions
            if tx['trans_type'] == 'Withdrawal' and
            tx['sell_curr'] == 'BTC' and
            'Destination:' in tx.get('comment', '')
        ]
        assert len(onchain_btc_txs) == 2
        assert all(tx['exchange'] == 'Coldcard' for tx in onchain_btc_txs)


"""Tests for the Kraken parser (IMP-006)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.exchanges.kraken import KrakenImporter, _normalize_asset, _is_btc_related
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


class TestKrakenAssetNormalization:
    """Tests for Kraken asset name normalization."""

    def test_xxbt_to_btc(self):
        """XXBT normalizes to BTC."""
        assert _normalize_asset('XXBT') == 'BTC'
        assert _normalize_asset('xxbt') == 'BTC'

    def test_xbt_to_btc(self):
        """XBT normalizes to BTC."""
        assert _normalize_asset('XBT') == 'BTC'
        assert _normalize_asset('xbt') == 'BTC'

    def test_zusd_to_usd(self):
        """ZUSD normalizes to USD."""
        assert _normalize_asset('ZUSD') == 'USD'
        assert _normalize_asset('zusd') == 'USD'

    def test_unknown_asset_uppercased(self):
        """Unknown assets are just uppercased."""
        assert _normalize_asset('xeth') == 'XETH'
        assert _normalize_asset('DOGE') == 'DOGE'

    def test_is_btc_related(self):
        """_is_btc_related correctly identifies BTC variants."""
        assert _is_btc_related('XXBT') is True
        assert _is_btc_related('XBT') is True
        assert _is_btc_related('xxbt') is True
        assert _is_btc_related('ZUSD') is False
        assert _is_btc_related('XETH') is False


class TestKrakenImporterDetection:
    """Tests for KrakenImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_kraken_format(self):
        """detect() returns True for Kraken ledger format."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1234","TBUY01","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0","0.05"\n'
        )
        try:
            parser = KrakenImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_coinbase_format(self):
        """detect() returns False for Coinbase format."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,Test\n"
        )
        try:
            parser = KrakenImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for unrelated CSV."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = KrakenImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestKrakenTradePairMatching:
    """Tests for Kraken trade pair matching logic - the critical part."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def test_buy_btc_with_usd(self):
        """Two-row trade: buy BTC with USD."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE1","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0","0.05"\n'
            '"L2","TRADE1","2024-01-15 10:30:00","trade","","currency","ZUSD","-2500.00","6.50","7500"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.05)
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == pytest.approx(2500.0)
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == pytest.approx(6.50)
            assert tx['fee_curr'] == 'USD'
            assert 'TRADE1' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_sell_btc_for_usd(self):
        """Two-row trade: sell BTC for USD."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE2","2024-02-01 14:00:00","trade","","currency","XXBT","-0.02","0","0.03"\n'
            '"L2","TRADE2","2024-02-01 14:00:00","trade","","currency","ZUSD","1040.00","2.70","8537"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(1040.0)
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == pytest.approx(0.02)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(2.70)
        finally:
            os.unlink(csv_path)

    def test_fee_on_buy_leg(self):
        """Fee can be on the buy leg instead of sell leg."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE3","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0.0001","0.05"\n'
            '"L2","TRADE3","2024-01-15 10:30:00","trade","","currency","ZUSD","-2500.00","0","7500"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['fee'] == pytest.approx(0.0001)
            assert tx['fee_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_fees_on_both_legs(self):
        """Fees on both legs are summed (unusual but possible)."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE4","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0.0001","0.05"\n'
            '"L2","TRADE4","2024-01-15 10:30:00","trade","","currency","ZUSD","-2500.00","5.00","7500"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            # Fees from both legs summed - fee_curr will be from last leg with fee
            assert tx['fee'] == pytest.approx(5.0001)
        finally:
            os.unlink(csv_path)

    def test_incomplete_trade_pair_skipped(self):
        """Single-row trade (incomplete pair) is skipped."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE5","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0","0.05"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 0
        finally:
            os.unlink(csv_path)

    def test_non_btc_trade_filtered(self):
        """Trade not involving BTC is filtered out."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE6","2024-01-15 10:30:00","trade","","currency","XETH","1.0","0","1.0"\n'
            '"L2","TRADE6","2024-01-15 10:30:00","trade","","currency","ZUSD","-3000.00","7.80","5000"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 0
        finally:
            os.unlink(csv_path)

    def test_btc_eth_trade_included(self):
        """Trade of BTC for ETH is included (BTC involved)."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","TRADE7","2024-01-15 10:30:00","trade","","currency","XXBT","0.05","0","0.05"\n'
            '"L2","TRADE7","2024-01-15 10:30:00","trade","","currency","XETH","-1.5","0.01","8.5"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['buy'] == pytest.approx(0.05)
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == pytest.approx(1.5)
            assert tx['sell_curr'] == 'XETH'
        finally:
            os.unlink(csv_path)


class TestKrakenSingleRowTransactions:
    """Tests for single-row transaction types (deposit, withdrawal, staking)."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def test_btc_deposit(self):
        """BTC deposit parsed correctly."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","DEP001","2024-02-15 09:00:00","deposit","","currency","XXBT","0.10","0","0.13"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.10)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Kraken'
        finally:
            os.unlink(csv_path)

    def test_non_btc_deposit_filtered(self):
        """Non-BTC deposit is filtered out."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","DEP002","2024-02-15 09:00:00","deposit","","currency","XETH","0.50","0","1.5"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 0
        finally:
            os.unlink(csv_path)

    def test_btc_withdrawal_with_withdraw_to(self):
        """BTC withdrawal with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","WITH001","2024-03-01 12:00:00","withdrawal","","currency","XXBT","-0.01","0.0001","0.12"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['sell'] == pytest.approx(0.01)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.0001)
            assert tx['exchange'] == 'Ledger'
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_btc_withdrawal_without_withdraw_to(self):
        """BTC withdrawal without withdraw_to uses default and adds review comment."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","WITH002","2024-03-01 12:00:00","withdrawal","","currency","XXBT","-0.01","0.0001","0.12"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Kraken-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_staking_reward(self):
        """Staking reward parsed as Interest Income."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","STAK001","2024-03-15 00:00:00","staking","","currency","XXBT","0.00005","0","0.12005"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.00005)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Kraken'
        finally:
            os.unlink(csv_path)

    def test_reward_type(self):
        """'reward' type also parsed as Interest Income."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","REW001","2024-05-01 00:00:00","reward","staking","currency","XXBT","0.00002","0","0.12007"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.00002)
            assert 'staking' in tx['comment']
        finally:
            os.unlink(csv_path)


class TestKrakenImporterParsing:
    """General parsing tests for KrakenImporter."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped kraken_sample.csv fixture end-to-end."""
        parser = KrakenImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "kraken_sample.csv"))

        # Should have: 2 trades (BTC buy, BTC sell), 1 deposit, 1 withdrawal, 2 staking
        # ETH trade and ETH deposit should be filtered out
        assert len(transactions) == 6

        types = [tx['trans_type'] for tx in transactions]
        assert types.count('Trade') == 2
        assert types.count('Deposit') == 1
        assert types.count('Withdrawal') == 1
        assert types.count('Interest Income') == 2

    def test_transactions_sorted_by_time(self):
        """Transactions are returned sorted by timestamp."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","DEP002","2024-03-01 00:00:00","deposit","","currency","XXBT","0.1","0","0.1"\n'
            '"L2","DEP001","2024-01-01 00:00:00","deposit","","currency","XXBT","0.2","0","0.2"\n'
            '"L3","DEP003","2024-02-01 00:00:00","deposit","","currency","XXBT","0.3","0","0.3"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 3
            assert transactions[0]['created_date'] == '2024-01-01 00:00:00'
            assert transactions[1]['created_date'] == '2024-02-01 00:00:00'
            assert transactions[2]['created_date'] == '2024-03-01 00:00:00'
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_case_insensitive_columns(self):
        """Column matching is case-insensitive."""
        csv_path = _make_csv(
            '"TXID","REFID","TIME","TYPE","SUBTYPE","ACLASS","ASSET","AMOUNT","FEE","BALANCE"\n'
            '"L1","DEP001","2024-02-15 09:00:00","deposit","","currency","XXBT","0.10","0","0.13"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
        finally:
            os.unlink(csv_path)


class TestKrakenImporterRegistration:
    """Tests for KrakenImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """KrakenImporter is retrievable by name 'kraken'."""
        parser = get_parser("kraken")
        assert parser is not None
        assert isinstance(parser, KrakenImporter)

    def test_source_type_is_exchange(self):
        """source_type is 'exchange'."""
        parser = KrakenImporter()
        assert parser.source_type == "exchange"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Kraken columns."""
        parser = KrakenImporter()
        help_text = parser.get_format_help()
        assert "Kraken" in help_text
        assert "txid" in help_text
        assert "refid" in help_text


class TestKrakenImporterIntegration:
    """Integration tests for Kraken parser with database import."""

    def setup_method(self):
        clear_registry()
        register(KrakenImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Kraken CSV and import all transactions to database."""
        parser = KrakenImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "kraken_sample.csv"), withdraw_to="Ledger")

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 6
        assert import_result['skipped'] == 0

        # Verify all types imported
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Trade', 0) == 2
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Interest Income', 0) == 2

        crypto.close()

    def test_refid_preserved_in_comment(self):
        """refid is preserved in comment for traceability."""
        csv_path = _make_csv(
            '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
            '"L1","UNIQUE-REFID-123","2024-02-15 09:00:00","deposit","","currency","XXBT","0.10","0","0.13"\n'
        )
        try:
            parser = KrakenImporter()
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger")
            assert len(rows) == 1
            assert 'UNIQUE-REFID-123' in rows[0]['comment']
            crypto.close()
        finally:
            os.unlink(csv_path)


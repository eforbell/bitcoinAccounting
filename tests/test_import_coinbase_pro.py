"""Tests for the Coinbase Pro parser (FIAT-005b)."""

import tempfile
import os
from pathlib import Path

import pytest

from imports.exchanges.coinbase_pro import CoinbaseProImporter, _parse_number
from imports.registry import register, get_parser, get_all_parsers, clear_registry
from imports.validation import validate_batch
from db import SqliteBackend
from bitcoinAccounts import CryptoAccounts

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"

# Shared header constant
_HDR = "portfolio,type,time,amount,balance,amount/balance unit,transfer id,trade id,order id\n"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestCoinbaseProImporterDetection:
    """Detection logic for Coinbase Pro account statement exports."""

    def test_detects_coinbase_pro_export(self):
        """File with portfolio, trade id, amount/balance unit is detected."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:22:09.503Z,-142.35,4019.35,USD,,112847531,c3d4e5f6\n"
        )
        try:
            parser = CoinbaseProImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_rejects_standard_coinbase_export(self):
        """Standard Coinbase CSV (different columns) is not detected."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15 10:00:00 UTC,Buy,BTC,0.05,USD,30000,1500,1502.50,2.50,\n"
        )
        try:
            parser = CoinbaseProImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_kraken_export(self):
        """Kraken CSV (has refid, not trade id) is not detected."""
        csv_path = _make_csv(
            "txid,refid,time,type,subtype,aclass,asset,amount,fee,balance\n"
            "TX123,REF456,2024-01-01 10:00:00,trade,,currency,BTC,0.5,0.001,0.5\n"
        )
        try:
            parser = CoinbaseProImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_rejects_empty_file(self):
        """Empty file is not detected."""
        csv_path = _make_csv("")
        try:
            parser = CoinbaseProImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)


class TestCoinbaseProParseNumber:
    """Unit tests for the _parse_number helper."""

    def test_plain_number(self):
        assert _parse_number("0.00253") == 0.00253

    def test_negative_number(self):
        assert _parse_number("-142.35") == -142.35

    def test_large_precision(self):
        assert _parse_number("0.0025300000000000") == 0.00253

    def test_empty_string(self):
        assert _parse_number("") == 0.0

    def test_whitespace_only(self):
        assert _parse_number("   ") == 0.0

    def test_non_numeric(self):
        assert _parse_number("abc") == 0.0


class TestCoinbaseProTradeParsing:
    """Trade pairing logic: group match rows by trade_id and pair buy/sell legs."""

    def test_btc_buy_trade_with_fee(self):
        """BTC buy: 2 match rows (USD sell, BTC buy) + 1 fee row."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:22:09.503Z,-142.3500,4019.35,USD,,112847531,c3d4e5f6\n"
            "default,match,2021-03-15T14:22:09.503Z,0.0025300000,0.00253,BTC,,112847531,c3d4e5f6\n"
            "default,fee,2021-03-15T14:22:09.503Z,-0.7117500000,4018.64,USD,,112847531,c3d4e5f6\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['exchange'] == 'CoinbasePro'
            assert tx['buy'] == 0.00253
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 142.35
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 0.71175
            assert tx['fee_curr'] == 'USD'
            assert 'Trade ID: 112847531' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_btc_sell_trade(self):
        """BTC sell: BTC is sell side, USD is buy side."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:22:09.503Z,565.75,5000.00,USD,,99887766,a1b2c3\n"
            "default,match,2021-03-15T14:22:09.503Z,-0.0100000000,0.00,BTC,,99887766,a1b2c3\n"
            "default,fee,2021-03-15T14:22:09.503Z,-2.82875,4997.17,USD,,99887766,a1b2c3\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == 565.75
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.01
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == 2.82875
            assert tx['fee_curr'] == 'USD'
        finally:
            os.unlink(csv_path)

    def test_trade_without_fee_row(self):
        """Trade with only 2 match rows (no fee) is still valid."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:22:09.503Z,-100.00,900.00,USD,,11111111,xyz123\n"
            "default,match,2021-03-15T14:22:09.503Z,0.00177000,0.00177,BTC,,11111111,xyz123\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == 0.00177
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == 100.00
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == 0.0
            assert tx['fee_curr'] == ''
        finally:
            os.unlink(csv_path)

    def test_multiple_trades_sorted_by_time(self):
        """Multiple trades are parsed and sorted by timestamp."""
        csv_path = _make_csv(
            _HDR +
            # Trade 1 at 14:22:09
            "default,match,2021-03-15T14:22:09.503Z,-142.35,4019.35,USD,,112847531,c3d4e5f6\n"
            "default,match,2021-03-15T14:22:09.503Z,0.00253,0.00253,BTC,,112847531,c3d4e5f6\n"
            "default,fee,2021-03-15T14:22:09.503Z,-0.71175,4018.64,USD,,112847531,c3d4e5f6\n"
            # Trade 2 at 14:22:11
            "default,match,2021-03-15T14:22:11.716Z,-356.72,3661.92,USD,,112847533,c3d4e5f6\n"
            "default,match,2021-03-15T14:22:11.716Z,0.00634,0.00887,BTC,,112847533,c3d4e5f6\n"
            "default,fee,2021-03-15T14:22:11.716Z,-1.7836,3660.14,USD,,112847533,c3d4e5f6\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 2

            # Verify ordering
            assert txs[0]['created_date'] < txs[1]['created_date']
            assert txs[0]['buy'] == 0.00253
            assert txs[1]['buy'] == 0.00634
        finally:
            os.unlink(csv_path)


class TestCoinbaseProBTCFilter:
    """BTC filter: only import trades where BTC is on at least one side."""

    def test_ltc_usd_trade_filtered(self):
        """LTC/USD trade (no BTC) is filtered out."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:12:07.221Z,-185.43,4812.57,USD,,44781201,a1b2c3\n"
            "default,match,2021-03-15T14:12:07.221Z,0.8250,0.8250,LTC,,44781201,a1b2c3\n"
            "default,fee,2021-03-15T14:12:07.221Z,-0.92715,4811.64,USD,,44781201,a1b2c3\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0  # Altcoin-only trade filtered
        finally:
            os.unlink(csv_path)

    def test_link_usd_trade_filtered(self):
        """LINK/USD trade is filtered out."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:15:41.098Z,-275.62,4163.08,USD,,15207744,b2c3d4\n"
            "default,match,2021-03-15T14:15:41.098Z,8.5000,18.5000,LINK,,15207744,b2c3d4\n"
            "default,fee,2021-03-15T14:15:41.098Z,-1.3781,4161.70,USD,,15207744,b2c3d4\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0
        finally:
            os.unlink(csv_path)

    def test_btc_usd_trade_imported(self):
        """BTC/USD trade is imported (BTC on one side)."""
        csv_path = _make_csv(
            _HDR +
            "default,match,2021-03-15T14:22:09.503Z,-142.35,4019.35,USD,,112847531,c3d4e5f6\n"
            "default,match,2021-03-15T14:22:09.503Z,0.00253,0.00253,BTC,,112847531,c3d4e5f6\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            assert txs[0]['buy_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)


class TestCoinbaseProDepositParsing:
    """Deposit parsing: BTC and fiat allowed, altcoins filtered."""

    def test_usd_deposit(self):
        """USD deposit produces Deposit(buy_curr='USD')."""
        csv_path = _make_csv(
            _HDR +
            "default,deposit,2021-04-05T17:22:38.914Z,750.00,1566.71,USD,3a7b8c9d-0e1f,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['exchange'] == 'CoinbasePro'
            assert tx['buy'] == 750.00
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == 0.0
            assert tx['sell_curr'] == ''
            assert 'Transfer ID: 3a7b8c9d-0e1f' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_btc_deposit(self):
        """BTC deposit produces Deposit(buy_curr='BTC')."""
        csv_path = _make_csv(
            _HDR +
            "default,deposit,2021-04-10T12:00:00.000Z,0.5000,0.5000,BTC,abc123-def456,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == 0.5
            assert tx['buy_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_altcoin_deposit_filtered(self):
        """CGLD deposit (altcoin, not fiat) is filtered out."""
        csv_path = _make_csv(
            _HDR +
            "default,deposit,2021-03-18T09:44:33.105Z,75.20,75.20,CGLD,9c3d4e5f-6a7b,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0  # Altcoin deposit filtered
        finally:
            os.unlink(csv_path)

    def test_usdc_deposit_allowed(self):
        """USDC deposit (stablecoin = fiat-equivalent) is allowed."""
        csv_path = _make_csv(
            _HDR +
            "default,deposit,2021-04-01T08:00:00.000Z,1000.00,1000.00,USDC,xyz-789,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == 1000.00
            assert tx['buy_curr'] == 'USDC'
        finally:
            os.unlink(csv_path)


class TestCoinbaseProWithdrawalParsing:
    """Withdrawal parsing: BTC and fiat allowed, altcoins filtered."""

    def test_btc_withdrawal_with_withdraw_to(self):
        """BTC withdrawal with --withdraw-to uses specified wallet."""
        csv_path = _make_csv(
            _HDR +
            "default,withdrawal,2021-03-15T22:05:18.442Z,-0.01611,0.00005,BTC,7a1b2c3d-4e5f,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path, withdraw_to='Coldcard')
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Coldcard'
            assert tx['sell'] == 0.01611
            assert tx['sell_curr'] == 'BTC'
            assert 'Transfer ID: 7a1b2c3d-4e5f' in tx['comment']
            # No review note when withdraw_to is specified
            assert 'Review' not in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_btc_withdrawal_without_withdraw_to(self):
        """BTC withdrawal without --withdraw-to uses placeholder and review note."""
        csv_path = _make_csv(
            _HDR +
            "default,withdrawal,2021-03-15T22:05:18.442Z,-0.01611,0.00005,BTC,7a1b2c3d-4e5f,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 1
            tx = txs[0]

            assert tx['exchange'] == 'CoinbasePro-Withdrawal'
            assert tx['sell'] == 0.01611
            assert tx['sell_curr'] == 'BTC'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_usd_withdrawal(self):
        """USD withdrawal stays at CoinbasePro (bank transfer)."""
        csv_path = _make_csv(
            _HDR +
            "default,withdrawal,2021-04-01T14:00:00.000Z,-500.00,1066.71,USD,bank-transfer-123,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path, withdraw_to='Coldcard')
            assert len(txs) == 1
            tx = txs[0]

            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'CoinbasePro'  # Fiat stays at exchange
            assert tx['sell'] == 500.00
            assert tx['sell_curr'] == 'USD'
            assert 'Fiat withdrawal' in tx['comment']
            assert 'Transfer ID: bank-transfer-123' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_altcoin_withdrawal_filtered(self):
        """LTC withdrawal (altcoin) is filtered out."""
        csv_path = _make_csv(
            _HDR +
            "default,withdrawal,2021-03-16T01:33:21.607Z,-2.47495,0.00005,LTC,8b2c3d4e-5f6a,,\n"
        )
        try:
            parser = CoinbaseProImporter()
            _, txs = parser.parse(csv_path)
            assert len(txs) == 0  # Altcoin withdrawal filtered
        finally:
            os.unlink(csv_path)


class TestCoinbaseProRegistration:
    """Registry integration tests."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseProImporter)

    def teardown_method(self):
        clear_registry()

    def test_parser_is_registered(self):
        """CoinbaseProImporter is registered via @register decorator."""
        all_parsers = get_all_parsers()
        names = {p.name for p in all_parsers}
        assert 'CoinbasePro' in names

    def test_parser_source_type(self):
        """CoinbasePro parser is tagged as 'exchange' source type."""
        all_parsers = get_all_parsers()
        cbpro_parser = next(p for p in all_parsers if p.name == 'CoinbasePro')
        assert cbpro_parser.source_type == 'exchange'

    def test_get_parser_by_name(self):
        """get_parser() retrieves CoinbasePro parser by name."""
        parser = get_parser("CoinbasePro")
        assert parser is not None
        assert parser.name == 'CoinbasePro'
        assert isinstance(parser, CoinbaseProImporter)


class TestCoinbaseProIntegration:
    """End-to-end tests with real fixture file and database import."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseProImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_fixture_file(self):
        """Fixture: 5 BTC trades + 3 BTC withdrawals + 2 USD deposits.

        Altcoin rows (LTC, LINK, CGLD) are filtered out.
        """
        parser = CoinbaseProImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_pro_sample.csv"))

        assert len(colnames) == 11

        # Count transaction types
        type_counts: dict[str, int] = {}
        for tx in transactions:
            type_counts[tx['trans_type']] = type_counts.get(tx['trans_type'], 0) + 1

        # 5 BTC trades (rows 11-13, 14-16, 17-19, 23-25, 27-29)
        assert type_counts.get('Trade', 0) == 5

        # 3 BTC withdrawals (rows 20, 26, 30)
        assert type_counts.get('Withdrawal', 0) == 3

        # 2 USD deposits (rows 35, 36)
        assert type_counts.get('Deposit', 0) == 2

        # Total: 10 transactions
        assert len(transactions) == 10

    def test_full_import_to_database(self):
        """Import Coinbase Pro fixture to database via CryptoAccounts."""
        backend = SqliteBackend(":memory:")
        ca = CryptoAccounts(backend)

        parser = CoinbaseProImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_pro_sample.csv"))

        # Validate before import
        result = validate_batch(transactions)
        assert result.error_count == 0, f"Validation errors: {result.errors}"

        # Import
        import_result = ca.import_transactions(transactions)
        assert import_result['imported'] == 10  # 5 trades + 3 withdrawals + 2 deposits

        # Verify transaction counts
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        # 5 BTC trades, 3 BTC withdrawals, 2 USD deposits
        assert type_counts.get('Trade', 0) == 5
        assert type_counts.get('Withdrawal', 0) == 3
        assert type_counts.get('Deposit', 0) == 2

        # Verify deposits are USD
        deposits = backend.execute("SELECT buy_curr FROM ledger WHERE trans_type = 'Deposit'")
        assert len(deposits) == 2
        assert all(d['buy_curr'] == 'USD' for d in deposits)

        # Verify withdrawals are BTC
        withdrawals = backend.execute("SELECT sell_curr FROM ledger WHERE trans_type = 'Withdrawal'")
        assert len(withdrawals) == 3
        assert all(w['sell_curr'] == 'BTC' for w in withdrawals)

        # Verify trades have BTC on one side
        trades = backend.execute("SELECT buy_curr, sell_curr FROM ledger WHERE trans_type = 'Trade'")
        assert len(trades) == 5
        for trade in trades:
            assert trade['buy_curr'] == 'BTC' or trade['sell_curr'] == 'BTC'

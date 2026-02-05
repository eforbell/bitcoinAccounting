"""Tests for the Native format parser (IMP-004)."""

import pytest
import tempfile
import os
from pathlib import Path

from imports.exchanges.native import NativeImporter, _detect_format, _CLEAN_MAP, _LEGACY_MAP
from imports.registry import register, get_parser, clear_registry

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestNativeImporterDetection:
    """Tests for NativeImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(NativeImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_clean_format(self):
        """detect() returns True for a file with clean column names."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
            "Deposit,1.0,BTC,,,,,River,,,2024-01-01 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_detects_legacy_format(self):
        """detect() returns True for a file with legacy column names."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Deposit,1.0,BTC,,,,,River,,,2024-01-01 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = NativeImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_empty_file(self):
        """detect() returns False for an empty file."""
        csv_path = _make_csv("")
        try:
            parser = NativeImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_missing_file(self):
        """detect() returns False for a nonexistent file."""
        parser = NativeImporter()
        assert parser.detect("/no/such/file.csv") is False

    def test_detect_format_helper_clean(self):
        """_detect_format returns _CLEAN_MAP for clean headers."""
        result = _detect_format([
            "trans_type", "buy", "buy_curr", "sell", "sell_curr",
            "fee", "fee_curr", "exchange", "group", "comment", "created_date",
        ])
        assert result is _CLEAN_MAP

    def test_detect_format_helper_legacy(self):
        """_detect_format returns _LEGACY_MAP for legacy headers."""
        result = _detect_format([
            "Type", "Buy", "Buy Cur.", "Sell", "Sell Cur.",
            "Fee", "Fee Cur.", "Exchange", "Group", "Comment", "Date",
        ])
        assert result is _LEGACY_MAP

    def test_detect_format_helper_unknown(self):
        """_detect_format returns None for unrecognised headers."""
        assert _detect_format(["foo", "bar", "baz"]) is None

    def test_detect_format_case_insensitive(self):
        """_detect_format matches headers regardless of case."""
        result = _detect_format([
            "TRANS_TYPE", "Buy", "Buy_Curr", "SELL", "sell_curr",
            "Fee", "fee_curr", "EXCHANGE", "Group", "comment", "Created_Date",
        ])
        assert result is _CLEAN_MAP


class TestNativeImporterCleanFormat:
    """Tests for parsing the clean column format."""

    def setup_method(self):
        clear_registry()
        register(NativeImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped native_sample.csv fixture end-to-end."""
        parser = NativeImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "native_sample.csv"))

        assert len(transactions) == 4

        # Trade
        trade = transactions[0]
        assert trade['trans_type'] == 'Trade'
        assert trade['buy'] == pytest.approx(0.05)
        assert trade['buy_curr'] == 'BTC'
        assert trade['sell'] == pytest.approx(2500.0)
        assert trade['sell_curr'] == 'USD'
        assert trade['fee'] == pytest.approx(10.0)
        assert trade['exchange'] == 'Coinbase'
        assert trade['comment'] == 'Purchase'

        # Deposit
        deposit = transactions[1]
        assert deposit['trans_type'] == 'Deposit'
        assert deposit['buy'] == pytest.approx(0.1)
        assert deposit['buy_curr'] == 'BTC'
        assert deposit['sell'] == 0.0
        assert deposit['exchange'] == 'River'

        # Withdrawal
        withdraw = transactions[2]
        assert withdraw['trans_type'] == 'Withdrawal'
        assert withdraw['sell'] == pytest.approx(0.02)
        assert withdraw['sell_curr'] == 'BTC'
        assert withdraw['fee'] == pytest.approx(0.0001)
        assert withdraw['exchange'] == 'Ledger'

        # Interest Income
        interest = transactions[3]
        assert interest['trans_type'] == 'Interest Income'
        assert interest['buy'] == pytest.approx(0.001)
        assert interest['buy_curr'] == 'BTC'
        assert interest['exchange'] == 'Gemini'

    def test_colnames_are_clean_keys(self):
        """Returned colnames match the clean format field names."""
        parser = NativeImporter()
        colnames, _ = parser.parse(str(FIXTURES_DIR / "native_sample.csv"))
        assert colnames == list(_CLEAN_MAP.values())

    def test_empty_rows_are_skipped(self):
        """Rows with no trans_type value are silently skipped."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
            "Deposit,0.5,BTC,,,,,River,,,2024-01-01 00:00:00\n"
            ",,,,,,,,,,\n"
            "Trade,0.1,BTC,5000,USD,10,USD,Coinbase,,,2024-01-02 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 2
        finally:
            os.unlink(csv_path)

    def test_header_only_file_returns_empty(self):
        """File with header but no data rows returns empty list."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_numeric_fields_handle_dollar_signs_and_commas(self):
        """Numbers with $ prefix or , separators are parsed correctly."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
            'Trade,0.05,BTC,"$2,500.00",USD,$10.00,USD,Coinbase,,,2024-01-15 10:30:00\n'
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions[0]['sell'] == pytest.approx(2500.0)
            assert transactions[0]['fee'] == pytest.approx(10.0)
        finally:
            os.unlink(csv_path)

    def test_whitespace_in_column_names_is_stripped(self):
        """Leading/trailing whitespace in CSV headers is handled."""
        csv_path = _make_csv(
            " trans_type , buy , buy_curr , sell , sell_curr , fee , fee_curr , exchange , group , comment , created_date \n"
            "Deposit,1.0,BTC,,,,,River,,,2024-01-01 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
        finally:
            os.unlink(csv_path)


class TestNativeImporterLegacyFormat:
    """Tests for parsing the legacy export column format."""

    def setup_method(self):
        clear_registry()
        register(NativeImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_legacy_trade(self):
        """Legacy format Trade is mapped correctly."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Trade,0.1,BTC,5000,USD,25,USD,Kraken,,Bought on Kraken,2024-03-10 12:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.1)
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == pytest.approx(5000.0)
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == pytest.approx(25.0)
            assert tx['exchange'] == 'Kraken'
            assert tx['comment'] == 'Bought on Kraken'
            assert tx['created_date'] == '2024-03-10 12:00:00'
        finally:
            os.unlink(csv_path)

    def test_parse_legacy_deposit(self):
        """Legacy format Deposit is mapped correctly."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Deposit,0.25,BTC,,,,,Strike,,DCA,2024-04-01 09:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[0]['buy'] == pytest.approx(0.25)
            assert transactions[0]['exchange'] == 'Strike'
        finally:
            os.unlink(csv_path)

    def test_parse_legacy_withdrawal(self):
        """Legacy format Withdrawal is mapped correctly."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Withdrawal,,,0.05,BTC,0.0002,BTC,Coinbase,,Withdraw to Ledger,2024-04-15 16:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
            assert transactions[0]['sell'] == pytest.approx(0.05)
            assert transactions[0]['sell_curr'] == 'BTC'
            assert transactions[0]['fee'] == pytest.approx(0.0002)
        finally:
            os.unlink(csv_path)

    def test_parse_legacy_interest_income(self):
        """Legacy format Interest Income is mapped correctly."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Interest Income,0.002,BTC,,,,,Gemini,,Earn,2024-05-01 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Interest Income'
            assert transactions[0]['buy'] == pytest.approx(0.002)
        finally:
            os.unlink(csv_path)

    def test_parse_legacy_multiple_rows(self):
        """Legacy format file with multiple transaction types."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Trade,0.1,BTC,5000,USD,10,USD,Coinbase,,,2024-01-15 10:00:00\n"
            "Deposit,0.05,BTC,,,,,River,,,2024-01-16 10:00:00\n"
            "Withdrawal,,,0.02,BTC,0.0001,BTC,Ledger,,,2024-01-17 10:00:00\n"
            "Interest Income,0.001,BTC,,,,,Gemini,,,2024-01-18 10:00:00\n"
        )
        try:
            parser = NativeImporter()
            _, transactions = parser.parse(csv_path)
            assert len(transactions) == 4
            types = [tx['trans_type'] for tx in transactions]
            assert types == ['Trade', 'Deposit', 'Withdrawal', 'Interest Income']
        finally:
            os.unlink(csv_path)

    def test_legacy_colnames_still_return_clean_keys(self):
        """Even when parsing legacy format, colnames uses clean field names."""
        csv_path = _make_csv(
            "Type,Buy,Buy Cur.,Sell,Sell Cur.,Fee,Fee Cur.,Exchange,Group,Comment,Date\n"
            "Deposit,1.0,BTC,,,,,River,,,2024-01-01 00:00:00\n"
        )
        try:
            parser = NativeImporter()
            colnames, _ = parser.parse(csv_path)
            assert colnames == list(_CLEAN_MAP.values())
        finally:
            os.unlink(csv_path)


class TestNativeImporterRegistration:
    """Tests for NativeImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(NativeImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """NativeImporter is retrievable by name 'native'."""
        parser = get_parser("native")
        assert parser is not None
        assert isinstance(parser, NativeImporter)

    def test_source_type_is_native(self):
        """source_type is 'native', not 'exchange'."""
        parser = NativeImporter()
        assert parser.source_type == "native"

    def test_format_help_includes_expected_columns(self):
        """get_format_help() lists all expected columns."""
        parser = NativeImporter()
        help_text = parser.get_format_help()
        assert "Native" in help_text
        assert "trans_type" in help_text
        assert "created_date" in help_text
        assert "buy_curr" in help_text


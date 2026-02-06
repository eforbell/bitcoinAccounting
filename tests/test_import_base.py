"""Tests for BaseImporter and registry (IMP-001)."""

import pytest
import tempfile
import os

from imports.base import BaseImporter, FIAT_CURRENCIES, is_fiat
from imports.registry import (
    register,
    get_parser,
    get_all_parsers,
    detect_parser,
    get_parser_names,
    clear_registry,
    _REGISTRY,
)


class TestBaseImporter:
    """Tests for BaseImporter abstract class."""

    def test_base_importer_has_required_attributes(self):
        """BaseImporter should have all required class attributes."""
        assert hasattr(BaseImporter, 'name')
        assert hasattr(BaseImporter, 'source_type')
        assert hasattr(BaseImporter, 'file_patterns')
        assert hasattr(BaseImporter, 'description')
        assert hasattr(BaseImporter, 'expected_columns')

    def test_base_importer_default_values(self):
        """BaseImporter defaults should be sensible."""
        assert BaseImporter.name == "Unknown"
        assert BaseImporter.source_type == "exchange"
        assert BaseImporter.file_patterns == ["*.csv"]
        assert BaseImporter.description == "No description"
        assert BaseImporter.expected_columns == []

    def test_cannot_instantiate_base_importer(self):
        """BaseImporter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseImporter()

    def test_get_format_help(self):
        """Test get_format_help returns formatted string."""
        # Create a concrete implementation for testing
        class TestImporter(BaseImporter):
            name = "TestParser"
            source_type = "exchange"
            description = "Test parser for unit tests"
            expected_columns = ["col1", "col2", "col3"]

            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        help_text = parser.get_format_help()

        assert "Format: TestParser" in help_text
        assert "Type: exchange" in help_text
        assert "Test parser for unit tests" in help_text
        assert "col1" in help_text
        assert "col2" in help_text
        assert "col3" in help_text

    def test_withdrawal_exchange_with_user_specified(self):
        """_get_withdrawal_exchange should use user-specified value."""
        class TestImporter(BaseImporter):
            name = "TestParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        assert parser._get_withdrawal_exchange("Ledger") == "Ledger"
        assert parser._get_withdrawal_exchange("ColdStorage") == "ColdStorage"

    def test_withdrawal_exchange_with_none(self):
        """_get_withdrawal_exchange should use default placeholder when None."""
        class TestImporter(BaseImporter):
            name = "Coinbase"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        assert parser._get_withdrawal_exchange(None) == "Coinbase-Withdrawal"

    def test_withdrawal_comment_with_user_specified(self):
        """_get_withdrawal_comment should not add review note when user specified."""
        class TestImporter(BaseImporter):
            name = "TestParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        assert parser._get_withdrawal_comment("Ledger", "") == ""
        assert parser._get_withdrawal_comment("Ledger", "Existing note") == "Existing note"

    def test_withdrawal_comment_with_none(self):
        """_get_withdrawal_comment should add review note when None."""
        class TestImporter(BaseImporter):
            name = "TestParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        comment = parser._get_withdrawal_comment(None, "")
        assert "Review: Verify destination wallet" in comment

    def test_withdrawal_comment_preserves_existing(self):
        """_get_withdrawal_comment should preserve existing comment."""
        class TestImporter(BaseImporter):
            name = "TestParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = TestImporter()
        comment = parser._get_withdrawal_comment(None, "Original note")
        assert "Original note" in comment
        assert "Review: Verify destination wallet" in comment


class TestFiatCurrencies:
    """Tests for FIAT_CURRENCIES and is_fiat() helper (FIAT-000)."""

    def test_fiat_currencies_contains_traditional_fiat(self):
        """FIAT_CURRENCIES should contain traditional fiat currencies."""
        assert 'USD' in FIAT_CURRENCIES
        assert 'EUR' in FIAT_CURRENCIES
        assert 'GBP' in FIAT_CURRENCIES
        assert 'CAD' in FIAT_CURRENCIES
        assert 'AUD' in FIAT_CURRENCIES
        assert 'JPY' in FIAT_CURRENCIES
        assert 'CHF' in FIAT_CURRENCIES

    def test_fiat_currencies_contains_stablecoins(self):
        """FIAT_CURRENCIES should contain stablecoins."""
        assert 'USDC' in FIAT_CURRENCIES
        assert 'USDT' in FIAT_CURRENCIES
        assert 'GUSD' in FIAT_CURRENCIES
        assert 'BUSD' in FIAT_CURRENCIES
        assert 'DAI' in FIAT_CURRENCIES
        assert 'PYUSD' in FIAT_CURRENCIES

    def test_fiat_currencies_is_frozenset(self):
        """FIAT_CURRENCIES should be a frozenset (immutable)."""
        assert isinstance(FIAT_CURRENCIES, frozenset)

    def test_is_fiat_recognizes_traditional_fiat(self):
        """is_fiat() should recognize traditional fiat currencies."""
        assert is_fiat('USD') is True
        assert is_fiat('EUR') is True
        assert is_fiat('GBP') is True
        assert is_fiat('CAD') is True
        assert is_fiat('AUD') is True
        assert is_fiat('JPY') is True
        assert is_fiat('CHF') is True

    def test_is_fiat_recognizes_stablecoins(self):
        """is_fiat() should recognize stablecoins as fiat-equivalent."""
        assert is_fiat('USDC') is True
        assert is_fiat('USDT') is True
        assert is_fiat('GUSD') is True
        assert is_fiat('BUSD') is True
        assert is_fiat('DAI') is True
        assert is_fiat('PYUSD') is True

    def test_is_fiat_rejects_btc(self):
        """is_fiat() should reject BTC."""
        assert is_fiat('BTC') is False

    def test_is_fiat_rejects_altcoins(self):
        """is_fiat() should reject altcoins."""
        assert is_fiat('ETH') is False
        assert is_fiat('LTC') is False
        assert is_fiat('XRP') is False
        assert is_fiat('DOGE') is False

    def test_is_fiat_case_insensitive(self):
        """is_fiat() should be case-insensitive."""
        assert is_fiat('usd') is True
        assert is_fiat('Usd') is True
        assert is_fiat('usdc') is True
        assert is_fiat('USDC') is True
        assert is_fiat('btc') is False
        assert is_fiat('Btc') is False


class TestRegistry:
    """Tests for parser registry."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def teardown_method(self):
        """Clear registry after each test."""
        clear_registry()

    def test_register_decorator(self):
        """@register decorator should add parser to registry."""
        @register
        class TestImporter(BaseImporter):
            name = "TestParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        assert "testparser" in _REGISTRY
        assert _REGISTRY["testparser"] == TestImporter

    def test_register_duplicate_raises_error(self):
        """Registering same name twice should raise ValueError."""
        @register
        class TestImporter1(BaseImporter):
            name = "DuplicateName"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        with pytest.raises(ValueError, match="already registered"):
            @register
            class TestImporter2(BaseImporter):
                name = "DuplicateName"
                def parse(self, file_path, withdraw_to=None):
                    return [], []

    def test_get_parser_returns_instance(self):
        """get_parser should return an instance of the parser."""
        @register
        class TestImporter(BaseImporter):
            name = "MyParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = get_parser("MyParser")
        assert parser is not None
        assert isinstance(parser, TestImporter)

    def test_get_parser_case_insensitive(self):
        """get_parser should be case-insensitive."""
        @register
        class TestImporter(BaseImporter):
            name = "CaseSensitive"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        assert get_parser("casesensitive") is not None
        assert get_parser("CASESENSITIVE") is not None
        assert get_parser("CaseSensitive") is not None

    def test_get_parser_not_found(self):
        """get_parser should return None for unknown parser."""
        assert get_parser("nonexistent") is None

    def test_get_all_parsers(self):
        """get_all_parsers should return all registered parsers."""
        @register
        class Parser1(BaseImporter):
            name = "Alpha"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        @register
        class Parser2(BaseImporter):
            name = "Beta"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parsers = get_all_parsers()
        assert len(parsers) == 2
        names = [p.name for p in parsers]
        assert "Alpha" in names
        assert "Beta" in names

    def test_get_all_parsers_sorted(self):
        """get_all_parsers should return parsers sorted by name."""
        @register
        class ParserZ(BaseImporter):
            name = "Zebra"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        @register
        class ParserA(BaseImporter):
            name = "Apple"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parsers = get_all_parsers()
        assert parsers[0].name == "Apple"
        assert parsers[1].name == "Zebra"

    def test_get_parser_names(self):
        """get_parser_names should return lowercase names."""
        @register
        class TestParser(BaseImporter):
            name = "MyParser"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        names = get_parser_names()
        assert "myparser" in names

    def test_clear_registry(self):
        """clear_registry should remove all parsers."""
        @register
        class TestParser(BaseImporter):
            name = "ToBeCleared"
            def parse(self, file_path, withdraw_to=None):
                return [], []

        assert len(_REGISTRY) > 0
        clear_registry()
        assert len(_REGISTRY) == 0


class TestDetection:
    """Tests for auto-detection functionality."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def teardown_method(self):
        """Clear registry after each test."""
        clear_registry()

    def test_detect_matches_by_columns(self):
        """detect should match based on expected columns."""
        @register
        class TestImporter(BaseImporter):
            name = "ColumnMatcher"
            expected_columns = ["timestamp", "type", "amount"]
            def parse(self, file_path, withdraw_to=None):
                return [], []

        # Create a CSV with matching columns
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("timestamp,type,amount,extra\n")
            f.write("2024-01-01,buy,100\n")
            temp_path = f.name

        try:
            parser = detect_parser(temp_path)
            assert parser is not None
            assert parser.name == "ColumnMatcher"
        finally:
            os.unlink(temp_path)

    def test_detect_no_match(self):
        """detect should return None when no parser matches."""
        @register
        class TestImporter(BaseImporter):
            name = "SpecificParser"
            expected_columns = ["very_specific_column"]
            def parse(self, file_path, withdraw_to=None):
                return [], []

        # Create a CSV with non-matching columns
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("completely,different,columns\n")
            f.write("1,2,3\n")
            temp_path = f.name

        try:
            parser = detect_parser(temp_path)
            assert parser is None
        finally:
            os.unlink(temp_path)

    def test_detect_handles_missing_file(self):
        """detect should handle missing files gracefully."""
        @register
        class TestImporter(BaseImporter):
            name = "TestParser"
            expected_columns = ["col1"]
            def parse(self, file_path, withdraw_to=None):
                return [], []

        parser = detect_parser("/nonexistent/path/file.csv")
        assert parser is None

    def test_detect_case_insensitive_columns(self):
        """detect should match columns case-insensitively."""
        @register
        class TestImporter(BaseImporter):
            name = "CaseTest"
            expected_columns = ["Timestamp", "Type"]
            def parse(self, file_path, withdraw_to=None):
                return [], []

        # Create CSV with different casing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("TIMESTAMP,type\n")
            f.write("2024-01-01,buy\n")
            temp_path = f.name

        try:
            parser = detect_parser(temp_path)
            assert parser is not None
            assert parser.name == "CaseTest"
        finally:
            os.unlink(temp_path)

    def test_detect_empty_expected_columns_returns_false(self):
        """Parser with empty expected_columns should not match."""
        @register
        class TestImporter(BaseImporter):
            name = "NoColumns"
            expected_columns = []
            def parse(self, file_path, withdraw_to=None):
                return [], []

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("any,columns,here\n")
            temp_path = f.name

        try:
            parser = TestImporter()
            assert parser.detect(temp_path) is False
        finally:
            os.unlink(temp_path)



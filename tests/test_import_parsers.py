"""Tests for import parser infrastructure (IMP-001)."""

import pytest
import tempfile
import os

# Add src/python to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from imports.base import BaseImporter
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


# ============================================================================
# IMP-002: Transaction Validation Tests
# ============================================================================

from imports.validation import (
    ValidationResult,
    validate_transaction,
    validate_batch,
    get_transaction_warnings,
    VALID_TRANS_TYPES,
    BUY_TYPES,
    SELL_TYPES,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_values(self):
        """ValidationResult should have sensible defaults."""
        result = ValidationResult()
        assert result.valid_count == 0
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.errors == []
        assert result.warnings == []

    def test_is_valid_when_no_errors(self):
        """is_valid should return True when error_count is 0."""
        result = ValidationResult(valid_count=5, error_count=0)
        assert result.is_valid is True

    def test_is_valid_when_has_errors(self):
        """is_valid should return False when error_count > 0."""
        result = ValidationResult(valid_count=3, error_count=2)
        assert result.is_valid is False

    def test_total_count(self):
        """total_count should sum valid and error counts."""
        result = ValidationResult(valid_count=7, error_count=3)
        assert result.total_count == 10


class TestValidateTransaction:
    """Tests for validate_transaction function."""

    def test_valid_trade_transaction(self):
        """Valid trade transaction should pass validation."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15 10:30:00',
            'exchange': 'Coinbase',
            'buy': 0.5,
            'buy_curr': 'BTC',
            'sell': 25000.00,
            'sell_curr': 'USD',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_valid_deposit_transaction(self):
        """Valid deposit transaction should pass validation."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Ledger',
            'buy': 1.0,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_valid_withdrawal_transaction(self):
        """Valid withdrawal transaction should pass validation."""
        tx = {
            'trans_type': 'Withdrawal',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'sell': 0.5,
            'sell_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_valid_interest_income_transaction(self):
        """Valid interest income transaction should pass validation."""
        tx = {
            'trans_type': 'Interest Income',
            'created_date': '2024-01-15',
            'exchange': 'Gemini',
            'buy': 0.001,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_valid_mining_transaction(self):
        """Valid mining transaction should pass validation."""
        tx = {
            'trans_type': 'Mining',
            'created_date': '2024-01-15',
            'exchange': 'Mining Pool',
            'buy': 0.00001,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_staking_alias_accepted(self):
        """Staking should be accepted as alias for Interest Income."""
        tx = {
            'trans_type': 'Staking',
            'created_date': '2024-01-15',
            'exchange': 'Kraken',
            'buy': 0.001,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_interest_alias_accepted(self):
        """Interest should be accepted as alias for Interest Income."""
        tx = {
            'trans_type': 'Interest',
            'created_date': '2024-01-15',
            'exchange': 'BlockFi',
            'buy': 0.001,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_missing_trans_type(self):
        """Missing trans_type should produce error."""
        tx = {
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
        }
        errors = validate_transaction(tx)
        assert any('trans_type' in e for e in errors)

    def test_missing_created_date(self):
        """Missing created_date should produce error."""
        tx = {
            'trans_type': 'Trade',
            'exchange': 'Coinbase',
        }
        errors = validate_transaction(tx)
        assert any('created_date' in e for e in errors)

    def test_missing_exchange(self):
        """Missing exchange should produce error."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
        }
        errors = validate_transaction(tx)
        assert any('exchange' in e for e in errors)

    def test_invalid_trans_type(self):
        """Invalid trans_type should produce error."""
        tx = {
            'trans_type': 'InvalidType',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
        }
        errors = validate_transaction(tx)
        assert any('trans_type' in e.lower() for e in errors)

    def test_invalid_date_format(self):
        """Invalid date format should produce error."""
        tx = {
            'trans_type': 'Trade',
            'created_date': 'not-a-date',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('created_date' in e for e in errors)

    def test_deposit_missing_buy(self):
        """Deposit without buy amount should produce error."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('buy' in e.lower() for e in errors)

    def test_deposit_missing_buy_curr(self):
        """Deposit without buy_curr should produce error."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
        }
        errors = validate_transaction(tx)
        assert any('buy_curr' in e.lower() for e in errors)

    def test_withdrawal_missing_sell(self):
        """Withdrawal without sell amount should produce error."""
        tx = {
            'trans_type': 'Withdrawal',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'sell_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('sell' in e.lower() for e in errors)

    def test_withdrawal_missing_sell_curr(self):
        """Withdrawal without sell_curr should produce error."""
        tx = {
            'trans_type': 'Withdrawal',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'sell': 1.0,
        }
        errors = validate_transaction(tx)
        assert any('sell_curr' in e.lower() for e in errors)

    def test_trade_requires_buy_or_sell(self):
        """Trade without buy or sell should produce error."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
        }
        errors = validate_transaction(tx)
        assert any('buy' in e.lower() or 'sell' in e.lower() for e in errors)

    def test_trade_with_only_buy_is_valid(self):
        """Trade with only buy side is valid (receiving)."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 0.5,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_trade_with_only_sell_is_valid(self):
        """Trade with only sell side is valid (selling)."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'sell': 0.5,
            'sell_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert errors == []

    def test_negative_buy_amount(self):
        """Negative buy amount should produce error."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': -1.0,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('buy' in e.lower() and 'positive' in e.lower() for e in errors)

    def test_zero_buy_amount(self):
        """Zero buy amount should produce error."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 0,
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('buy' in e.lower() and 'positive' in e.lower() for e in errors)

    def test_negative_sell_amount(self):
        """Negative sell amount should produce error."""
        tx = {
            'trans_type': 'Withdrawal',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'sell': -1.0,
            'sell_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('sell' in e.lower() and 'positive' in e.lower() for e in errors)

    def test_negative_fee(self):
        """Negative fee should produce error."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
            'fee': -0.01,
        }
        errors = validate_transaction(tx)
        assert any('fee' in e.lower() for e in errors)

    def test_zero_fee_is_valid(self):
        """Zero fee should be valid (no fee charged)."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
            'fee': 0,
        }
        errors = validate_transaction(tx)
        assert not any('fee' in e.lower() for e in errors)

    def test_non_numeric_buy_amount(self):
        """Non-numeric buy amount should produce error."""
        tx = {
            'trans_type': 'Deposit',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 'not-a-number',
            'buy_curr': 'BTC',
        }
        errors = validate_transaction(tx)
        assert any('buy' in e.lower() for e in errors)

    def test_various_valid_date_formats(self):
        """Various common date formats should be accepted."""
        valid_dates = [
            '2024-01-15 10:30:00',
            '2024-01-15T10:30:00',
            '2024-01-15T10:30:00Z',
            '2024-01-15',
            '01/15/2024',
            '2024-01-15T10:30:00.123456',
        ]
        for date_str in valid_dates:
            tx = {
                'trans_type': 'Trade',
                'created_date': date_str,
                'exchange': 'Coinbase',
                'buy': 1.0,
                'buy_curr': 'BTC',
            }
            errors = validate_transaction(tx)
            assert not any('created_date' in e for e in errors), f"Date format failed: {date_str}"


class TestGetTransactionWarnings:
    """Tests for get_transaction_warnings function."""

    def test_no_warnings_for_complete_transaction(self):
        """Complete transaction should produce no warnings."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
            'fee': 0.01,
            'fee_curr': 'USD',
        }
        warnings = get_transaction_warnings(tx)
        assert warnings == []

    def test_warning_for_fee_without_currency(self):
        """Fee without fee_curr should produce warning."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2024-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
            'fee': 0.01,
        }
        warnings = get_transaction_warnings(tx)
        assert any('fee_curr' in w.lower() for w in warnings)

    def test_warning_for_future_date(self):
        """Future date should produce warning."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2099-12-31',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
        }
        warnings = get_transaction_warnings(tx)
        assert any('future' in w.lower() for w in warnings)

    def test_no_warning_for_past_date(self):
        """Past date should not produce future date warning."""
        tx = {
            'trans_type': 'Trade',
            'created_date': '2020-01-15',
            'exchange': 'Coinbase',
            'buy': 1.0,
            'buy_curr': 'BTC',
        }
        warnings = get_transaction_warnings(tx)
        assert not any('future' in w.lower() for w in warnings)


class TestValidateBatch:
    """Tests for validate_batch function."""

    def test_all_valid_transactions(self):
        """Batch with all valid transactions should pass."""
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-15',
                'exchange': 'Coinbase',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                'trans_type': 'Withdrawal',
                'created_date': '2024-01-16',
                'exchange': 'Coinbase',
                'sell': 0.5,
                'sell_curr': 'BTC',
            },
        ]
        result = validate_batch(transactions)
        assert result.is_valid
        assert result.valid_count == 2
        assert result.error_count == 0

    def test_mixed_valid_and_invalid(self):
        """Batch with mixed transactions should report correctly."""
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-15',
                'exchange': 'Coinbase',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                'trans_type': 'Invalid',  # Invalid type
                'created_date': '2024-01-16',
                'exchange': 'Coinbase',
            },
            {
                'trans_type': 'Trade',
                'created_date': '2024-01-17',
                'exchange': 'Coinbase',
                'buy': 0.5,
                'buy_curr': 'BTC',
            },
        ]
        result = validate_batch(transactions)
        assert not result.is_valid
        assert result.valid_count == 2
        assert result.error_count == 1
        assert result.total_count == 3

    def test_errors_include_index(self):
        """Errors should include transaction index."""
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-15',
                'exchange': 'Coinbase',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                # Missing required fields - index 1
            },
        ]
        result = validate_batch(transactions)
        assert len(result.errors) == 1
        index, errors = result.errors[0]
        assert index == 1

    def test_warnings_tracked_separately(self):
        """Warnings should be tracked separately from errors."""
        transactions = [
            {
                'trans_type': 'Trade',
                'created_date': '2024-01-15',
                'exchange': 'Coinbase',
                'buy': 1.0,
                'buy_curr': 'BTC',
                'fee': 0.01,  # No fee_curr - warning
            },
        ]
        result = validate_batch(transactions)
        assert result.is_valid  # Warnings don't invalidate
        assert result.valid_count == 1
        assert result.warning_count == 1

    def test_empty_batch(self):
        """Empty batch should return empty result."""
        result = validate_batch([])
        assert result.is_valid
        assert result.valid_count == 0
        assert result.error_count == 0


class TestTransactionTypeConstants:
    """Tests for transaction type constants."""

    def test_valid_trans_types_includes_all(self):
        """VALID_TRANS_TYPES should include all expected types."""
        expected = {'Trade', 'Deposit', 'Withdrawal', 'Interest Income', 'Mining', 'Staking', 'Interest'}
        assert expected == VALID_TRANS_TYPES

    def test_buy_types(self):
        """BUY_TYPES should include types that produce buy."""
        assert 'Trade' in BUY_TYPES
        assert 'Deposit' in BUY_TYPES
        assert 'Interest Income' in BUY_TYPES
        assert 'Mining' in BUY_TYPES
        assert 'Staking' in BUY_TYPES
        assert 'Interest' in BUY_TYPES

    def test_sell_types(self):
        """SELL_TYPES should include types that produce sell."""
        assert 'Trade' in SELL_TYPES
        assert 'Withdrawal' in SELL_TYPES

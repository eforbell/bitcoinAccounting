"""Tests for import parser infrastructure (IMP-001, IMP-002, IMP-003)."""

import pytest
import tempfile
import os
import subprocess
import csv as csv_mod
from pathlib import Path

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


# ============================================================================
# IMP-003: CLI Entry Point Tests
# ============================================================================

from db import SqliteBackend
from cryptoAccounts import CryptoAccounts
from imports.validation import detect_duplicates

SCRIPT_PATH = Path(__file__).parent.parent / "src" / "scripts" / "import_csv"


class _TestExchangeImporter(BaseImporter):
    """Test exchange parser for IMP-003 integration tests.

    Reads a simple CSV with columns: date, type, amount, currency, usd_amount, fee, comment, txid
    Transaction types: buy, deposit, send, interest, mining
    """
    name = "TestExchange"
    source_type = "exchange"
    description = "Simple test parser for integration tests"
    expected_columns = ["date", "type", "amount", "currency"]

    def parse(self, file_path, withdraw_to=None):
        transactions = []
        with open(file_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                tx_type = row['type']
                if tx_type == 'buy':
                    transactions.append({
                        'trans_type': 'Trade',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'sell': float(row.get('usd_amount') or 0),
                        'sell_curr': 'USD',
                        'fee': float(row.get('fee') or 0),
                        'fee_curr': 'USD',
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'deposit':
                    transactions.append({
                        'trans_type': 'Deposit',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'send':
                    transactions.append({
                        'trans_type': 'Withdrawal',
                        'created_date': row['date'],
                        'exchange': self._get_withdrawal_exchange(withdraw_to),
                        'sell': float(row['amount']),
                        'sell_curr': row['currency'],
                        'fee': float(row.get('fee') or 0),
                        'fee_curr': row['currency'],
                        'comment': self._get_withdrawal_comment(withdraw_to, row.get('comment', '')),
                        'group': '',
                    })
                elif tx_type == 'interest':
                    transactions.append({
                        'trans_type': 'Interest Income',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                    })
                elif tx_type == 'mining':
                    transactions.append({
                        'trans_type': 'Mining',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
                        'comment': row.get('comment', ''),
                        'transactionid': row.get('txid', ''),
                    })
        colnames = ['trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
                    'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment', 'transactionid']
        return colnames, transactions


def _make_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestImportCSVCli:
    """CLI behavior tests for import_csv script via subprocess."""

    def test_help_flag(self):
        """--help exits 0 and shows all flags."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0
        assert "--list" in result.stdout
        assert "--source" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--withdraw-to" in result.stdout
        assert "--format" in result.stdout

    def test_list_flag_exits_0(self):
        """--list exits 0 even with no parsers registered."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--list"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0

    def test_no_args_exits_1(self):
        """No arguments prints FILE required error and exits 1."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH)],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "FILE is required" in result.stderr

    def test_file_not_found_exits_1(self):
        """Nonexistent file path exits 1 with not found message."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "/no/such/file.csv"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_unknown_source_exits_1(self):
        """--source with unregistered parser name exits 1."""
        csv_path = _make_csv("a,b\n1,2\n")
        try:
            result = subprocess.run(
                [".venv/bin/python", str(SCRIPT_PATH), "--source", "bogus", csv_path],
                capture_output=True, text=True,
                cwd=Path(__file__).parent.parent
            )
            assert result.returncode == 1
            assert "Unknown parser" in result.stderr
        finally:
            os.unlink(csv_path)

    def test_format_unknown_parser_exits_1(self):
        """--format with unregistered parser name exits 1."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--format", "bogus"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 1
        assert "Unknown parser" in result.stderr


class TestImportWorkflow:
    """Integration tests for the full import pipeline (IMP-003).

    Uses _TestExchangeImporter with in-memory SQLite to exercise the same
    code paths the import_csv script orchestrates.
    """

    def setup_method(self):
        clear_registry()
        register(_TestExchangeImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_import_deposit(self):
        """Parse deposit CSV, validate, import, verify in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Deposit'
            assert transactions[0]['buy'] == 0.5

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['buy'] == 0.5
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['exchange'] == 'TestExchange'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_trade(self):
        """Parse trade CSV, import, verify Trade row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Trade'

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Trade'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.1)
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['sell'] == pytest.approx(5000.0)
            assert rows[0]['sell_curr'] == 'USD'
            assert rows[0]['fee'] == pytest.approx(25.0)
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_withdrawal_with_withdraw_to(self):
        """Withdrawal with withdraw_to sets exchange to wallet name, no review comment."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Withdrawal'
            assert transactions[0]['exchange'] == 'Ledger'
            assert transactions[0]['comment'] == ''

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert rows[0]['exchange'] == 'Ledger'
            assert rows[0]['sell'] == pytest.approx(0.2)
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_withdrawal_without_withdraw_to(self):
        """Withdrawal without withdraw_to uses placeholder exchange and adds review comment."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to=None)

            assert transactions[0]['exchange'] == 'TestExchange-Withdrawal'
            assert 'Review: Verify destination wallet' in transactions[0]['comment']
        finally:
            os.unlink(csv_path)

    def test_import_interest_income(self):
        """Parse interest CSV, import, verify Interest Income row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,interest,0.001,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert transactions[0]['trans_type'] == 'Interest Income'

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Interest Income'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.001)
            assert rows[0]['buy_curr'] == 'BTC'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_duplicate_detection(self):
        """Second parse of same deposit detected as duplicate."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            # Re-parse same CSV — should now be detected as duplicate
            _, transactions2 = parser.parse(csv_path)
            duplicates = detect_duplicates(transactions2, backend)
            assert len(duplicates) == 1
            assert duplicates[0]['trans_type'] == 'Deposit'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_validation_catches_missing_fields(self):
        """validate_batch rejects transactions missing required fields."""
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-03-15',
                'exchange': 'TestExchange',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                # Missing trans_type, created_date, exchange
            },
        ]
        result = validate_batch(transactions)
        assert not result.is_valid
        assert result.valid_count == 1
        assert result.error_count == 1

    def test_empty_csv_produces_no_transactions(self):
        """CSV with only a header row produces zero transactions."""
        csv_path = _make_csv("date,type,amount,currency\n")
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_multiple_transaction_types_in_one_file(self):
        """Mixed transaction types all import correctly."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25\n"
            "2024-03-16 11:00:00,deposit,0.05,BTC,,\n"
            "2024-03-17 12:00:00,interest,0.001,BTC,,\n"
            "2024-03-18 13:00:00,send,0.02,BTC,,0.0001\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path, withdraw_to="ColdStorage")

            assert len(transactions) == 4
            types = {tx['trans_type'] for tx in transactions}
            assert types == {'Trade', 'Deposit', 'Interest Income', 'Withdrawal'}

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger")
            assert len(rows) == 4
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_mining(self):
        """Parse mining CSV, import, verify Mining row in DB."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment,txid\n"
            "2024-03-15 10:00:00,mining,0.00001,BTC,,,,abc123def\n"
        )
        try:
            parser = get_parser("TestExchange")
            colnames, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['trans_type'] == 'Mining'
            assert transactions[0]['transactionid'] == 'abc123def'

            result = validate_batch(transactions)
            assert result.is_valid

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['buy'] == pytest.approx(0.00001)
            assert rows[0]['buy_curr'] == 'BTC'
            assert rows[0]['transactionid'] == 'abc123def'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_mining_without_txid(self):
        """Mining without transactionid still imports (empty string)."""
        csv_path = _make_csv(
            "date,type,amount,currency\n"
            "2024-03-15 10:00:00,mining,0.00002,BTC\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT * FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['transactionid'] == ''
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_import_returns_counts(self):
        """import_transactions returns dict with imported and skipped counts."""
        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)

        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-03-15',
                'exchange': 'Test',
                'buy': 1.0,
                'buy_curr': 'BTC',
            },
            {
                'trans_type': 'UnknownType',  # Will be skipped
                'created_date': '2024-03-16',
                'exchange': 'Test',
            },
        ]
        result = crypto.import_transactions(transactions)

        assert result['imported'] == 1
        assert result['skipped'] == 1
        crypto.close()


class TestCommentPreservation:
    """Tests verifying comments are stored in DB for all transaction types."""

    def setup_method(self):
        clear_registry()
        register(_TestExchangeImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_trade_comment_stored(self):
        """Trade transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,buy,0.1,BTC,5000,25,DCA purchase\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Trade'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'DCA purchase'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_deposit_comment_stored(self):
        """Deposit transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,deposit,0.5,BTC,,,Transfer from cold storage\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Deposit'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Transfer from cold storage'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_withdrawal_comment_stored(self):
        """Withdrawal transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001,To Ledger Nano\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'To Ledger Nano'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_withdrawal_review_comment_stored(self):
        """Withdrawal without withdraw_to stores review comment in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,send,0.2,BTC,,0.0001,\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert 'Review: Verify destination wallet' in rows[0]['comment']
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_interest_income_comment_stored(self):
        """Interest Income transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment\n"
            "2024-03-15 10:00:00,interest,0.001,BTC,,,Gemini Earn reward\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Interest Income'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Gemini Earn reward'
            crypto.close()
        finally:
            os.unlink(csv_path)

    def test_mining_comment_stored(self):
        """Mining transaction comment is stored in database."""
        csv_path = _make_csv(
            "date,type,amount,currency,usd_amount,fee,comment,txid\n"
            "2024-03-15 10:00:00,mining,0.00001,BTC,,,Pool payout,block123\n"
        )
        try:
            parser = get_parser("TestExchange")
            _, transactions = parser.parse(csv_path)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Mining'")
            assert len(rows) == 1
            assert rows[0]['comment'] == 'Pool payout'
            crypto.close()
        finally:
            os.unlink(csv_path)


# ============================================================================
# IMP-004: Native Format Parser Tests
# ============================================================================

from imports.exchanges.native import NativeImporter, _detect_format, _CLEAN_MAP, _LEGACY_MAP

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv_samples"


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


# ============================================================================
# IMP-005: Coinbase Parser Tests
# ============================================================================

from imports.exchanges.coinbase import CoinbaseImporter


class TestCoinbaseImporterDetection:
    """Tests for CoinbaseImporter auto-detection."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_detects_coinbase_format(self):
        """detect() returns True for a file with Coinbase columns."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,Test\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_unrelated_csv(self):
        """detect() returns False for a CSV with unrelated columns."""
        csv_path = _make_csv("name,age,city\nAlice,30,NYC\n")
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_does_not_detect_native_format(self):
        """detect() returns False for native format CSV."""
        csv_path = _make_csv(
            "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
            "Trade,0.05,BTC,2500.00,USD,10.00,USD,Coinbase,,Purchase,2024-01-15\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is False
        finally:
            os.unlink(csv_path)

    def test_detect_case_insensitive(self):
        """detect() matches columns case-insensitively."""
        csv_path = _make_csv(
            "TIMESTAMP,TRANSACTION TYPE,ASSET,QUANTITY TRANSACTED,SPOT PRICE CURRENCY,"
            "SPOT PRICE AT TRANSACTION,SUBTOTAL,TOTAL,FEES,NOTES\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,Test\n"
        )
        try:
            parser = CoinbaseImporter()
            assert parser.detect(csv_path) is True
        finally:
            os.unlink(csv_path)


class TestCoinbaseImporterParsing:
    """Tests for CoinbaseImporter parsing logic."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_parse_sample_fixture(self):
        """Parse the shipped coinbase_sample.csv fixture end-to-end."""
        parser = CoinbaseImporter()
        colnames, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_sample.csv"))

        # Should have 7 BTC transactions (the ETH one is filtered out)
        assert len(transactions) == 7

        # Verify Buy transaction
        buy_tx = transactions[0]
        assert buy_tx['trans_type'] == 'Trade'
        assert buy_tx['buy'] == pytest.approx(0.05)
        assert buy_tx['buy_curr'] == 'BTC'
        assert buy_tx['sell'] == pytest.approx(2510.0)  # Total includes fees
        assert buy_tx['sell_curr'] == 'USD'
        assert buy_tx['fee'] == pytest.approx(10.0)
        assert buy_tx['exchange'] == 'Coinbase'
        assert buy_tx['comment'] == 'DCA purchase'

    def test_parse_buy_transaction(self):
        """Buy transaction maps to Trade with BTC buy side."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,BTC,0.1,USD,50000.00,5000.00,5025.00,25.00,My purchase\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.1)
            assert tx['buy_curr'] == 'BTC'
            assert tx['sell'] == pytest.approx(5025.0)
            assert tx['sell_curr'] == 'USD'
            assert tx['fee'] == pytest.approx(25.0)
            assert tx['fee_curr'] == 'USD'
            assert tx['comment'] == 'My purchase'
        finally:
            os.unlink(csv_path)

    def test_parse_sell_transaction(self):
        """Sell transaction maps to Trade with BTC sell side."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-01T14:00:00Z,Sell,BTC,0.02,USD,52000.00,1040.00,1030.00,10.00,Profit taking\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(1040.0)  # Subtotal (before fees)
            assert tx['buy_curr'] == 'USD'
            assert tx['sell'] == pytest.approx(0.02)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(10.0)
        finally:
            os.unlink(csv_path)

    def test_parse_send_with_withdraw_to(self):
        """Send transaction with withdraw_to uses specified exchange."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,To ledger\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path, withdraw_to="Ledger")

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Withdrawal'
            assert tx['exchange'] == 'Ledger'
            assert tx['sell'] == pytest.approx(0.01)
            assert tx['sell_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.0001)
            assert tx['comment'] == 'To ledger'  # No review note when withdraw_to specified
        finally:
            os.unlink(csv_path)

    def test_parse_send_without_withdraw_to(self):
        """Send transaction without withdraw_to uses default exchange and adds review comment."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['exchange'] == 'Coinbase-Withdrawal'
            assert 'Review: Verify destination wallet' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_parse_receive_transaction(self):
        """Receive transaction maps to Deposit."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-03-01T00:00:00Z,Receive,BTC,0.005,USD,48000.00,240.00,240.00,0.00,From friend\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Deposit'
            assert tx['buy'] == pytest.approx(0.005)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Coinbase'
            assert tx['comment'] == 'From friend'
        finally:
            os.unlink(csv_path)

    def test_parse_rewards_income(self):
        """Rewards Income maps to Interest Income."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-03-15T12:00:00Z,Rewards Income,BTC,0.0001,USD,55000.00,5.50,5.50,0.00,Staking\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.0001)
            assert tx['buy_curr'] == 'BTC'
            assert tx['exchange'] == 'Coinbase'
            assert 'usd_equivalent' in tx
            assert tx['usd_equivalent'] == pytest.approx(5.50)
        finally:
            os.unlink(csv_path)

    def test_parse_learning_reward(self):
        """Learning Reward maps to Interest Income."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-04-01T08:00:00Z,Learning Reward,BTC,0.00005,USD,60000.00,3.00,3.00,0.00,\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Interest Income'
            assert tx['buy'] == pytest.approx(0.00005)
            # When no notes, should include original type
            assert 'Learning Reward' in tx['comment']
        finally:
            os.unlink(csv_path)

    def test_parse_convert_transaction(self):
        """Convert transaction maps to Trade."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-04-15T16:00:00Z,Convert,BTC,0.001,USD,62000.00,62.00,62.00,0.50,From ETH\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            tx = transactions[0]
            assert tx['trans_type'] == 'Trade'
            assert tx['buy'] == pytest.approx(0.001)
            assert tx['buy_curr'] == 'BTC'
            assert tx['fee'] == pytest.approx(0.50)
        finally:
            os.unlink(csv_path)

    def test_filters_non_btc_transactions(self):
        """Non-BTC transactions are filtered out."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-01-15T10:30:00Z,Buy,ETH,1.0,USD,3000.00,3000.00,3015.00,15.00,ETH purchase\n"
            "2024-01-16T10:30:00Z,Buy,BTC,0.05,USD,50000.00,2500.00,2510.00,10.00,BTC purchase\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)

            assert len(transactions) == 1
            assert transactions[0]['buy_curr'] == 'BTC'
        finally:
            os.unlink(csv_path)

    def test_handles_empty_file(self):
        """Empty file returns empty transaction list."""
        csv_path = _make_csv("")
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)

    def test_handles_header_only_file(self):
        """File with only headers returns empty transaction list."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path)
            assert transactions == []
        finally:
            os.unlink(csv_path)


class TestCoinbaseImporterRegistration:
    """Tests for CoinbaseImporter registration and metadata."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def test_registered_name(self):
        """CoinbaseImporter is retrievable by name 'coinbase'."""
        parser = get_parser("coinbase")
        assert parser is not None
        assert isinstance(parser, CoinbaseImporter)

    def test_source_type_is_exchange(self):
        """source_type is 'exchange'."""
        parser = CoinbaseImporter()
        assert parser.source_type == "exchange"

    def test_format_help_includes_columns(self):
        """get_format_help() lists expected Coinbase columns."""
        parser = CoinbaseImporter()
        help_text = parser.get_format_help()
        assert "Coinbase" in help_text
        assert "Timestamp" in help_text
        assert "Transaction Type" in help_text
        assert "Quantity Transacted" in help_text


class TestCoinbaseImporterIntegration:
    """Integration tests for Coinbase parser with database import."""

    def setup_method(self):
        clear_registry()
        register(CoinbaseImporter)

    def teardown_method(self):
        clear_registry()

    def _make_backend(self):
        return SqliteBackend(':memory:', auto_create_tables=True)

    def test_full_import_workflow(self):
        """Parse Coinbase CSV and import all transactions to database."""
        parser = CoinbaseImporter()
        _, transactions = parser.parse(str(FIXTURES_DIR / "coinbase_sample.csv"), withdraw_to="Ledger")

        result = validate_batch(transactions)
        assert result.is_valid

        backend = self._make_backend()
        crypto = CryptoAccounts(backend=backend)
        import_result = crypto.import_transactions(transactions)

        assert import_result['imported'] == 7
        assert import_result['skipped'] == 0

        # Verify all types imported
        rows = backend.execute("SELECT trans_type, COUNT(*) as cnt FROM ledger GROUP BY trans_type")
        type_counts = {row['trans_type']: row['cnt'] for row in rows}

        assert type_counts.get('Trade', 0) == 3  # 1 Buy + 1 Sell + 1 Convert (ETH Buy filtered)
        assert type_counts.get('Withdrawal', 0) == 1
        assert type_counts.get('Deposit', 0) == 1
        assert type_counts.get('Interest Income', 0) == 2  # Rewards + Learning

        crypto.close()

    def test_withdrawal_comment_preserved(self):
        """Withdrawal review comment is stored in database."""
        csv_path = _make_csv(
            "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,"
            "Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
            "2024-02-15T09:00:00Z,Send,BTC,0.01,USD,51000.00,510.00,510.00,0.0001,\n"
        )
        try:
            parser = CoinbaseImporter()
            _, transactions = parser.parse(csv_path, withdraw_to=None)

            backend = self._make_backend()
            crypto = CryptoAccounts(backend=backend)
            crypto.import_transactions(transactions)

            rows = backend.execute("SELECT comment FROM ledger WHERE trans_type = 'Withdrawal'")
            assert len(rows) == 1
            assert 'Review: Verify destination wallet' in rows[0]['comment']
            crypto.close()
        finally:
            os.unlink(csv_path)


# ============================================================================
# IMP-006: Kraken Parser Tests
# ============================================================================

from imports.exchanges.kraken import KrakenImporter, _normalize_asset, _is_btc_related


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


# ---------------------------------------------------------------------------
# IMP-007 – Strike parser
# ---------------------------------------------------------------------------
from imports.exchanges.strike import StrikeImporter, _parse_number


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

        crypto.close()

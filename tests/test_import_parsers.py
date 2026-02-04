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

    Reads a simple CSV with columns: date, type, amount, currency, usd_amount, fee
    Transaction types: buy, deposit, send, interest
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
                    })
                elif tx_type == 'deposit':
                    transactions.append({
                        'trans_type': 'Deposit',
                        'created_date': row['date'],
                        'exchange': 'TestExchange',
                        'buy': float(row['amount']),
                        'buy_curr': row['currency'],
                        'group': '',
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
                        'comment': self._get_withdrawal_comment(withdraw_to),
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
                        'comment': '',
                    })
        colnames = ['trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
                    'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment']
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
            crypto.import_transactions(colnames, transactions)

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
            crypto.import_transactions(colnames, transactions)

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
            crypto.import_transactions(colnames, transactions)

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
            crypto.import_transactions(colnames, transactions)

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
            crypto.import_transactions(colnames, transactions)

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
            crypto.import_transactions(colnames, transactions)

            rows = backend.execute("SELECT * FROM ledger")
            assert len(rows) == 4
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

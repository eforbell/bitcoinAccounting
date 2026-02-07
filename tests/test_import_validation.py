"""Tests for transaction validation utilities (IMP-002)."""

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
        expected = {'Trade', 'Deposit', 'Withdrawal', 'Spend', 'Interest Income', 'Mining', 'Staking', 'Interest'}
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


"""Transaction validation utilities for import parsers.

This module provides validation functions to check parsed transactions
before importing them into the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from db import DatabaseBackend


# Valid transaction types
VALID_TRANS_TYPES = frozenset({
    'Trade',
    'Deposit',
    'Withdrawal',
    'Interest Income',
    'Mining',
    'Staking',  # Alias for Interest Income
    'Interest',  # Alias for Interest Income
})

# Transaction types that require buy fields
BUY_TYPES = frozenset({'Trade', 'Deposit', 'Interest Income', 'Mining', 'Staking', 'Interest'})

# Transaction types that require sell fields
SELL_TYPES = frozenset({'Trade', 'Withdrawal'})


@dataclass
class ValidationResult:
    """Result of batch transaction validation.

    Attributes:
        valid_count: Number of transactions that passed validation
        error_count: Number of transactions with errors
        warning_count: Number of transactions with warnings (but still valid)
        errors: List of (index, error_messages) tuples for invalid transactions
        warnings: List of (index, warning_messages) tuples
    """
    valid_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    errors: list[tuple[int, list[str]]] = field(default_factory=list)
    warnings: list[tuple[int, list[str]]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return True if all transactions are valid (no errors)."""
        return self.error_count == 0

    @property
    def total_count(self) -> int:
        """Return total number of transactions validated."""
        return self.valid_count + self.error_count


def validate_transaction(tx: dict[str, Any]) -> list[str]:
    """Validate a single transaction dict.

    Checks for required fields, valid values, and consistency.

    Args:
        tx: Transaction dictionary to validate

    Returns:
        List of error messages. Empty list means transaction is valid.
    """
    errors: list[str] = []

    # Check required fields
    if 'trans_type' not in tx or not tx['trans_type']:
        errors.append("Missing required field: trans_type")
    if 'created_date' not in tx or not tx['created_date']:
        errors.append("Missing required field: created_date")
    if 'exchange' not in tx or not tx['exchange']:
        errors.append("Missing required field: exchange")

    # If missing required fields, can't do further validation
    if errors:
        return errors

    # Validate trans_type
    trans_type = tx['trans_type']
    if trans_type not in VALID_TRANS_TYPES:
        errors.append(f"Invalid trans_type: '{trans_type}'. Must be one of: {', '.join(sorted(VALID_TRANS_TYPES))}")
        return errors  # Can't validate buy/sell fields without valid type

    # Validate created_date is parseable
    created_date = tx['created_date']
    if not _is_valid_date(created_date):
        errors.append(f"Invalid created_date format: '{created_date}'. Unable to parse as date.")

    # Validate buy fields for types that require them
    if trans_type in BUY_TYPES:
        if trans_type != 'Withdrawal':  # Withdrawal doesn't need buy
            buy = tx.get('buy')
            buy_curr = tx.get('buy_curr')

            if buy is None and trans_type != 'Trade':
                errors.append(f"Missing buy amount for {trans_type} transaction")
            elif buy is not None:
                if not _is_positive_number(buy):
                    errors.append(f"Invalid buy amount: '{buy}'. Must be a positive number.")

            if not buy_curr and trans_type != 'Trade':
                errors.append(f"Missing buy_curr for {trans_type} transaction")

    # Validate sell fields for types that require them
    if trans_type in SELL_TYPES:
        sell = tx.get('sell')
        sell_curr = tx.get('sell_curr')

        if sell is None and trans_type == 'Withdrawal':
            errors.append("Missing sell amount for Withdrawal transaction")
        elif sell is not None:
            if not _is_positive_number(sell):
                errors.append(f"Invalid sell amount: '{sell}'. Must be a positive number.")

        if not sell_curr and trans_type == 'Withdrawal':
            errors.append("Missing sell_curr for Withdrawal transaction")

    # Validate Trade has both buy and sell
    if trans_type == 'Trade':
        has_buy = tx.get('buy') is not None and tx.get('buy_curr')
        has_sell = tx.get('sell') is not None and tx.get('sell_curr')
        if not has_buy and not has_sell:
            errors.append("Trade transaction must have buy and/or sell fields")

    # Validate fee if present
    fee = tx.get('fee')
    if fee is not None and not _is_non_negative_number(fee):
        errors.append(f"Invalid fee: '{fee}'. Must be a non-negative number.")

    return errors


def get_transaction_warnings(tx: dict[str, Any]) -> list[str]:
    """Get warnings for a transaction (issues that don't prevent import).

    Args:
        tx: Transaction dictionary to check

    Returns:
        List of warning messages.
    """
    warnings: list[str] = []

    # Warn about missing fee currency when fee is present
    if tx.get('fee') and not tx.get('fee_curr'):
        warnings.append("Fee amount present but fee_curr not specified")

    # Warn about $0 cost basis
    trans_type = tx.get('trans_type', '')
    if trans_type in ('Deposit', 'Interest Income') and tx.get('buy'):
        # These might need cost basis info
        pass  # This is expected, not a warning

    # Warn about future dates
    created_date = tx.get('created_date')
    if created_date and _is_future_date(created_date):
        warnings.append(f"Transaction date is in the future: {created_date}")

    return warnings


def validate_batch(transactions: list[dict[str, Any]]) -> ValidationResult:
    """Validate a batch of transactions.

    Args:
        transactions: List of transaction dicts to validate

    Returns:
        ValidationResult with counts and error/warning details
    """
    result = ValidationResult()

    for i, tx in enumerate(transactions):
        errors = validate_transaction(tx)
        warnings = get_transaction_warnings(tx)

        if errors:
            result.error_count += 1
            result.errors.append((i, errors))
        else:
            result.valid_count += 1

        if warnings:
            result.warning_count += 1
            result.warnings.append((i, warnings))

    return result


def detect_duplicates(
    transactions: list[dict[str, Any]],
    backend: DatabaseBackend
) -> list[dict[str, Any]]:
    """Detect transactions that may already exist in the database.

    Checks for existing transactions with matching:
    - created_date (same day)
    - exchange
    - trans_type
    - amount (buy or sell)

    Args:
        transactions: List of transactions to check
        backend: Database backend for querying existing transactions

    Returns:
        List of transactions that appear to be duplicates
    """
    duplicates: list[dict[str, Any]] = []

    for tx in transactions:
        if _is_potential_duplicate(tx, backend):
            duplicates.append(tx)

    return duplicates


def _is_potential_duplicate(tx: dict[str, Any], backend: DatabaseBackend) -> bool:
    """Check if a transaction appears to already exist.

    Uses a query to find transactions with similar characteristics.
    """
    trans_type = tx.get('trans_type', '')
    exchange = tx.get('exchange', '')
    created_date = tx.get('created_date', '')

    if not all([trans_type, exchange, created_date]):
        return False

    # Normalize trans_type aliases
    if trans_type in ('Staking', 'Interest'):
        trans_type = 'Interest Income'

    # Get the amount to match (buy for deposits, sell for withdrawals)
    if trans_type in ('Deposit', 'Interest Income', 'Mining'):
        amount = tx.get('buy')
        amount_col = 'buy'
        curr = tx.get('buy_curr', 'BTC')
        curr_col = 'buy_curr'
    elif trans_type == 'Withdrawal':
        amount = tx.get('sell')
        amount_col = 'sell'
        curr = tx.get('sell_curr', 'BTC')
        curr_col = 'sell_curr'
    elif trans_type == 'Trade':
        # For trades, check buy side
        amount = tx.get('buy')
        amount_col = 'buy'
        curr = tx.get('buy_curr', 'BTC')
        curr_col = 'buy_curr'
    else:
        return False

    if amount is None:
        return False

    # Parse date to get just the date part for comparison
    try:
        if isinstance(created_date, str):
            # Try to parse and get date string
            date_str = created_date[:10]  # Get YYYY-MM-DD part
        else:
            date_str = str(created_date)[:10]
    except (ValueError, TypeError):
        return False

    # Query for potential duplicates
    query = f"""
        SELECT COUNT(*) as cnt FROM ledger
        WHERE trans_type = :trans_type
        AND exchange = :exchange
        AND {amount_col} = :amount
        AND {curr_col} = :curr
        AND DATE(createddate) = DATE(:date_str)
    """

    try:
        result = backend.execute_scalar(query, {
            'trans_type': trans_type,
            'exchange': exchange,
            'amount': float(amount),
            'curr': curr,
            'date_str': date_str,
        })
        return result is not None and result > 0
    except Exception:
        # If query fails, assume not duplicate
        return False


def _is_valid_date(value: Any) -> bool:
    """Check if a value can be parsed as a date."""
    if value is None:
        return False

    if isinstance(value, datetime):
        return True

    if not isinstance(value, str):
        return False

    # Try common date formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y',
        '%d/%m/%Y',
    ]

    for fmt in formats:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue

    # Try ISO format parsing (handles timezone offsets)
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return True
    except (ValueError, AttributeError):
        pass

    return False


def _is_positive_number(value: Any) -> bool:
    """Check if a value is a positive number."""
    try:
        num = float(value)
        return num > 0
    except (TypeError, ValueError):
        return False


def _is_non_negative_number(value: Any) -> bool:
    """Check if a value is a non-negative number."""
    try:
        num = float(value)
        return num >= 0
    except (TypeError, ValueError):
        return False


def _is_future_date(value: Any) -> bool:
    """Check if a date is in the future."""
    if isinstance(value, datetime):
        return value > datetime.now()

    if not isinstance(value, str):
        return False

    # Try to parse
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt > datetime.now()
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.replace(tzinfo=None) > datetime.now()
    except (ValueError, AttributeError):
        pass

    return False

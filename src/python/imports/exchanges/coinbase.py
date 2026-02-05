"""Coinbase transaction history CSV parser.

Parses the standard Coinbase transaction export format with columns:
Timestamp, Transaction Type, Asset, Quantity Transacted, Spot Price Currency,
Spot Price at Transaction, Subtotal, Total, Fees, Notes

Filters to BTC transactions only and maps Coinbase transaction types to
our standard transaction types.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


# Expected Coinbase column names (case-insensitive matching)
_EXPECTED_COLUMNS = [
    'timestamp',
    'transaction type',
    'asset',
    'quantity transacted',
    'spot price currency',
    'spot price at transaction',
    'subtotal',
    'total',
    'fees',
    'notes',
]


def _parse_number(value: str) -> float:
    """Parse a numeric string, handling currency symbols and commas."""
    if not value:
        return 0.0
    value = value.strip().lstrip('$').replace(',', '')
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _normalize_header(header: list[str]) -> dict[str, str]:
    """Create mapping from lowercase column name to original column name."""
    return {col.lower().strip(): col for col in header}


@register
class CoinbaseImporter(BaseImporter):
    """Parser for Coinbase transaction history CSV exports."""

    name = "Coinbase"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Coinbase transaction history export"
    expected_columns = [
        "Timestamp", "Transaction Type", "Asset", "Quantity Transacted",
        "Spot Price Currency", "Spot Price at Transaction", "Subtotal",
        "Total", "Fees", "Notes",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Coinbase export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Check for key Coinbase-specific columns
                return (
                    'transaction type' in header_lower and
                    'quantity transacted' in header_lower and
                    'spot price at transaction' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Coinbase transaction history CSV.

        Args:
            file_path: Path to CSV file
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []

            # Create case-insensitive column lookup
            col_map = _normalize_header(reader.fieldnames)

            for row in reader:
                tx = self._parse_row(row, col_map, withdraw_to)
                if tx is not None:
                    transactions.append(tx)

        colnames = [
            'trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
            'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment',
        ]
        return colnames, transactions

    def _parse_row(
        self,
        row: dict[str, str],
        col_map: dict[str, str],
        withdraw_to: str | None,
    ) -> dict[str, Any] | None:
        """Parse a single CSV row into a transaction dict.

        Returns None if the row should be skipped (non-BTC or unrecognized type).
        """
        # Helper to get column value case-insensitively
        def get(col: str) -> str:
            original_col = col_map.get(col.lower(), col)
            return (row.get(original_col) or '').strip()

        # Filter to BTC transactions only
        asset = get('asset').upper()
        if asset != 'BTC':
            return None

        tx_type = get('transaction type')
        timestamp = get('timestamp')
        quantity = _parse_number(get('quantity transacted'))
        spot_price = _parse_number(get('spot price at transaction'))
        spot_currency = get('spot price currency') or 'USD'
        subtotal = _parse_number(get('subtotal'))
        total = _parse_number(get('total'))
        fees = _parse_number(get('fees'))
        notes = get('notes')

        # Calculate USD value if subtotal is missing
        usd_value = subtotal if subtotal > 0 else (quantity * spot_price)

        # Map Coinbase transaction types to our types
        tx_type_upper = tx_type.upper() if tx_type else ''

        if tx_type_upper == 'BUY':
            # Buy BTC with USD
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': total if total > 0 else usd_value,  # Total includes fees
                'sell_curr': spot_currency,
                'fee': fees,
                'fee_curr': spot_currency,
                'group': '',
                'comment': notes,
            }

        elif tx_type_upper == 'SELL':
            # Sell BTC for USD
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': subtotal if subtotal > 0 else usd_value,  # Before fees
                'buy_curr': spot_currency,
                'sell': quantity,
                'sell_curr': 'BTC',
                'fee': fees,
                'fee_curr': spot_currency,
                'group': '',
                'comment': notes,
            }

        elif tx_type_upper == 'SEND':
            # Withdrawal to external wallet
            return {
                'trans_type': 'Withdrawal',
                'created_date': timestamp,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': quantity,
                'sell_curr': 'BTC',
                'fee': fees,
                'fee_curr': 'BTC' if fees > 0 else '',
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to, notes),
            }

        elif tx_type_upper == 'RECEIVE':
            # Deposit from external source
            return {
                'trans_type': 'Deposit',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': notes,
            }

        elif tx_type_upper in ('REWARDS INCOME', 'LEARNING REWARD', 'COINBASE EARN'):
            # Interest/rewards income
            return {
                'trans_type': 'Interest Income',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': notes or tx_type,  # Include original type if no notes
                'usd_equivalent': usd_value if usd_value > 0 else None,
            }

        elif tx_type_upper == 'CONVERT':
            # Convert between assets - for BTC this means buying BTC
            # The subtotal represents the value exchanged
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': usd_value,
                'sell_curr': spot_currency,
                'fee': fees,
                'fee_curr': spot_currency,
                'group': '',
                'comment': notes or 'Converted to BTC',
            }

        # Unknown transaction type - skip
        return None

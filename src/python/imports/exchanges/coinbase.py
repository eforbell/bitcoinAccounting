"""Coinbase transaction history CSV parser.

Supports both legacy Coinbase exports and standard Coinbase account exports.

Legacy columns:
Timestamp, Transaction Type, Asset, Quantity Transacted, Spot Price Currency,
Spot Price at Transaction, Subtotal, Total, Fees, Notes

Standard account export columns:
ID, Timestamp, Transaction Type, Asset, Quantity Transacted, Price Currency,
Price at Transaction, Subtotal, Total (inclusive of fees and/or spread),
Fees and/or Spread, Notes

Standard exports may include metadata rows before the CSV header, e.g.
"Transactions" and "User,...".
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


_BASE_REQUIRED_COLUMNS = frozenset({
    'timestamp',
    'transaction type',
    'asset',
    'quantity transacted',
})

_LEGACY_PRICE_COLUMNS = frozenset({
    'spot price currency',
    'spot price at transaction',
})

_STANDARD_PRICE_COLUMNS = frozenset({
    'price currency',
    'price at transaction',
})


def _parse_number(value: str) -> float:
    """Parse a numeric string, handling currency symbols and commas."""
    if not value:
        return 0.0
    value = value.strip().replace(',', '').replace('$', '')
    if value.startswith('(') and value.endswith(')'):
        value = f"-{value[1:-1]}"
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _normalize_header(header: list[str]) -> dict[str, str]:
    """Create mapping from lowercase column name to original column name."""
    return {col.lower().strip(): col for col in header}


def _is_coinbase_header(header: list[str]) -> bool:
    """Return True when header matches a supported Coinbase schema."""
    header_lower = {col.lower().strip() for col in header}
    if not _BASE_REQUIRED_COLUMNS.issubset(header_lower):
        return False
    has_legacy = _LEGACY_PRICE_COLUMNS.issubset(header_lower)
    has_standard = _STANDARD_PRICE_COLUMNS.issubset(header_lower)
    return has_legacy or has_standard


def _normalize_timestamp(timestamp: str) -> str:
    """Normalize Coinbase timestamps to app-friendly formats."""
    ts = timestamp.strip()
    if ts.endswith(" UTC"):
        # Coinbase account export format: "2022-12-29 11:06:39 UTC"
        return ts[:-4]
    return ts


@register
class CoinbaseImporter(BaseImporter):
    """Parser for Coinbase transaction history CSV exports."""

    name = "Coinbase"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Coinbase transaction history export"
    expected_columns = [
        "Timestamp", "Transaction Type", "Asset", "Quantity Transacted",
        "Spot Price Currency / Price Currency",
        "Spot Price at Transaction / Price at Transaction",
        "Subtotal",
        "Total / Total (inclusive of fees and/or spread)",
        "Fees / Fees and/or Spread",
        "Notes",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Coinbase export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # Some Coinbase exports include metadata lines before the header.
                for _ in range(25):
                    row = next(reader, None)
                    if row is None:
                        return False
                    if _is_coinbase_header(row):
                        return True
                return False
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Coinbase transaction history CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Ignored for exchange parsers
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)

            header: list[str] | None = None
            row_dicts: list[dict[str, str]] = []

            for raw_row in reader:
                if not raw_row:
                    continue

                if header is None:
                    if _is_coinbase_header(raw_row):
                        header = [col.strip() for col in raw_row]
                    continue

                row = [col.strip() for col in raw_row]
                row_dict: dict[str, str] = {}
                for idx, col_name in enumerate(header):
                    row_dict[col_name] = row[idx] if idx < len(row) else ''
                row_dicts.append(row_dict)

            if header is None:
                return [], []

            # Create case-insensitive column lookup from detected header.
            col_map = _normalize_header(header)

            for row in row_dicts:
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

        def get_any(*cols: str) -> str:
            for col in cols:
                value = get(col)
                if value:
                    return value
            return ''

        # Filter to BTC transactions only
        asset = get('asset').upper()
        if asset != 'BTC':
            return None

        tx_type = get('transaction type')
        timestamp = _normalize_timestamp(get('timestamp'))
        quantity = _parse_number(get('quantity transacted'))
        quantity_abs = abs(quantity)
        spot_price = _parse_number(get_any('spot price at transaction', 'price at transaction'))
        spot_currency = get_any('spot price currency', 'price currency') or 'USD'
        subtotal = _parse_number(get('subtotal'))
        total = _parse_number(get_any('total', 'total (inclusive of fees and/or spread)'))
        fees = abs(_parse_number(get_any('fees', 'fees and/or spread')))
        notes = get('notes')

        # Calculate fiat value fallback when subtotal/total are missing.
        usd_value = abs(subtotal) if subtotal != 0 else (quantity_abs * spot_price)
        total_abs = abs(total) if total != 0 else usd_value

        # Map Coinbase transaction types to our types
        tx_type_upper = tx_type.upper() if tx_type else ''

        if tx_type_upper == 'BUY':
            # Buy BTC with USD
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity_abs,
                'buy_curr': 'BTC',
                'sell': total_abs,  # Total includes fees/spread
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
                'buy': usd_value,  # Subtotal is before fees
                'buy_curr': spot_currency,
                'sell': quantity_abs,
                'sell_curr': 'BTC',
                'fee': fees,
                'fee_curr': spot_currency,
                'group': '',
                'comment': notes,
            }

        elif tx_type_upper in ('SEND', 'WITHDRAWAL', 'PRO WITHDRAWAL'):
            # Withdrawal to external wallet
            return {
                'trans_type': 'Withdrawal',
                'created_date': timestamp,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': quantity_abs,
                'sell_curr': 'BTC',
                'fee': fees,
                'fee_curr': 'BTC' if fees > 0 else '',
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to, notes),
            }

        elif tx_type_upper in ('RECEIVE', 'DEPOSIT'):
            # Deposit from external source
            return {
                'trans_type': 'Deposit',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity_abs,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': notes,
            }

        elif tx_type_upper in (
            'REWARD INCOME',
            'REWARDS INCOME',
            'LEARNING REWARD',
            'COINBASE EARN',
        ):
            # Interest/rewards income
            return {
                'trans_type': 'Interest Income',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity_abs,
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
                'buy': quantity_abs,
                'buy_curr': 'BTC',
                'sell': usd_value,
                'sell_curr': spot_currency,
                'fee': fees,
                'fee_curr': spot_currency,
                'group': '',
                'comment': notes or 'Converted to BTC',
            }

        elif tx_type_upper == 'EXCHANGE DEPOSIT':
            # Transfer between Coinbase and Coinbase Pro/Advanced Trade.
            if quantity < 0:
                return {
                    'trans_type': 'Withdrawal',
                    'created_date': timestamp,
                    'exchange': self._get_withdrawal_exchange(withdraw_to),
                    'buy': 0.0,
                    'buy_curr': '',
                    'sell': quantity_abs,
                    'sell_curr': 'BTC',
                    'fee': fees,
                    'fee_curr': 'BTC' if fees > 0 else '',
                    'group': '',
                    'comment': self._get_withdrawal_comment(withdraw_to, notes),
                }
            return {
                'trans_type': 'Deposit',
                'created_date': timestamp,
                'exchange': 'Coinbase',
                'buy': quantity_abs,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': notes,
            }

        # Unknown transaction type - skip
        return None

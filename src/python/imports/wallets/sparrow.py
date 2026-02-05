"""Sparrow Wallet transaction history CSV parser.

Parses the standard Sparrow Wallet transaction export format with columns:
Date, Label, Value, Balance, Fee, TXID

Sparrow is a Bitcoin-only desktop wallet known for its privacy features
and UTXO management. Value and Fee columns use satoshis by default.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


# Expected Sparrow Wallet column names (case-insensitive matching)
_EXPECTED_COLUMNS = [
    'date',
    'label',
    'value',
    'balance',
    'fee',
    'txid',
]


def _parse_number(value: str) -> float:
    """Parse a numeric string, handling whitespace and empty values."""
    if not value:
        return 0.0
    value = value.strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_satoshis(value_str: str) -> float:
    """Parse satoshi value and convert to BTC.

    Tries parsing as integer satoshis first, falls back to decimal BTC.
    """
    if not value_str:
        return 0.0

    value_str = value_str.strip()
    if not value_str:
        return 0.0

    # Try as integer satoshis first
    try:
        value_sats = int(value_str)
        return value_sats / 100_000_000
    except ValueError:
        pass

    # Fallback to decimal BTC
    try:
        return float(value_str)
    except ValueError:
        return 0.0


def _normalize_header(header: list[str]) -> dict[str, str]:
    """Create mapping from lowercase column name to original column name."""
    return {col.lower().strip(): col for col in header}


@register
class SparrowImporter(BaseImporter):
    """Parser for Sparrow Wallet transaction history CSV exports."""

    name = "Sparrow"
    source_type = "wallet"
    file_patterns = ["*.csv"]
    description = "Sparrow Wallet transaction history export"
    expected_columns = [
        "Date", "Label", "Value", "Balance", "Fee", "TXID",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Sparrow Wallet export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Check for key Sparrow-specific columns
                # The combination of 'label' and 'balance' is distinctive for Sparrow
                return (
                    'date' in header_lower and
                    'label' in header_lower and
                    'value' in header_lower and
                    'balance' in header_lower and
                    'txid' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Sparrow Wallet transaction history CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Name of this wallet (required for deposits)
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        colnames = ['date', 'label', 'value', 'balance', 'fee', 'txid']

        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return colnames, transactions

            # Create case-insensitive mapping
            header_map = _normalize_header(list(reader.fieldnames))

            for row in reader:
                value_key = header_map.get('value')
                fee_key = header_map.get('fee')
                label_key = header_map.get('label')
                date_key = header_map.get('date')

                if not value_key or not date_key:
                    continue

                value_str = row.get(value_key, '0')
                fee_str = row.get(fee_key, '0') if fee_key else '0'
                label = row.get(label_key, '') if label_key else ''
                date_str = row.get(date_key, '')

                # Parse satoshi values and convert to BTC
                value_btc = _parse_satoshis(value_str)
                fee_btc = _parse_satoshis(fee_str)

                # Skip transactions with zero value
                if value_btc == 0:
                    continue

                transaction: dict[str, Any] = {
                    'created_date': date_str,
                    'group': None,
                    'comment': label if label else None
                }

                # Positive value = incoming (Deposit)
                if value_btc > 0:
                    transaction['trans_type'] = 'Deposit'
                    transaction['buy'] = value_btc
                    transaction['buy_curr'] = 'BTC'
                    transaction['exchange'] = wallet_name if wallet_name else 'Sparrow'
                    transactions.append(transaction)

                # Negative value = outgoing (Withdrawal)
                elif value_btc < 0:
                    transaction['trans_type'] = 'Withdrawal'
                    transaction['sell'] = abs(value_btc)
                    transaction['sell_curr'] = 'BTC'
                    transaction['fee'] = fee_btc
                    transaction['fee_curr'] = 'BTC' if fee_btc > 0 else ''
                    transaction['exchange'] = self._get_withdrawal_exchange(withdraw_to)

                    # Combine label and review comment
                    withdrawal_comment = self._get_withdrawal_comment(withdraw_to)
                    if label and withdrawal_comment:
                        transaction['comment'] = f"{label}; {withdrawal_comment}"
                    elif label:
                        transaction['comment'] = label
                    else:
                        transaction['comment'] = withdrawal_comment

                    transactions.append(transaction)

        return colnames, transactions

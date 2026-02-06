"""Trezor Suite transaction history CSV parser.

Parses the standard Trezor Suite transaction export format with columns:
Date, Time, Type, Amount, Fee, Address, TX ID

Maps Trezor transaction types (recv/sent) to our standard transaction types.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


# Expected Trezor Suite column names (case-insensitive matching)
_EXPECTED_COLUMNS = [
    'date',
    'time',
    'type',
    'amount',
    'fee',
    'address',
    'tx id',
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


def _normalize_header(header: list[str]) -> dict[str, str]:
    """Create mapping from lowercase column name to original column name."""
    return {col.lower().strip(): col for col in header}


@register
class TrezorImporter(BaseImporter):
    """Parser for Trezor Suite transaction history CSV exports."""

    name = "Trezor"
    source_type = "wallet"
    file_patterns = ["*.csv"]
    description = "Trezor Suite transaction history export"
    expected_columns = [
        "Date", "Time", "Type", "Amount", "Fee", "Address", "TX ID",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Trezor Suite export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Check for key Trezor-specific columns
                # Using 'tx id' as distinctive marker (Ledger uses 'hash')
                return (
                    'date' in header_lower and
                    'type' in header_lower and
                    'tx id' in header_lower and
                    'address' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Trezor Suite transaction history CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Name of this wallet (required for deposits)
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        colnames = ['date', 'time', 'type', 'amount', 'fee', 'address', 'tx_id']

        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return colnames, transactions

            # Create case-insensitive mapping
            header_map = _normalize_header(list(reader.fieldnames))

            for row in reader:
                type_key = header_map.get('type')
                amount_key = header_map.get('amount')
                fee_key = header_map.get('fee')
                date_key = header_map.get('date')
                time_key = header_map.get('time')

                if not type_key or not amount_key:
                    continue

                tx_type = row.get(type_key, '').lower()
                amount_str = row.get(amount_key, '0')
                fee_str = row.get(fee_key, '0') if fee_key else '0'
                date_str = row.get(date_key, '') if date_key else ''
                time_str = row.get(time_key, '') if time_key else ''

                amount = _parse_number(amount_str)
                fee = _parse_number(fee_str)

                # Skip transactions with zero amount
                if amount == 0:
                    continue

                # Combine date and time if both present
                if date_str and time_str:
                    created_date = f"{date_str} {time_str}"
                else:
                    created_date = date_str

                transaction: dict[str, Any] = {
                    'created_date': created_date,
                    'group': None
                }

                # Trezor uses 'recv' or 'received' for receiving
                if tx_type in ('recv', 'received'):
                    transaction['trans_type'] = 'Deposit'
                    transaction['buy'] = amount
                    transaction['buy_curr'] = 'BTC'
                    transaction['exchange'] = wallet_name if wallet_name else 'Trezor'
                    transactions.append(transaction)

                # Trezor uses 'sent' or 'send' for sending
                elif tx_type in ('sent', 'send'):
                    transaction['trans_type'] = 'Withdrawal'
                    transaction['sell'] = abs(amount)
                    transaction['sell_curr'] = 'BTC'
                    transaction['fee'] = fee
                    transaction['fee_curr'] = 'BTC' if fee > 0 else ''
                    transaction['exchange'] = self._get_withdrawal_exchange(withdraw_to)
                    transaction['comment'] = self._get_withdrawal_comment(withdraw_to)
                    transactions.append(transaction)

        return colnames, transactions

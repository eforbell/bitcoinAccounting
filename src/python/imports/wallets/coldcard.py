"""Coldcard transaction history CSV parser.

Parses the Coldcard address explorer transaction export format with columns:
Date, Type, Amount, Fee, TXID

Coldcard is a Bitcoin-only hardware wallet. Amount values are in decimal BTC.
Type-based and sign-based transaction detection are both supported to handle
firmware version variations.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


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
class ColdcardImporter(BaseImporter):
    """Parser for Coldcard transaction history CSV exports."""

    name = "Coldcard"
    source_type = "wallet"
    file_patterns = ["*.csv"]
    description = "Coldcard address explorer transaction export"
    expected_columns = [
        "Date", "Type", "Amount", "Fee", "TXID",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Coldcard export.

        Distinguishes from:
        - Trezor: has 'tx id' (space) and 'address', not 'txid'
        - Sparrow: has 'value'/'label'/'balance', not 'amount'/'type'
        - Ledger: has 'operation type', not 'type'
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Coldcard-specific: 'type' + 'amount' + 'txid' (one word)
                # Trezor uses 'tx id' (two words) and has 'address'
                # Sparrow uses 'value' not 'amount' and has 'label'/'balance'
                return (
                    'date' in header_lower and
                    'type' in header_lower and
                    'amount' in header_lower and
                    'txid' in header_lower and
                    'address' not in header_lower and
                    'label' not in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Coldcard transaction history CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Name of this wallet (required for deposits)
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        colnames = ['date', 'type', 'amount', 'fee', 'txid']

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

                if not amount_key:
                    continue

                tx_type = row.get(type_key, '').lower() if type_key else ''
                amount_str = row.get(amount_key, '0')
                fee_str = row.get(fee_key, '0') if fee_key else '0'
                date_str = row.get(date_key, '') if date_key else ''

                amount = _parse_number(amount_str)
                fee = _parse_number(fee_str)

                # Skip transactions with zero amount
                if amount == 0:
                    continue

                transaction: dict[str, Any] = {
                    'created_date': date_str,
                    'group': None,
                }

                # Determine transaction type from Type column or amount sign
                is_deposit = (
                    tx_type in ('receive', 'received', 'in') or
                    (not tx_type and amount > 0)
                )
                is_withdrawal = (
                    tx_type in ('send', 'sent', 'out') or
                    (not tx_type and amount < 0)
                )

                if is_deposit:
                    transaction['trans_type'] = 'Deposit'
                    transaction['buy'] = abs(amount)
                    transaction['buy_curr'] = 'BTC'
                    transaction['exchange'] = wallet_name if wallet_name else 'Coldcard'
                    transactions.append(transaction)

                elif is_withdrawal:
                    transaction['trans_type'] = 'Withdrawal'
                    transaction['sell'] = abs(amount)
                    transaction['sell_curr'] = 'BTC'
                    transaction['fee'] = fee
                    transaction['fee_curr'] = 'BTC' if fee > 0 else ''
                    transaction['exchange'] = self._get_withdrawal_exchange(withdraw_to)
                    transaction['comment'] = self._get_withdrawal_comment(withdraw_to)
                    transactions.append(transaction)

        return colnames, transactions

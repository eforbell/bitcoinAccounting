"""Ledger Live transaction history CSV parser.

Parses the standard Ledger Live operation export format with columns:
Operation Date, Currency, Operation Type, Amount, Fees, Hash, Account Name, xpub,
Cost Currency, Cost, Cost at Export

Filters to BTC transactions only and maps Ledger operation types to
our standard transaction types.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


# Expected Ledger Live column names (case-insensitive matching)
_EXPECTED_COLUMNS = [
    'operation date',
    'currency',
    'operation type',
    'amount',
    'fees',
    'hash',
    'account name',
    'xpub',
    'cost currency',
    'cost',
    'cost at export',
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
class LedgerImporter(BaseImporter):
    """Parser for Ledger Live operation history CSV exports."""

    name = "Ledger"
    source_type = "wallet"
    file_patterns = ["*.csv"]
    description = "Ledger Live operation history export"
    expected_columns = [
        "Operation Date", "Currency", "Operation Type", "Amount", "Fees",
        "Hash", "Account Name", "xpub", "Cost Currency", "Cost", "Cost at Export",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Ledger Live export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Check for key Ledger-specific columns
                return (
                    'operation date' in header_lower and
                    'operation type' in header_lower and
                    'xpub' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Ledger Live operation history CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Name of this wallet (required for deposits)
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions) where transactions is a list
            of dicts ready for import_transactions().
        """
        colnames = [
            'created_date', 'curr', 'op_type', 'value', 'fee', 'hash',
            'account name', 'xpub', 'cost_currency', 'cost', 'cost_at_export'
        ]

        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return colnames, transactions

            # Create case-insensitive mapping
            header_map = _normalize_header(list(reader.fieldnames))

            for row in reader:
                # Skip non-BTC transactions
                curr_key = header_map.get('currency')
                if not curr_key:
                    continue

                curr = row.get(curr_key, '')
                if curr.upper() != 'BTC':
                    continue

                op_type_key = header_map.get('operation type')
                amount_key = header_map.get('amount')
                fee_key = header_map.get('fees')
                date_key = header_map.get('operation date')

                if not op_type_key or not amount_key:
                    continue

                op_type = row.get(op_type_key, '')
                value_str = row.get(amount_key, '0')
                fee_str = row.get(fee_key, '0') if fee_key else '0'
                created_date = row.get(date_key, '') if date_key else ''

                value = _parse_number(value_str)
                fee = _parse_number(fee_str)

                # Skip transactions with zero value
                if value == 0:
                    continue

                transaction: dict[str, Any] = {
                    'created_date': created_date,
                    'group': None
                }

                # Incoming transactions → Deposit
                if op_type == 'IN':
                    transaction['trans_type'] = 'Deposit'
                    transaction['buy_curr'] = 'BTC'
                    transaction['buy'] = value
                    transaction['exchange'] = wallet_name if wallet_name else 'Ledger'
                    transactions.append(transaction)

                # Outgoing transactions → Withdrawal
                elif op_type == 'OUT':
                    transaction['trans_type'] = 'Withdrawal'
                    transaction['sell_curr'] = 'BTC'
                    transaction['sell'] = abs(value)
                    transaction['fee'] = fee
                    transaction['fee_curr'] = 'BTC' if fee > 0 else ''
                    transaction['exchange'] = self._get_withdrawal_exchange(withdraw_to)
                    transaction['comment'] = self._get_withdrawal_comment(withdraw_to)
                    transactions.append(transaction)

        return colnames, transactions

"""Bitcoin wallet import utilities for common hardware and software wallets.

This module provides import functionality for popular Bitcoin wallets:
- Ledger Live (hardware wallet)
- Trezor Suite (hardware wallet)
- Sparrow Wallet (Bitcoin-only desktop wallet)
- Coldcard (hardware wallet)

Each import function returns a tuple: (colnames, transactions)
where transactions is a list of dicts ready for CryptoAccounts.import_transactions()
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


def import_ledger_live_csv(in_file: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Import Bitcoin transactions from Ledger Live CSV export.

    Ledger Live exports include operation type, amount, fees, and historical cost.

    Args:
        in_file: Path to Ledger Live CSV export file

    Returns:
        tuple: (column_names, transactions)
            - column_names: List of expected columns
            - transactions: List of transaction dicts ready for import_transactions()

    CSV Format (Ledger Live):
        Operation Date, Currency, Operation Type, Amount, Fees, Hash, Account Name, xpub, Cost Currency, Cost, Cost at Export
    """
    colnames = [
        'created_date', 'curr', 'op_type', 'value', 'fee', 'hash',
        'account name', 'xpub', 'cost_currency', 'cost', 'cost_at_export'
    ]

    transactions: list[dict[str, Any]] = []

    with open(in_file, 'r', encoding='utf-8') as csv_in:
        reader = csv.DictReader(csv_in)

        for row in reader:
            # Skip non-BTC transactions
            curr = row.get('Currency', '')
            if curr.upper() != 'BTC':
                continue

            op_type = row.get('Operation Type', '')
            value = row.get('Amount', '0')
            fee = row.get('Fees', '0')

            # Skip transactions with zero value
            if not value or float(value) == 0:
                continue

            transaction: dict[str, Any] = {
                'created_date': row.get('Operation Date', ''),
                'exchange': 'Ledger',
                'group': None
            }

            # Incoming transactions → Deposit
            if op_type == 'IN':
                transaction['trans_type'] = 'Deposit'
                transaction['buy_curr'] = 'BTC'
                transaction['buy'] = value
                transactions.append(transaction)

            # Outgoing transactions → Withdrawal
            elif op_type == 'OUT':
                transaction['trans_type'] = 'Withdrawal'
                transaction['sell_curr'] = 'BTC'
                transaction['sell'] = abs(float(value))
                transaction['fee'] = float(fee) if fee else 0.0
                transaction['fee_curr'] = 'BTC'
                transactions.append(transaction)

    return colnames, transactions


def import_trezor_suite_csv(in_file: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Import Bitcoin transactions from Trezor Suite CSV export.

    Trezor Suite exports transaction history with type, amount, and fee.

    Args:
        in_file: Path to Trezor Suite CSV export file

    Returns:
        tuple: (column_names, transactions)

    CSV Format (Trezor Suite):
        Date, Time, Type, Amount, Fee, Address, TX ID
    """
    colnames = ['date', 'time', 'type', 'amount', 'fee', 'address', 'tx_id']

    transactions: list[dict[str, Any]] = []

    with open(in_file, 'r', encoding='utf-8') as csv_in:
        reader = csv.DictReader(csv_in)

        for row in reader:
            tx_type = row.get('Type', '').lower()
            amount = row.get('Amount', '0')
            fee = row.get('Fee', '0')
            date_str = row.get('Date', '')
            time_str = row.get('Time', '')

            # Skip zero amounts
            if not amount or float(amount) == 0:
                continue

            # Combine date and time if both present
            if date_str and time_str:
                created_date = f"{date_str} {time_str}"
            else:
                created_date = date_str

            transaction: dict[str, Any] = {
                'created_date': created_date,
                'exchange': 'Trezor',
                'group': None
            }

            # Trezor uses 'recv' for receiving, 'sent' for sending
            if tx_type in ('recv', 'received'):
                transaction['trans_type'] = 'Deposit'
                transaction['buy'] = amount
                transaction['buy_curr'] = 'BTC'
                transactions.append(transaction)

            elif tx_type in ('sent', 'send'):
                transaction['trans_type'] = 'Withdrawal'
                transaction['sell'] = abs(float(amount))
                transaction['sell_curr'] = 'BTC'
                transaction['fee'] = float(fee) if fee else 0.0
                transaction['fee_curr'] = 'BTC'
                transactions.append(transaction)

    return colnames, transactions


def import_sparrow_csv(in_file: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Import transactions from Sparrow Wallet CSV export.

    Sparrow Wallet is a Bitcoin-only desktop wallet known for its
    privacy features and UTXO management.

    Args:
        in_file: Path to Sparrow Wallet CSV export file

    Returns:
        tuple: (column_names, transactions)

    CSV Format (Sparrow):
        Date, Label, Value, Balance, Fee, TXID
    """
    colnames = ['date', 'label', 'value', 'balance', 'fee', 'txid']

    transactions: list[dict[str, Any]] = []

    with open(in_file, 'r', encoding='utf-8') as csv_in:
        reader = csv.DictReader(csv_in)

        for row in reader:
            value_str = row.get('Value', '0')
            fee_str = row.get('Fee', '0')
            label = row.get('Label', '')
            date_str = row.get('Date', '')

            # Skip zero values
            if not value_str:
                continue

            # Sparrow uses satoshis, convert to BTC
            try:
                value_sats = int(value_str)
                value_btc = value_sats / 100_000_000
            except ValueError:
                # Try as decimal BTC
                value_btc = float(value_str)

            try:
                fee_sats = int(fee_str) if fee_str else 0
                fee_btc = fee_sats / 100_000_000
            except ValueError:
                fee_btc = float(fee_str) if fee_str else 0.0

            if value_btc == 0:
                continue

            transaction: dict[str, Any] = {
                'created_date': date_str,
                'exchange': 'Sparrow',
                'group': None,
                'comment': label
            }

            # Positive value = incoming (Deposit)
            if value_btc > 0:
                transaction['trans_type'] = 'Deposit'
                transaction['buy'] = value_btc
                transaction['buy_curr'] = 'BTC'
                transactions.append(transaction)

            # Negative value = outgoing (Withdrawal)
            elif value_btc < 0:
                transaction['trans_type'] = 'Withdrawal'
                transaction['sell'] = abs(value_btc)
                transaction['sell_curr'] = 'BTC'
                transaction['fee'] = fee_btc
                transaction['fee_curr'] = 'BTC'
                transactions.append(transaction)

    return colnames, transactions


def import_coldcard_csv(in_file: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Import transactions from Coldcard transaction log.

    Coldcard is a Bitcoin-only hardware wallet that can export transaction history
    via its address explorer feature.

    Args:
        in_file: Path to Coldcard CSV export file

    Returns:
        tuple: (column_names, transactions)

    Note: Coldcard exports vary by firmware version. This handles the common format.
    """
    colnames = ['date', 'type', 'amount', 'fee', 'txid']

    transactions: list[dict[str, Any]] = []

    with open(in_file, 'r', encoding='utf-8') as csv_in:
        reader = csv.DictReader(csv_in)

        for row in reader:
            amount_str = row.get('Amount', row.get('amount', '0'))
            tx_type = row.get('Type', row.get('type', '')).lower()
            date_str = row.get('Date', row.get('date', ''))
            fee_str = row.get('Fee', row.get('fee', '0'))

            try:
                amount = float(amount_str)
            except ValueError:
                continue

            if amount == 0:
                continue

            try:
                fee = float(fee_str) if fee_str else 0.0
            except ValueError:
                fee = 0.0

            transaction: dict[str, Any] = {
                'created_date': date_str,
                'exchange': 'Coldcard',
                'group': None
            }

            if tx_type in ('receive', 'received', 'in') or amount > 0:
                transaction['trans_type'] = 'Deposit'
                transaction['buy'] = abs(amount)
                transaction['buy_curr'] = 'BTC'
                transactions.append(transaction)

            elif tx_type in ('send', 'sent', 'out') or amount < 0:
                transaction['trans_type'] = 'Withdrawal'
                transaction['sell'] = abs(amount)
                transaction['sell_curr'] = 'BTC'
                transaction['fee'] = fee
                transaction['fee_curr'] = 'BTC'
                transactions.append(transaction)

    return colnames, transactions


# Export all import functions
__all__ = [
    'import_ledger_live_csv',
    'import_trezor_suite_csv',
    'import_sparrow_csv',
    'import_coldcard_csv',
]

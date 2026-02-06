"""Coinbase Pro transaction history CSV parser.

Parses the Coinbase Pro account statement export format which has a unique structure:
- Trades appear as multiple rows with the same trade id:
  - Two 'match' rows (one for each leg of the trade)
  - One 'fee' row for trading fees
- Deposits and withdrawals are single rows with type='deposit' or 'withdrawal'
- Currency is in the 'amount/balance unit' column

Columns: portfolio, type, time, amount, balance, amount/balance unit,
         transfer id, trade id, order id

Trade matching logic:
- Positive amount = asset received (buy leg)
- Negative amount = asset spent (sell leg)
- Only imports trades where BTC is on one side (filters out altcoin-only trades)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter, is_fiat
from imports.registry import register


def _parse_number(value: str) -> float:
    """Parse a numeric string, handling empty values."""
    if not value:
        return 0.0
    value = value.strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


@register
class CoinbaseProImporter(BaseImporter):
    """Parser for Coinbase Pro account statement CSV exports."""

    name = "CoinbasePro"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Coinbase Pro account statement export"
    expected_columns = [
        "portfolio", "type", "time", "amount", "balance",
        "amount/balance unit", "transfer id", "trade id", "order id",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Coinbase Pro export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Coinbase Pro specific: has these three distinctive columns
                return (
                    'portfolio' in header_lower and
                    'trade id' in header_lower and
                    'amount/balance unit' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Coinbase Pro account statement CSV.

        The key complexity is trade matching:
        1. Group all rows by trade_id
        2. For each trade, combine the two match legs (buy + sell) into one transaction
        3. Add fee from the fee row
        4. Handle deposits and withdrawals as single-row transactions

        Args:
            file_path: Path to CSV file
            wallet_name: Ignored for exchange parsers
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions)
        """
        # First pass: group rows by trade_id, and collect standalone deposits/withdrawals
        rows_by_trade_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        standalone_rows: list[dict[str, str]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []

            # Create case-insensitive column lookup
            col_map = {col.lower().strip(): col for col in reader.fieldnames}

            for row in reader:
                # Helper to get column value case-insensitively
                def get(col: str) -> str:
                    original_col = col_map.get(col.lower(), col)
                    return (row.get(original_col) or '').strip()

                row_type = get('type').lower()
                trade_id = get('trade id')

                # Normalize row data
                normalized_row = {
                    'portfolio': get('portfolio'),
                    'type': row_type,
                    'time': get('time'),
                    'amount': get('amount'),
                    'balance': get('balance'),
                    'currency': get('amount/balance unit').upper(),
                    'transfer_id': get('transfer id'),
                    'trade_id': trade_id,
                    'order_id': get('order id'),
                }

                # Group trades by trade_id
                if row_type in ('match', 'fee') and trade_id:
                    rows_by_trade_id[trade_id].append(normalized_row)
                elif row_type in ('deposit', 'withdrawal'):
                    standalone_rows.append(normalized_row)

        # Second pass: process trades
        transactions: list[dict[str, Any]] = []

        for trade_id, rows in rows_by_trade_id.items():
            tx = self._process_trade(rows)
            if tx is not None:
                transactions.append(tx)

        # Third pass: process deposits and withdrawals
        for row in standalone_rows:
            if row['type'] == 'deposit':
                tx = self._process_deposit(row)
                if tx is not None:
                    transactions.append(tx)
            elif row['type'] == 'withdrawal':
                tx = self._process_withdrawal(row, withdraw_to)
                if tx is not None:
                    transactions.append(tx)

        # Sort by timestamp
        transactions.sort(key=lambda x: x.get('created_date', ''))

        colnames = [
            'trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
            'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment',
        ]
        return colnames, transactions

    def _process_trade(self, rows: list[dict[str, str]]) -> dict[str, Any] | None:
        """Process trade rows (2 match rows + optional fee row).

        In a trade:
        - Positive amount = asset received (buy leg)
        - Negative amount = asset spent (sell leg)
        - Fee row contains fee amount (always negative)

        Only imports trades where BTC is on at least one side.
        """
        if len(rows) < 2:
            # Need at least 2 match rows for a complete trade
            return None

        # Separate match rows and fee rows
        match_rows = [r for r in rows if r['type'] == 'match']
        fee_rows = [r for r in rows if r['type'] == 'fee']

        if len(match_rows) != 2:
            # Invalid trade structure
            return None

        # Identify buy and sell legs
        buy_leg = None
        sell_leg = None

        for row in match_rows:
            amount = _parse_number(row['amount'])
            if amount > 0:
                buy_leg = row
            elif amount < 0:
                sell_leg = row

        if not buy_leg or not sell_leg:
            # Missing a leg - invalid trade
            return None

        # Extract currencies
        buy_curr = buy_leg['currency']
        sell_curr = sell_leg['currency']

        # Filter: only import trades where BTC is on at least one side
        if buy_curr != 'BTC' and sell_curr != 'BTC':
            return None

        # Extract amounts
        buy_amount = _parse_number(buy_leg['amount'])
        sell_amount = abs(_parse_number(sell_leg['amount']))

        # Extract fee
        fee = 0.0
        fee_curr = ''
        if fee_rows:
            # Coinbase Pro fees are in the same currency as the sell side
            fee = abs(_parse_number(fee_rows[0]['amount']))
            fee_curr = fee_rows[0]['currency']

        # Use timestamp from first match row
        timestamp = match_rows[0]['time']

        return {
            'trans_type': 'Trade',
            'created_date': timestamp,
            'exchange': 'CoinbasePro',
            'buy': buy_amount,
            'buy_curr': buy_curr,
            'sell': sell_amount,
            'sell_curr': sell_curr,
            'fee': fee,
            'fee_curr': fee_curr if fee > 0 else '',
            'group': '',
            'comment': f"Trade ID: {rows[0]['trade_id']}",
        }

    def _process_deposit(self, row: dict[str, str]) -> dict[str, Any] | None:
        """Process deposit row.

        Only imports BTC and fiat deposits.
        Filters out altcoin deposits.
        """
        currency = row['currency']
        amount = _parse_number(row['amount'])

        # Filter: only BTC or fiat deposits
        if currency != 'BTC' and not is_fiat(currency):
            return None

        if amount <= 0:
            return None

        return {
            'trans_type': 'Deposit',
            'created_date': row['time'],
            'exchange': 'CoinbasePro',
            'buy': amount,
            'buy_curr': currency,
            'sell': 0.0,
            'sell_curr': '',
            'fee': 0.0,
            'fee_curr': '',
            'group': '',
            'comment': f"Transfer ID: {row['transfer_id']}" if row['transfer_id'] else '',
        }

    def _process_withdrawal(
        self,
        row: dict[str, str],
        withdraw_to: str | None,
    ) -> dict[str, Any] | None:
        """Process withdrawal row.

        Only imports BTC and fiat withdrawals.
        Filters out altcoin withdrawals.
        """
        currency = row['currency']
        amount = abs(_parse_number(row['amount']))

        # Filter: only BTC or fiat withdrawals
        if currency != 'BTC' and not is_fiat(currency):
            return None

        if amount <= 0:
            return None

        # Determine exchange field based on currency and withdraw_to
        if currency == 'BTC':
            exchange = self._get_withdrawal_exchange(withdraw_to)
            comment = self._get_withdrawal_comment(withdraw_to)
        else:
            # Fiat withdrawals stay at CoinbasePro (bank transfer)
            exchange = 'CoinbasePro'
            comment = 'Fiat withdrawal'

        # Add transfer ID to comment if present
        if row['transfer_id']:
            if comment:
                comment = f"{comment}; Transfer ID: {row['transfer_id']}"
            else:
                comment = f"Transfer ID: {row['transfer_id']}"

        return {
            'trans_type': 'Withdrawal',
            'created_date': row['time'],
            'exchange': exchange,
            'buy': 0.0,
            'buy_curr': '',
            'sell': amount,
            'sell_curr': currency,
            'fee': 0.0,
            'fee_curr': '',
            'group': '',
            'comment': comment,
        }

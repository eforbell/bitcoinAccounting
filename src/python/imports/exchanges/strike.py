"""Strike transaction history CSV parser.

Strike is a Bitcoin-only exchange — no asset filtering required.

Typical Strike export columns:
  Date, Type, Description, BTC Amount, USD Amount, Fee (USD), Fee (BTC)

Transaction types mapped:
  Purchase  -> Trade  (buy BTC, sell USD)
  Send      -> Withdrawal
  Receive   -> Deposit
  Payment   -> Withdrawal (Lightning payment out)
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


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


@register
class StrikeImporter(BaseImporter):
    """Parser for Strike transaction history CSV exports."""

    name = "Strike"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Strike transaction history export"
    expected_columns = [
        "Date", "Type", "Description", "BTC Amount", "USD Amount",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Strike export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Strike-specific: has both "btc amount" and "usd amount"
                return (
                    'btc amount' in header_lower and
                    'usd amount' in header_lower and
                    'type' in header_lower
                )
        except (OSError, csv.Error):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Strike transaction history CSV.

        Args:
            file_path: Path to CSV file
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions)
        """
        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []

            col_map = {col.lower().strip(): col for col in reader.fieldnames}

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
        """Parse a single CSV row into a transaction dict."""
        def get(col: str) -> str:
            original_col = col_map.get(col.lower(), col)
            return (row.get(original_col) or '').strip()

        tx_type = get('type').upper()
        date = get('date')
        btc_amount = _parse_number(get('btc amount'))
        usd_amount = _parse_number(get('usd amount'))
        description = get('description')

        # Fee can be in USD or BTC depending on column availability
        fee_usd = _parse_number(get('fee (usd)'))
        fee_btc = _parse_number(get('fee (btc)'))

        if not date or not tx_type:
            return None

        if tx_type == 'PURCHASE':
            # Buy BTC with USD — usd_amount is cost before fees
            return {
                'trans_type': 'Trade',
                'created_date': date,
                'exchange': 'Strike',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': usd_amount + fee_usd,  # Total USD out of pocket
                'sell_curr': 'USD',
                'fee': fee_usd,
                'fee_curr': 'USD',
                'group': '',
                'comment': description,
            }

        elif tx_type in ('SEND', 'PAYMENT'):
            # Withdrawal — send BTC out
            return {
                'trans_type': 'Withdrawal',
                'created_date': date,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': btc_amount,
                'sell_curr': 'BTC',
                'fee': fee_btc if fee_btc > 0 else fee_usd,
                'fee_curr': 'BTC' if fee_btc > 0 else ('USD' if fee_usd > 0 else ''),
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to, description),
            }

        elif tx_type == 'RECEIVE':
            # Deposit — receive BTC from outside
            return {
                'trans_type': 'Deposit',
                'created_date': date,
                'exchange': 'Strike',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': description,
            }

        # Unknown type — skip
        return None

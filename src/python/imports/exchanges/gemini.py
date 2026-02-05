"""Gemini transaction history CSV parser.

Gemini exports trade/transfer/earn history via API or xlsx.
Third-party tools (e.g. gemini-exports) convert to CSV with
hyphenated column names:

  time, base-asset, quote-asset, type, price, quantity, total,
  fee, fee-currency, trade-id

Only rows where base-asset == BTC are kept.

Transaction types mapped:
  Buy            -> Trade  (buy BTC, sell quote-asset)
  Sell           -> Trade  (sell BTC, buy quote-asset)
  Deposit        -> Deposit
  Withdrawal     -> Withdrawal (apply --withdraw-to or default)
  Earn / Earn Interest -> Interest Income (Gemini Earn rewards)
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
class GeminiImporter(BaseImporter):
    """Parser for Gemini transaction history CSV exports."""

    name = "Gemini"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Gemini transaction history export"
    expected_columns = [
        "time", "base-asset", "quote-asset", "type", "price",
        "quantity", "total", "fee", "fee-currency", "trade-id",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Gemini transaction export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Hyphenated column names are Gemini-specific
                return (
                    'base-asset' in header_lower and
                    'quote-asset' in header_lower and
                    'trade-id' in header_lower
                )
        except (OSError, csv.Error):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Gemini transaction history CSV.

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
        """Parse a single row.  Returns None for non-BTC or unknown types."""
        def get(col: str) -> str:
            original_col = col_map.get(col.lower(), col)
            return (row.get(original_col) or '').strip()

        base_asset = get('base-asset').upper()
        if base_asset != 'BTC':
            return None

        tx_type = get('type').upper()
        timestamp = get('time')
        quote_asset = get('quote-asset').upper() or 'USD'
        quantity = _parse_number(get('quantity'))
        total = _parse_number(get('total'))
        price = _parse_number(get('price'))
        fee = _parse_number(get('fee'))
        fee_currency = get('fee-currency').upper()

        if not timestamp or not tx_type:
            return None

        if tx_type == 'BUY':
            # total = quote-asset spent; fall back to price * quantity
            sell_amount = total if total > 0 else price * quantity
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Gemini',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': sell_amount,
                'sell_curr': quote_asset,
                'fee': fee,
                'fee_curr': fee_currency if fee > 0 else '',
                'group': '',
                'comment': '',
            }

        elif tx_type == 'SELL':
            # total = quote-asset received; fall back to price * quantity
            buy_amount = total if total > 0 else price * quantity
            return {
                'trans_type': 'Trade',
                'created_date': timestamp,
                'exchange': 'Gemini',
                'buy': buy_amount,
                'buy_curr': quote_asset,
                'sell': quantity,
                'sell_curr': 'BTC',
                'fee': fee,
                'fee_curr': fee_currency if fee > 0 else '',
                'group': '',
                'comment': '',
            }

        elif tx_type == 'DEPOSIT':
            return {
                'trans_type': 'Deposit',
                'created_date': timestamp,
                'exchange': 'Gemini',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': fee,
                'fee_curr': fee_currency if fee > 0 else '',
                'group': '',
                'comment': '',
            }

        elif tx_type == 'WITHDRAWAL':
            return {
                'trans_type': 'Withdrawal',
                'created_date': timestamp,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': quantity,
                'sell_curr': 'BTC',
                'fee': fee,
                'fee_curr': fee_currency if fee > 0 else '',
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to),
            }

        elif tx_type in ('EARN', 'EARN INTEREST'):
            # Gemini Earn interest rewards
            return {
                'trans_type': 'Interest Income',
                'created_date': timestamp,
                'exchange': 'Gemini',
                'buy': quantity,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': 'Gemini Earn',
            }

        # Unknown type — skip
        return None

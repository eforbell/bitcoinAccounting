"""Swan Bitcoin deposits & purchases CSV parser.

Swan Bitcoin is a DCA (Dollar Cost Averaging) platform — the primary
transaction type is Purchase.

Typical Swan export columns:
  Date, Type, Amount (BTC), Price (USD), Total (USD), Fee (USD), Status

Transaction types mapped:
  Purchase    -> Trade  (buy BTC, sell USD)
  Withdrawal  -> Withdrawal
  Deposit     -> Deposit (BTC received from external wallet)
  USD Deposit -> skipped (no BTC involved)

Pending and Failed status rows are skipped.
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
class SwanImporter(BaseImporter):
    """Parser for Swan Bitcoin deposits & purchases CSV exports."""

    name = "Swan"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Swan Bitcoin deposits & purchases export"
    expected_columns = [
        "Date", "Type", "Amount (BTC)", "Price (USD)", "Total (USD)", "Fee (USD)", "Status",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Swan Bitcoin export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Swan-specific: "amount (btc)" and "price (usd)" together
                return (
                    'amount (btc)' in header_lower and
                    'price (usd)' in header_lower and
                    'total (usd)' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Swan Bitcoin deposits & purchases CSV.

        Args:
            file_path: Path to CSV file
            wallet_name: Ignored for exchange parsers
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
        status = get('status').upper()
        btc_amount = _parse_number(get('amount (btc)'))
        total_usd = _parse_number(get('total (usd)'))
        fee_usd = _parse_number(get('fee (usd)'))

        # Skip pending or failed transactions
        if status in ('PENDING', 'FAILED'):
            return None

        if not date or not tx_type:
            return None

        if tx_type == 'PURCHASE':
            # DCA purchase: buy BTC with USD
            # Total (USD) is the full amount deducted (includes fee)
            return {
                'trans_type': 'Trade',
                'created_date': date,
                'exchange': 'Swan',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': total_usd,
                'sell_curr': 'USD',
                'fee': fee_usd,
                'fee_curr': 'USD',
                'group': 'DCA',
                'comment': '',
            }

        elif tx_type == 'WITHDRAWAL':
            return {
                'trans_type': 'Withdrawal',
                'created_date': date,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': btc_amount,
                'sell_curr': 'BTC',
                'fee': fee_usd,
                'fee_curr': 'USD' if fee_usd > 0 else '',
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to),
            }

        elif tx_type == 'DEPOSIT':
            # BTC deposit from external source
            return {
                'trans_type': 'Deposit',
                'created_date': date,
                'exchange': 'Swan',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': '',
            }

        # USD Deposit and any other type — no BTC involved, skip
        return None

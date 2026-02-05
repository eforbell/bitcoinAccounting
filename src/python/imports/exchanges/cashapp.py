"""Cash App Bitcoin gain/loss CSV parser.

Cash App is Bitcoin-only — no asset filtering required. The "Gain/Loss"
CSV export contains both transaction history and cost basis information.

Key limitation: Cash App cannot determine cost basis for Bitcoin received
from external wallets.  Those Receive rows have an empty or $0 Cost Basis
field.  The parser emits a UserWarning for every such row so users know to
verify before tax filing.

Typical Cash App Gain/Loss CSV columns:
  Date, Transaction Type, Amount (BTC), Market Price ($),
  Cost Basis ($), Proceeds ($), Gain/Loss ($), Note

Transaction types mapped:
  Purchase  -> Trade  (buy BTC, sell USD)
  Sale      -> Trade  (sell BTC, buy USD)
  Send      -> Withdrawal
  Receive   -> Deposit  (warning when Cost Basis is zero / empty)
"""

from __future__ import annotations

import csv
import warnings
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
class CashAppImporter(BaseImporter):
    """Parser for Cash App Bitcoin gain/loss CSV exports."""

    name = "CashApp"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Cash App Bitcoin gain/loss export"
    expected_columns = [
        "Date", "Transaction Type", "Amount (BTC)", "Market Price ($)",
        "Cost Basis ($)", "Proceeds ($)", "Gain/Loss ($)", "Note",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Cash App gain/loss export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # "cost basis ($)" and "gain/loss ($)" together are Cash App-specific
                return (
                    'cost basis ($)' in header_lower and
                    'gain/loss ($)' in header_lower and
                    'amount (btc)' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Cash App Bitcoin gain/loss CSV.

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

        tx_type = get('transaction type').upper()
        date = get('date')
        btc_amount = _parse_number(get('amount (btc)'))
        market_price = _parse_number(get('market price ($)'))
        cost_basis = _parse_number(get('cost basis ($)'))
        proceeds = _parse_number(get('proceeds ($)'))
        note = get('note')

        if not date or not tx_type:
            return None

        if tx_type == 'PURCHASE':
            # Cost Basis is the USD actually charged; fall back to market calc
            usd_spent = cost_basis if cost_basis > 0 else btc_amount * market_price
            return {
                'trans_type': 'Trade',
                'created_date': date,
                'exchange': 'CashApp',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': usd_spent,
                'sell_curr': 'USD',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': note,
            }

        elif tx_type == 'SALE':
            # Proceeds is the USD received; fall back to market calc
            usd_received = proceeds if proceeds > 0 else btc_amount * market_price
            return {
                'trans_type': 'Trade',
                'created_date': date,
                'exchange': 'CashApp',
                'buy': usd_received,
                'buy_curr': 'USD',
                'sell': btc_amount,
                'sell_curr': 'BTC',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': note,
            }

        elif tx_type == 'SEND':
            return {
                'trans_type': 'Withdrawal',
                'created_date': date,
                'exchange': self._get_withdrawal_exchange(withdraw_to),
                'buy': 0.0,
                'buy_curr': '',
                'sell': btc_amount,
                'sell_curr': 'BTC',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': self._get_withdrawal_comment(withdraw_to, note),
            }

        elif tx_type == 'RECEIVE':
            comment = note
            # Warn when Cost Basis is zero / missing — likely an external transfer
            if cost_basis == 0.0:
                warnings.warn(
                    f"CashApp Receive on {date}: cost basis is $0 — "
                    "Bitcoin was likely transferred from an external wallet. "
                    "Verify cost basis before tax filing.",
                    UserWarning,
                    stacklevel=2,
                )
                basis_note = "Cost basis $0 - verify before tax filing"
                comment = f"{basis_note}; {note}" if note else basis_note
            return {
                'trans_type': 'Deposit',
                'created_date': date,
                'exchange': 'CashApp',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': 0.0,
                'sell_curr': '',
                'fee': 0.0,
                'fee_curr': '',
                'group': '',
                'comment': comment,
            }

        # Unknown type — skip
        return None

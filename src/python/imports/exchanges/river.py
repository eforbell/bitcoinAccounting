"""River Bitcoin exchange CSV parser.

River provides two export formats:

  Account Activity – full history (21 columns):
    Date, Reference Code, Transaction Type, Sent Amount, Sent Currency,
    Received Amount, Received Currency, Fee Amount, Fee Currency,
    Total Amount, Total Currency, Method, Source, Destination,
    Cost Basis, Cost Basis Currency, Bitcoin Price Amount,
    Bitcoin Price Currency, Transaction ID, Recurring, Tag

  Bitcoin Activity – BTC-only subset (8 columns):
    Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
    Fee Amount, Fee Currency, Tag

Transaction type mapping:

  Account Activity (via Transaction Type column):
    Buy              -> Trade  (buy BTC, sell USD)
    Send             -> Withdrawal
    Interest Payout  -> Interest Income
    Cash Deposit     -> skipped (USD-only, no BTC)

  Bitcoin Activity (inferred from Tag + sent/received pattern):
    Tag=Buy          -> Trade
    Tag=Interest     -> Interest Income
    empty tag + BTC sent -> Withdrawal
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register

# Columns present in Account Activity but absent from Bitcoin Activity.
# All three must appear for the file to be recognised as Account Activity.
_ACCOUNT_MARKERS = {'reference code', 'transaction type', 'bitcoin price amount'}

# All eight columns that define the Bitcoin Activity format.
_BTC_COLS = {
    'date', 'sent amount', 'sent currency', 'received amount',
    'received currency', 'fee amount', 'fee currency', 'tag',
}


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


def _detect_river_format(header_lower: set[str]) -> str | None:
    """Return ``'account'`` or ``'btc'`` when *header_lower* matches a River
    export, otherwise ``None``.

    Account Activity is checked first because its column set is a superset
    of Bitcoin Activity.
    """
    if _ACCOUNT_MARKERS.issubset(header_lower):
        return 'account'
    if _BTC_COLS.issubset(header_lower) and 'transaction type' not in header_lower:
        return 'btc'
    return None


@register
class RiverImporter(BaseImporter):
    """Parser for River Bitcoin exchange CSV exports.

    Supports both Account Activity and Bitcoin Activity formats,
    auto-detected from the CSV header.
    """

    name = "River"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "River Bitcoin export (Account Activity or Bitcoin Activity)"
    expected_columns = [
        "Date", "Sent Amount", "Sent Currency",
        "Received Amount", "Received Currency",
        "Fee Amount", "Fee Currency", "Tag",
    ]

    def detect(self, file_path: str) -> bool:
        """Return True when the file header matches either River format."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                return _detect_river_format(
                    {col.lower().strip() for col in header}
                ) is not None
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a River CSV, auto-detecting Account vs Bitcoin Activity."""
        transactions: list[dict[str, Any]] = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []

            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            col_map = {col.lower(): col for col in reader.fieldnames}
            fmt = _detect_river_format(set(col_map.keys()))

            if fmt is None:
                return [], []

            for row in reader:
                if fmt == 'account':
                    tx = self._parse_account_row(row, col_map, withdraw_to)
                else:  # fmt == 'btc'
                    tx = self._parse_btc_row(row, col_map, withdraw_to)
                if tx is not None:
                    transactions.append(tx)

        colnames = [
            'trans_type', 'created_date', 'exchange', 'buy', 'buy_curr',
            'sell', 'sell_curr', 'fee', 'fee_curr', 'group', 'comment',
        ]
        return colnames, transactions

    # ------------------------------------------------------------------
    # Account Activity format
    # ------------------------------------------------------------------

    def _parse_account_row(
        self,
        row: dict[str, str],
        col_map: dict[str, str],
        withdraw_to: str | None,
    ) -> dict[str, Any] | None:
        """Parse one Account Activity row.  Returns None for rows to skip."""

        def get(col: str) -> str:
            original = col_map.get(col.lower(), col)
            return (row.get(original) or '').strip()

        tx_type = get('Transaction Type')
        date    = get('Date')

        if not date or not tx_type:
            return None

        sent_curr = get('Sent Currency')
        recv_curr = get('Received Currency')

        # Drop rows that don't touch BTC (e.g. Cash Deposit)
        if sent_curr != 'BTC' and recv_curr != 'BTC':
            return None

        sent_amt  = _parse_number(get('Sent Amount'))
        recv_amt  = _parse_number(get('Received Amount'))
        fee_amt   = _parse_number(get('Fee Amount'))
        fee_curr  = get('Fee Currency')
        total_amt = _parse_number(get('Total Amount'))
        ref_code  = get('Reference Code')

        tx_upper = tx_type.upper()

        if tx_upper == 'BUY':
            return {
                'trans_type':   'Trade',
                'created_date': date,
                'exchange':     'River',
                'buy':          recv_amt,
                'buy_curr':     'BTC',
                'sell':         total_amt if total_amt > 0 else sent_amt + fee_amt,
                'sell_curr':    sent_curr,
                'fee':          fee_amt,
                'fee_curr':     fee_curr if fee_amt > 0 else '',
                'group':        '',
                'comment':      ref_code,
            }

        if tx_upper == 'SEND':
            return {
                'trans_type':   'Withdrawal',
                'created_date': date,
                'exchange':     self._get_withdrawal_exchange(withdraw_to),
                'buy':          0.0,
                'buy_curr':     '',
                'sell':         sent_amt,
                'sell_curr':    'BTC',
                'fee':          fee_amt,
                'fee_curr':     fee_curr if fee_amt > 0 else '',
                'group':        '',
                'comment':      self._get_withdrawal_comment(withdraw_to, ref_code),
            }

        if tx_upper == 'INTEREST PAYOUT':
            return {
                'trans_type':   'Interest Income',
                'created_date': date,
                'exchange':     'River',
                'buy':          recv_amt,
                'buy_curr':     'BTC',
                'sell':         0.0,
                'sell_curr':    '',
                'fee':          0.0,
                'fee_curr':     '',
                'group':        '',
                'comment':      ref_code,
            }

        return None  # Unrecognised Transaction Type

    # ------------------------------------------------------------------
    # Bitcoin Activity format
    # ------------------------------------------------------------------

    def _parse_btc_row(
        self,
        row: dict[str, str],
        col_map: dict[str, str],
        withdraw_to: str | None,
    ) -> dict[str, Any] | None:
        """Parse one Bitcoin Activity row.  Returns None for rows to skip."""

        def get(col: str) -> str:
            original = col_map.get(col.lower(), col)
            return (row.get(original) or '').strip()

        date      = get('Date')
        sent_amt  = _parse_number(get('Sent Amount'))
        sent_curr = get('Sent Currency')
        recv_amt  = _parse_number(get('Received Amount'))
        recv_curr = get('Received Currency')
        fee_amt   = _parse_number(get('Fee Amount'))
        fee_curr  = get('Fee Currency')
        tag       = get('Tag').upper()

        if not date:
            return None

        if tag == 'BUY':
            # sell = total out of pocket; add fee only when denominated in the
            # same currency as the amount sent (typically both USD).
            sell = sent_amt + (fee_amt if fee_curr == sent_curr else 0.0)
            return {
                'trans_type':   'Trade',
                'created_date': date,
                'exchange':     'River',
                'buy':          recv_amt,
                'buy_curr':     recv_curr,
                'sell':         sell,
                'sell_curr':    sent_curr,
                'fee':          fee_amt,
                'fee_curr':     fee_curr if fee_amt > 0 else '',
                'group':        '',
                'comment':      '',
            }

        if tag == 'INTEREST':
            return {
                'trans_type':   'Interest Income',
                'created_date': date,
                'exchange':     'River',
                'buy':          recv_amt,
                'buy_curr':     recv_curr,
                'sell':         0.0,
                'sell_curr':    '',
                'fee':          0.0,
                'fee_curr':     '',
                'group':        '',
                'comment':      '',
            }

        # Empty tag + outgoing BTC = on-chain withdrawal
        if tag == '' and sent_curr == 'BTC' and sent_amt > 0:
            return {
                'trans_type':   'Withdrawal',
                'created_date': date,
                'exchange':     self._get_withdrawal_exchange(withdraw_to),
                'buy':          0.0,
                'buy_curr':     '',
                'sell':         sent_amt,
                'sell_curr':    'BTC',
                'fee':          fee_amt,
                'fee_curr':     fee_curr if fee_amt > 0 else '',
                'group':        '',
                'comment':      self._get_withdrawal_comment(withdraw_to),
            }

        return None  # Unrecognised tag / pattern

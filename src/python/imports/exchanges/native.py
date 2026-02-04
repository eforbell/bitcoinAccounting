"""Native format parser for cryptoAccounting CSV exports.

Supports two column layouts:

  Clean (current):  trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr,
                    exchange, group, comment, created_date

  Legacy (export):  Type, Buy, Buy Cur., Sell, Sell Cur., Fee, Fee Cur.,
                    Exchange, Group, Comment, Date
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register

# lowercase column name → transaction dict key  (clean format)
_CLEAN_MAP: dict[str, str] = {
    'trans_type':   'trans_type',
    'buy':          'buy',
    'buy_curr':     'buy_curr',
    'sell':         'sell',
    'sell_curr':    'sell_curr',
    'fee':          'fee',
    'fee_curr':     'fee_curr',
    'exchange':     'exchange',
    'group':        'group',
    'comment':      'comment',
    'created_date': 'created_date',
}

# lowercase column name → transaction dict key  (legacy format)
_LEGACY_MAP: dict[str, str] = {
    'type':       'trans_type',
    'buy':        'buy',
    'buy cur.':   'buy_curr',
    'sell':       'sell',
    'sell cur.':  'sell_curr',
    'fee':        'fee',
    'fee cur.':   'fee_curr',
    'exchange':   'exchange',
    'group':      'group',
    'comment':    'comment',
    'date':       'created_date',
}


def _parse_number(value: str) -> float:
    """Parse a numeric string, returning 0.0 for empty/invalid values."""
    value = value.strip().lstrip('$').replace(',', '')
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _detect_format(fieldnames: list[str]) -> dict[str, str] | None:
    """Return the column map that matches the header, or None if neither matches.

    Clean format takes priority when both could match (unlikely but safe).
    """
    header_lower = {col.lower().strip() for col in fieldnames}
    if set(_CLEAN_MAP.keys()).issubset(header_lower):
        return _CLEAN_MAP
    if set(_LEGACY_MAP.keys()).issubset(header_lower):
        return _LEGACY_MAP
    return None


@register
class NativeImporter(BaseImporter):
    """Parser for cryptoAccounting's native CSV export format."""

    name = "Native"
    source_type = "native"
    file_patterns = ["*.csv"]
    description = "Native cryptoAccounting format (clean or legacy)"
    expected_columns = [
        "trans_type", "buy", "buy_curr", "sell", "sell_curr",
        "fee", "fee_curr", "exchange", "group", "comment", "created_date",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file matches either the clean or legacy native format."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                return _detect_format(header) is not None
        except (OSError, csv.Error):
            return False

    def parse(
        self, file_path: str, withdraw_to: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a native format CSV, auto-detecting clean vs legacy columns."""
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []

            # Strip whitespace so column matching is reliable
            reader.fieldnames = [name.strip() for name in reader.fieldnames]

            col_map = _detect_format(reader.fieldnames)
            if col_map is None:
                return [], []

            # Build mapping: original CSV column name → transaction dict key
            lower_to_original = {name.lower(): name for name in reader.fieldnames}
            field_mapping: dict[str, str] = {}
            for lower_col, tx_field in col_map.items():
                if lower_col in lower_to_original:
                    field_mapping[lower_to_original[lower_col]] = tx_field

            transactions: list[dict[str, Any]] = []
            for row in reader:
                tx = _map_row(row, field_mapping)
                if tx is not None:
                    transactions.append(tx)

        colnames = list(_CLEAN_MAP.values())
        return colnames, transactions


def _map_row(row: dict[str, str], field_mapping: dict[str, str]) -> dict[str, Any] | None:
    """Convert one CSV row to a transaction dict. Returns None for empty rows."""
    raw: dict[str, str] = {}
    for col_name, tx_field in field_mapping.items():
        raw[tx_field] = (row.get(col_name) or '').strip()

    if not raw.get('trans_type'):
        return None

    return {
        'trans_type':   raw.get('trans_type', ''),
        'created_date': raw.get('created_date', ''),
        'exchange':     raw.get('exchange', ''),
        'buy':          _parse_number(raw.get('buy', '')),
        'buy_curr':     raw.get('buy_curr', ''),
        'sell':         _parse_number(raw.get('sell', '')),
        'sell_curr':    raw.get('sell_curr', ''),
        'fee':          _parse_number(raw.get('fee', '')),
        'fee_curr':     raw.get('fee_curr', ''),
        'group':        raw.get('group', ''),
        'comment':      raw.get('comment', ''),
    }

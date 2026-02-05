"""Kraken ledger CSV parser.

Parses the Kraken ledger export format which has a unique structure:
- Each trade appears as TWO rows with the same refid
- One row has positive amount (asset received)
- One row has negative amount (asset spent)
- Deposits/withdrawals/staking are single rows

Columns: txid, refid, time, type, subtype, aclass, asset, amount, fee, balance

Asset naming quirks:
- XXBT, XBT -> BTC
- ZUSD, USD -> USD
- XXDG -> DOGE, etc.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter
from imports.registry import register


# Kraken asset name normalization
_ASSET_MAP = {
    'xxbt': 'BTC',
    'xbt': 'BTC',
    'zusd': 'USD',
    'usd': 'USD',
    'zeur': 'EUR',
    'eur': 'EUR',
    'usdc': 'USDC',
    'usdt': 'USDT',
}


def _normalize_asset(asset: str) -> str:
    """Normalize Kraken asset names to standard symbols."""
    asset_lower = asset.lower().strip()
    return _ASSET_MAP.get(asset_lower, asset.upper())


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


def _is_btc_related(asset: str) -> bool:
    """Check if asset is BTC (handles Kraken naming)."""
    return _normalize_asset(asset) == 'BTC'


@register
class KrakenImporter(BaseImporter):
    """Parser for Kraken ledger CSV exports."""

    name = "Kraken"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Kraken ledger export"
    expected_columns = [
        "txid", "refid", "time", "type", "subtype",
        "aclass", "asset", "amount", "fee", "balance",
    ]

    def detect(self, file_path: str) -> bool:
        """Check if file appears to be a Kraken ledger export."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False
                header_lower = {col.lower().strip() for col in header}
                # Kraken-specific: has refid and aclass columns
                return (
                    'refid' in header_lower and
                    'aclass' in header_lower and
                    'txid' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Kraken ledger CSV.

        The key complexity is trade pair matching:
        1. Group all rows by refid
        2. For trade type, combine the two legs (buy + sell) into one transaction
        3. Handle deposits, withdrawals, staking as single-row transactions

        Args:
            file_path: Path to CSV file
            wallet_name: Ignored for exchange parsers
            withdraw_to: Wallet name for withdrawal destinations

        Returns:
            Tuple of (column_names, transactions)
        """
        # First pass: group all rows by refid
        rows_by_refid: dict[str, list[dict[str, str]]] = defaultdict(list)

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

                refid = get('refid')
                if refid:
                    # Store the row with normalized access
                    rows_by_refid[refid].append({
                        'txid': get('txid'),
                        'refid': refid,
                        'time': get('time'),
                        'type': get('type'),
                        'subtype': get('subtype'),
                        'aclass': get('aclass'),
                        'asset': get('asset'),
                        'amount': get('amount'),
                        'fee': get('fee'),
                        'balance': get('balance'),
                    })

        # Second pass: process each refid group
        transactions: list[dict[str, Any]] = []

        for refid, rows in rows_by_refid.items():
            if not rows:
                continue

            tx_type = rows[0]['type'].lower()

            if tx_type == 'trade':
                tx = self._process_trade(rows)
                if tx is not None:
                    transactions.append(tx)

            elif tx_type == 'deposit':
                tx = self._process_deposit(rows)
                if tx is not None:
                    transactions.append(tx)

            elif tx_type == 'withdrawal':
                tx = self._process_withdrawal(rows, withdraw_to)
                if tx is not None:
                    transactions.append(tx)

            elif tx_type in ('staking', 'reward', 'dividend'):
                tx = self._process_staking(rows)
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
        """Process trade rows (usually 2 rows with same refid).

        In a trade:
        - Positive amount = asset received (buy leg)
        - Negative amount = asset spent (sell leg)
        - Fee may be on either or both legs
        """
        if len(rows) < 2:
            # Incomplete trade pair - skip
            return None

        buy_leg = None
        sell_leg = None
        total_fee = 0.0
        fee_currency = ''

        for row in rows:
            amount = _parse_number(row['amount'])
            fee = _parse_number(row['fee'])
            asset = row['asset']

            if fee > 0:
                total_fee += fee
                fee_currency = _normalize_asset(asset)

            if amount > 0:
                buy_leg = {
                    'asset': _normalize_asset(asset),
                    'amount': amount,
                }
            elif amount < 0:
                sell_leg = {
                    'asset': _normalize_asset(asset),
                    'amount': abs(amount),
                }

        if buy_leg is None or sell_leg is None:
            # Can't determine trade structure
            return None

        # Filter: only include if BTC is involved
        if buy_leg['asset'] != 'BTC' and sell_leg['asset'] != 'BTC':
            return None

        # Use timestamp from first row
        timestamp = rows[0]['time']
        refid = rows[0]['refid']

        return {
            'trans_type': 'Trade',
            'created_date': timestamp,
            'exchange': 'Kraken',
            'buy': buy_leg['amount'],
            'buy_curr': buy_leg['asset'],
            'sell': sell_leg['amount'],
            'sell_curr': sell_leg['asset'],
            'fee': total_fee,
            'fee_curr': fee_currency,
            'group': '',
            'comment': f'refid:{refid}',
        }

    def _process_deposit(self, rows: list[dict[str, str]]) -> dict[str, Any] | None:
        """Process deposit row(s)."""
        # Usually single row for deposit
        row = rows[0]
        asset = _normalize_asset(row['asset'])

        # Only BTC deposits
        if asset != 'BTC':
            return None

        amount = _parse_number(row['amount'])
        fee = _parse_number(row['fee'])
        timestamp = row['time']
        refid = row['refid']

        return {
            'trans_type': 'Deposit',
            'created_date': timestamp,
            'exchange': 'Kraken',
            'buy': amount,
            'buy_curr': asset,
            'sell': 0.0,
            'sell_curr': '',
            'fee': fee,
            'fee_curr': asset if fee > 0 else '',
            'group': '',
            'comment': f'refid:{refid}',
        }

    def _process_withdrawal(
        self, rows: list[dict[str, str]], withdraw_to: str | None
    ) -> dict[str, Any] | None:
        """Process withdrawal row(s)."""
        row = rows[0]
        asset = _normalize_asset(row['asset'])

        # Only BTC withdrawals
        if asset != 'BTC':
            return None

        # Withdrawal amount is negative in Kraken
        amount = abs(_parse_number(row['amount']))
        fee = _parse_number(row['fee'])
        timestamp = row['time']
        refid = row['refid']

        base_comment = f'refid:{refid}'

        return {
            'trans_type': 'Withdrawal',
            'created_date': timestamp,
            'exchange': self._get_withdrawal_exchange(withdraw_to),
            'buy': 0.0,
            'buy_curr': '',
            'sell': amount,
            'sell_curr': asset,
            'fee': fee,
            'fee_curr': asset if fee > 0 else '',
            'group': '',
            'comment': self._get_withdrawal_comment(withdraw_to, base_comment),
        }

    def _process_staking(self, rows: list[dict[str, str]]) -> dict[str, Any] | None:
        """Process staking/reward row(s)."""
        row = rows[0]
        asset = _normalize_asset(row['asset'])

        # Only BTC staking rewards
        if asset != 'BTC':
            return None

        amount = _parse_number(row['amount'])
        timestamp = row['time']
        refid = row['refid']
        subtype = row.get('subtype', '')

        return {
            'trans_type': 'Interest Income',
            'created_date': timestamp,
            'exchange': 'Kraken',
            'buy': amount,
            'buy_curr': asset,
            'sell': 0.0,
            'sell_curr': '',
            'fee': 0.0,
            'fee_curr': '',
            'group': '',
            'comment': f'{subtype} refid:{refid}'.strip(),
        }

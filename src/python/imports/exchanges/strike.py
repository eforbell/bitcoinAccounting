"""Strike transaction history CSV parser.

Strike is a Bitcoin and USD exchange — supports fiat deposits and USD sends.

Real Strike 'All Transactions' export columns:
  Reference, Date & Time (UTC), Transaction Type, Amount USD, Fee USD,
  Amount BTC, Fee BTC, BTC Price, Cost Basis (USD), Destination, Description,
  Transaction Hash, Note

Transaction types mapped:
  Purchase  -> Trade  (buy BTC, sell USD)
  Deposit   -> Deposit (USD in) or Withdrawal (deposit reversal)
  Send      -> Withdrawal (on-chain BTC, Lightning BTC, or Lightning USD)
  Receive   -> Deposit (BTC in)
"""

from __future__ import annotations

import csv
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from imports.base import BaseImporter, is_fiat
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


def _parse_strike_date(date_str: str) -> str:
    """Convert Strike date format to standard format.

    Strike uses 'Mar 15 2024 14:30:22', convert to 'YYYY-MM-DD HH:MM:SS'.
    """
    if not date_str:
        return ''
    try:
        # Parse Strike format: 'Mar 15 2024 14:30:22'
        dt = datetime.strptime(date_str.strip(), '%b %d %Y %H:%M:%S')
        # Return as standard format
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        # If parsing fails, return original
        return date_str


@register
class StrikeImporter(BaseImporter):
    """Parser for Strike transaction history CSV exports."""

    name = "Strike"
    source_type = "exchange"
    file_patterns = ["*.csv"]
    description = "Strike 'All Transactions' export"
    expected_columns = [
        "Date & Time (UTC)", "Transaction Type", "Amount USD", "Amount BTC",
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
                # Strike real format: 'amount btc', 'amount usd', 'transaction type'
                return (
                    'amount btc' in header_lower and
                    'amount usd' in header_lower and
                    'transaction type' in header_lower
                )
        except (OSError, csv.Error, UnicodeDecodeError):
            return False

    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a Strike transaction history CSV.

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

        # Map new column names
        tx_type = get('transaction type').upper()
        date = _parse_strike_date(get('date & time (utc)'))
        btc_amount = _parse_number(get('amount btc'))
        usd_amount = _parse_number(get('amount usd'))
        description = get('description')
        destination = get('destination')
        tx_hash = get('transaction hash')

        # Fee columns (may be negative in CSV, use abs())
        fee_usd = abs(_parse_number(get('fee usd')))
        fee_btc = abs(_parse_number(get('fee btc')))

        if not date or not tx_type:
            return None

        if tx_type == 'PURCHASE':
            # Buy BTC with USD — usd_amount is negative (cost + fee)
            return {
                'trans_type': 'Trade',
                'created_date': date,
                'exchange': 'Strike',
                'buy': btc_amount,
                'buy_curr': 'BTC',
                'sell': abs(usd_amount),  # Negative in CSV
                'sell_curr': 'USD',
                'fee': fee_usd,
                'fee_curr': 'USD' if fee_usd > 0 else '',
                'group': '',
                'comment': description,
            }

        elif tx_type == 'DEPOSIT':
            # USD deposit or deposit reversal
            if usd_amount < 0 and 'reversal' in description.lower():
                # Deposit reversal — USD withdrawn from account
                return {
                    'trans_type': 'Withdrawal',
                    'created_date': date,
                    'exchange': 'Strike',
                    'buy': 0.0,
                    'buy_curr': '',
                    'sell': abs(usd_amount),
                    'sell_curr': 'USD',
                    'fee': 0.0,
                    'fee_curr': '',
                    'group': '',
                    'comment': f'Deposit reversal: {description}',
                }
            elif usd_amount > 0:
                # Normal USD deposit
                return {
                    'trans_type': 'Deposit',
                    'created_date': date,
                    'exchange': 'Strike',
                    'buy': usd_amount,
                    'buy_curr': 'USD',
                    'sell': 0.0,
                    'sell_curr': '',
                    'fee': 0.0,
                    'fee_curr': '',
                    'group': '',
                    'comment': description,
                }
            # Skip zero or negative deposits without reversal flag
            return None

        elif tx_type == 'SEND':
            # Determine send type based on destination and amounts
            is_lightning = destination.startswith('lnbc')
            is_onchain_btc = destination.startswith(('bc1', '1', '3'))

            if btc_amount != 0 and is_onchain_btc:
                # On-chain BTC send
                comment_parts = [description] if description else []
                if destination:
                    comment_parts.append(f'Destination: {destination}')
                if tx_hash:
                    comment_parts.append(f'TxHash: {tx_hash}')

                return {
                    'trans_type': 'Withdrawal',
                    'created_date': date,
                    'exchange': self._get_withdrawal_exchange(withdraw_to),
                    'buy': 0.0,
                    'buy_curr': '',
                    'sell': abs(btc_amount),
                    'sell_curr': 'BTC',
                    'fee': fee_btc if fee_btc > 0 else fee_usd,
                    'fee_curr': 'BTC' if fee_btc > 0 else ('USD' if fee_usd > 0 else ''),
                    'group': '',
                    'comment': ' | '.join(comment_parts),
                }

            elif btc_amount != 0 and is_lightning:
                # Lightning BTC send — different target than on-chain
                target = self._get_lightning_btc_target(withdraw_to)
                comment_parts = [description] if description else []
                if destination:
                    comment_parts.append(f'Lightning: {destination}')

                return {
                    'trans_type': 'Withdrawal',
                    'created_date': date,
                    'exchange': target,
                    'buy': 0.0,
                    'buy_curr': '',
                    'sell': abs(btc_amount),
                    'sell_curr': 'BTC',
                    'fee': fee_btc if fee_btc > 0 else fee_usd,
                    'fee_curr': 'BTC' if fee_btc > 0 else ('USD' if fee_usd > 0 else ''),
                    'group': '',
                    'comment': ' | '.join(comment_parts),
                }

            elif usd_amount != 0 and is_lightning:
                # Lightning USD send — pure fiat debit, no BTC
                comment_parts = [description] if description else []
                if destination:
                    comment_parts.append(f'Lightning USD: {destination}')

                return {
                    'trans_type': 'Withdrawal',
                    'created_date': date,
                    'exchange': 'Strike',  # USD stays at Strike
                    'buy': 0.0,
                    'buy_curr': '',
                    'sell': abs(usd_amount),
                    'sell_curr': 'USD',
                    'fee': fee_usd,
                    'fee_curr': 'USD' if fee_usd > 0 else '',
                    'group': '',
                    'comment': ' | '.join(comment_parts),
                }

            # Unknown send type — skip
            return None

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

    def _get_lightning_btc_target(self, withdraw_to: str | None) -> str:
        """Get the target wallet for Lightning BTC sends.

        Lightning and on-chain BTC require different wallets, so we append
        '-Lightning' to the withdraw_to name. If no withdraw_to is specified,
        defaults to 'Strike-Lightning'.

        Args:
            withdraw_to: User-specified on-chain withdrawal destination, or None

        Returns:
            str: Lightning wallet name (withdraw_to-Lightning or Strike-Lightning)
        """
        if withdraw_to:
            return f"{withdraw_to}-Lightning"
        return "Strike-Lightning"

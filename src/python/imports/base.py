"""Base importer class for CSV transaction imports.

This module defines the abstract base class that all import parsers must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class BaseImporter(ABC):
    """Abstract base class for transaction importers.

    All exchange and wallet importers must inherit from this class and implement
    the required methods.

    Class Attributes:
        name: Human-readable name (e.g., 'Coinbase')
        source_type: Category ('exchange', 'wallet', or 'native')
        file_patterns: List of glob patterns for file matching (e.g., ['*.csv'])
        description: Brief description for --list output
        expected_columns: List of expected column names (for validation hints)
    """

    name: str = "Unknown"
    source_type: str = "exchange"
    file_patterns: list[str] = ["*.csv"]
    description: str = "No description"
    expected_columns: list[str] = []

    @abstractmethod
    def parse(
        self,
        file_path: str,
        wallet_name: str | None = None,
        withdraw_to: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Parse a CSV file and return transactions.

        Args:
            file_path: Path to the CSV file to parse
            wallet_name: Wallet name for deposits (required for wallet parsers).
                        For exchange parsers, this parameter is ignored.
            withdraw_to: Optional wallet name for withdrawal destinations.
                        If None, uses "{self.name}-Withdrawal" as placeholder.

        Returns:
            tuple: (column_names, transactions)
                - column_names: List of column names from the source
                - transactions: List of transaction dicts ready for import_transactions()

        Transaction dict format:
            {
                'trans_type': 'Trade' | 'Deposit' | 'Withdrawal' | 'Interest Income' | 'Mining',
                'created_date': '2024-01-15 10:30:00',
                'exchange': 'Coinbase',
                'buy': 0.01234,           # For buys/deposits
                'buy_curr': 'BTC',
                'sell': 500.00,           # For sells/withdrawals
                'sell_curr': 'USD',
                'fee': 2.50,              # Optional
                'fee_curr': 'USD',        # Optional
                'group': None,            # Optional grouping
                'comment': '',            # Optional note
            }
        """
        pass

    def detect(self, file_path: str) -> bool:
        """Check if this parser can handle the given file.

        Default implementation reads the header row and checks if expected columns
        are present. Subclasses can override for more sophisticated detection.

        Args:
            file_path: Path to the CSV file to check

        Returns:
            bool: True if this parser can likely handle the file
        """
        if not self.expected_columns:
            return False

        try:
            import csv

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return False

                # Check if all expected columns are present (case-insensitive)
                header_lower = [col.lower().strip() for col in header]
                expected_lower = [col.lower().strip() for col in self.expected_columns]

                # Require at least 80% of expected columns to match
                matches = sum(1 for col in expected_lower if col in header_lower)
                return matches >= len(expected_lower) * 0.8

        except (OSError, csv.Error):
            return False

    def get_format_help(self) -> str:
        """Get help text describing the expected CSV format.

        Returns:
            str: Multi-line help text for --format output
        """
        lines = [
            f"Format: {self.name}",
            f"Type: {self.source_type}",
            f"Description: {self.description}",
            "",
            "Expected columns:",
        ]

        if self.expected_columns:
            for col in self.expected_columns:
                lines.append(f"  - {col}")
        else:
            lines.append("  (format auto-detected)")

        return "\n".join(lines)

    def _get_withdrawal_exchange(self, withdraw_to: str | None) -> str:
        """Get the exchange name to use for withdrawal transactions.

        Args:
            withdraw_to: User-specified withdrawal destination, or None

        Returns:
            str: Exchange name to use for withdrawals
        """
        return withdraw_to if withdraw_to else f"{self.name}-Withdrawal"

    def _get_withdrawal_comment(self, withdraw_to: str | None, existing_comment: str = "") -> str:
        """Get the comment to add for withdrawal transactions.

        Args:
            withdraw_to: User-specified withdrawal destination, or None
            existing_comment: Any existing comment to preserve

        Returns:
            str: Comment with review note if needed
        """
        if withdraw_to:
            return existing_comment

        review_note = "Review: Verify destination wallet"
        if existing_comment:
            return f"{existing_comment}; {review_note}"
        return review_note

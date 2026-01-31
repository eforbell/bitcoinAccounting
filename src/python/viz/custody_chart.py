"""Custody Chart - Bitcoin holdings by custody type over time.

Stacked area chart showing self-custodied, custodial, and multisig holdings.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.figure import Figure

try:
    # When imported from tests
    from src.python.db.backend import DatabaseBackend
    from src.python.viz.config import VizConfig
except ModuleNotFoundError:
    # When running from CLI with sys.path manipulation
    from db.backend import DatabaseBackend  # type: ignore[import]
    from viz.config import VizConfig  # type: ignore[import]


class CustodyChart:
    """Generate custody breakdown chart showing holdings by custody type."""

    # Color scheme for custody types
    CUSTODY_COLORS = {
        "self-custodied": "#34C759",  # Green (sovereignty)
        "custodial": "#FF9500",       # Orange (risk/convenience)
        "multisig": "#007AFF",         # Blue (collaborative security)
        "unknown": "#8E8E93",          # Gray (no wallet metadata)
    }

    def __init__(self, backend: DatabaseBackend, config: VizConfig) -> None:
        """Initialize custody chart generator.

        Args:
            backend: Database backend for querying transaction data
            config: Visualization configuration
        """
        self.backend = backend
        self.config = config

    def generate(self) -> Path:
        """Generate custody breakdown chart and save to file.

        Returns:
            Path to generated PNG file

        Raises:
            ValueError: If no transaction data available
            RuntimeError: If chart generation fails
        """
        # Resolve date range
        start_date, end_date = self._resolve_date_range()

        # Get custody data over time
        custody_data = self._get_custody_balances(start_date, end_date)

        if not custody_data:
            raise ValueError(
                "No Bitcoin transactions found. Start stacking sats!"
            )

        # Create the plot
        fig = self._create_plot(custody_data, start_date, end_date)

        # Save to file
        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=self.config.dpi, bbox_inches="tight")
        plt.close(fig)

        return output_path

    def _resolve_date_range(self) -> tuple[datetime, datetime]:
        """Resolve date range from config.

        Returns:
            Tuple of (start_date, end_date)
        """
        if isinstance(self.config.date_range, tuple):
            return self.config.date_range

        # Get min/max dates from ledger
        result = self.backend.execute_one(
            """
            SELECT MIN(createddate) as min_date
            FROM ledger
            WHERE (buy_curr = 'BTC' OR sell_curr = 'BTC')
            """
        )

        if not result or not result.get("min_date"):
            # Default to last year if no trades
            end = datetime.now()
            start = datetime(end.year - 1, 1, 1)
            return start, end

        min_date_str = result["min_date"]
        if isinstance(min_date_str, str):
            min_date = datetime.fromisoformat(min_date_str.replace("Z", "+00:00"))
        else:
            min_date = min_date_str

        max_date = datetime.now()

        # Apply preset ranges
        if self.config.date_range == "ytd":
            start = datetime(max_date.year, 1, 1)
            end = max_date
        elif self.config.date_range == "1y":
            start = datetime(max_date.year - 1, max_date.month, max_date.day)
            end = max_date
        elif self.config.date_range == "5y":
            start = datetime(max_date.year - 5, max_date.month, max_date.day)
            end = max_date
        else:  # "all"
            start = min_date
            end = max_date

        return start, end

    def _get_custody_balances(
        self, start_date: datetime, end_date: datetime
    ) -> list[dict[str, Any]]:
        """Get BTC balance by custody type over time, smoothed by day.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with 'date' and balances by custody type
        """
        # Get all BTC value changes from ledger (buys - sells per wallet)
        query = """
            SELECT
                createddate as date,
                COALESCE(CASE WHEN buy_curr = 'BTC' THEN buy ELSE 0 END, 0) -
                COALESCE(CASE WHEN sell_curr = 'BTC' THEN sell ELSE 0 END, 0) as btc_change,
                exchange
            FROM ledger
            WHERE buy_curr = 'BTC' OR sell_curr = 'BTC'
            ORDER BY createddate ASC
        """

        transactions = self.backend.execute(query)

        # Get wallet custody information
        wallets = self._get_wallet_custody_map()

        # Group transactions by day and wallet to smooth the data
        from collections import defaultdict
        daily_changes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for txn in transactions:
            date = txn["date"]
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))

            # Skip transactions outside date range
            if date < start_date or date > end_date:
                continue

            # Get just the date (no time) for grouping
            date_key = date.date().isoformat()
            exchange = txn["exchange"]
            btc_change = txn["btc_change"]

            # Determine custody type
            custody_type = wallets.get(exchange, "unknown")

            # Accumulate changes for this day and custody type
            daily_changes[date_key][custody_type] += btc_change

        # Build daily balance snapshots
        custody_balances: dict[str, float] = {
            "self-custodied": 0.0,
            "custodial": 0.0,
            "multisig": 0.0,
            "unknown": 0.0,
        }

        balance_data = []

        # Add starting point
        balance_data.append({
            "date": start_date,
            **custody_balances.copy()
        })

        # Process each day chronologically
        for date_key in sorted(daily_changes.keys()):
            # Apply all changes for this day
            for custody_type, change in daily_changes[date_key].items():
                custody_balances[custody_type] += change

            # Record end-of-day balance
            day_date = datetime.fromisoformat(date_key)
            balance_data.append({
                "date": day_date,
                **custody_balances.copy()
            })

        # Add endpoint
        if balance_data:
            balance_data.append({
                "date": end_date,
                **custody_balances.copy()
            })

        return balance_data

    def _get_wallet_custody_map(self) -> dict[str, str]:
        """Get mapping of wallet/exchange IDs to custody types.

        Returns:
            Dict mapping wallet_id to custody type
        """
        # Check if wallets table exists
        try:
            wallets = self.backend.execute(
                """
                SELECT wallet_id, custody
                FROM wallets
                """
            )

            # Build mapping
            wallet_map = {}
            for wallet in wallets:
                wallet_id = wallet["wallet_id"]
                custody = wallet["custody"]
                # Normalize custody type
                if custody.lower() in ["self-custodied", "self", "cold", "hardware", "hot"]:
                    wallet_map[wallet_id] = "self-custodied"
                elif custody.lower() in ["custodial", "exchange", "third-party"]:
                    wallet_map[wallet_id] = "custodial"
                elif custody.lower() in ["multisig", "multi-sig", "collaborative"]:
                    wallet_map[wallet_id] = "multisig"
                else:
                    wallet_map[wallet_id] = "unknown"

            return wallet_map

        except Exception:
            # Wallets table doesn't exist or query failed
            return {}

    def _create_plot(
        self,
        balance_data: list[dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> Figure:
        """Create the custody breakdown chart figure.

        Args:
            balance_data: List of balance snapshots by custody type
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # Extract dates and balances by custody type
        dates = [point["date"] for point in balance_data]

        custody_types = ["self-custodied", "multisig", "custodial", "unknown"]
        balances_by_type = {
            custody_type: [point[custody_type] for point in balance_data]
            for custody_type in custody_types
        }

        # Calculate current totals for each custody type
        current_totals = {
            custody_type: balances_by_type[custody_type][-1]
            for custody_type in custody_types
        }

        # Filter out custody types with zero balance
        active_custody_types = [
            ct for ct in custody_types
            if current_totals[ct] > 0.00000001  # Ignore floating point errors
        ]

        if not active_custody_types:
            raise ValueError("No Bitcoin balance found across any custody type")

        # Create stacked area chart
        # Stack from bottom: self-custodied, multisig, custodial, unknown
        ax.stackplot(
            dates,
            *[balances_by_type[ct] for ct in active_custody_types],
            labels=[
                f"{ct.replace('-', ' ').title()}: {current_totals[ct]:.8f} BTC"
                for ct in active_custody_types
            ],
            colors=[self.CUSTODY_COLORS[ct] for ct in active_custody_types],
            alpha=0.8,
        )

        # Configure axes
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("BTC Balance", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")

        # Add legend
        ax.legend(loc="upper left", fontsize=10)

        # Calculate self-sovereignty index
        total_balance = sum(current_totals.values())
        if total_balance > 0:
            self_custodied_pct = (
                current_totals["self-custodied"] / total_balance
            ) * 100
        else:
            self_custodied_pct = 0

        # Title with self-sovereignty index
        title = "Bitcoin Holdings by Custody Type"
        subtitle = f"Self-Sovereignty Index: {self_custodied_pct:.1f}% self-custodied"

        ax.set_title(f"{title}\n{subtitle}", fontsize=14, pad=20)

        # Format x-axis dates nicely
        fig.autofmt_xdate()

        return fig

    def _get_output_path(self) -> Path:
        """Get output file path for chart.

        Returns:
            Path to output PNG file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"btc_custody_{today}.png"
        return self.config.output_dir / filename

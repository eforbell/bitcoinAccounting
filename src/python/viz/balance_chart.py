"""Balance Chart - Bitcoin stack growth over time visualization.

Shows cumulative BTC balance as an area chart with milestone markers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
import warnings

import matplotlib.pyplot as plt
import pandas as pd

if TYPE_CHECKING:
    from matplotlib.figure import Figure

try:
    # When imported from tests
    from src.python.db.backend import DatabaseBackend
    from src.python.viz.config import VizConfig
    from src.python.db.queries import BalanceCalculator, TradeQuery
except ModuleNotFoundError:
    # When running from CLI with sys.path manipulation
    from db.backend import DatabaseBackend  # type: ignore[import]
    from viz.config import VizConfig  # type: ignore[import]
    from db.queries import BalanceCalculator, TradeQuery  # type: ignore[import]


class BalanceChart:
    """Generate balance growth chart showing Bitcoin stack over time."""

    def __init__(self, backend: DatabaseBackend, config: VizConfig) -> None:
        """Initialize balance chart generator.

        Args:
            backend: Database backend for querying transaction data
            config: Visualization configuration
        """
        self.backend = backend
        self.config = config
        self.trade_query = TradeQuery(backend)
        self.balance_calc = BalanceCalculator(backend)

    def generate(self) -> Path:
        """Generate balance chart and save to file.

        Returns:
            Path to generated PNG file

        Raises:
            ValueError: If no transaction data available
            RuntimeError: If chart generation fails
        """
        # Get all BTC transactions
        trades = self.trade_query.get_trades("BTC")

        if not trades:
            raise ValueError(
                "No Bitcoin transactions found. Start stacking sats!"
            )

        # Resolve date range
        start_date, end_date = self._resolve_date_range(trades)

        # Calculate cumulative balance over time
        balance_data = self._calculate_cumulative_balance(trades, start_date, end_date)

        if not balance_data:
            raise ValueError("No balance data available for date range")

        # Create the plot
        fig = self._create_plot(balance_data, start_date, end_date)

        # Save to file
        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=self.config.dpi, bbox_inches="tight")
        plt.close(fig)

        return output_path

    def _resolve_date_range(
        self, trades: list[dict[str, Any]]
    ) -> tuple[datetime, datetime]:
        """Resolve date range from config or trades.

        Args:
            trades: List of trade transactions

        Returns:
            Tuple of (start_date, end_date)
        """
        if isinstance(self.config.date_range, tuple):
            return self.config.date_range

        # Get min/max dates from trades (strip timezone for consistent comparison)
        dates = []
        for trade in trades:
            date = trade["date"]
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if hasattr(date, 'tzinfo') and date.tzinfo is not None:
                date = date.replace(tzinfo=None)
            dates.append(date)

        min_date = min(dates)
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

    def _calculate_cumulative_balance(
        self, trades: list[dict[str, Any]], start_date: datetime, end_date: datetime
    ) -> list[dict[str, Any]]:
        """Calculate cumulative balance at each transaction date.

        Args:
            trades: List of trade transactions
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with 'date' and 'balance' keys, sorted by date
        """
        balance_data = []
        cumulative_balance = 0.0

        # Sort trades by date
        sorted_trades = sorted(
            trades,
            key=lambda t: (
                t["date"]
                if isinstance(t["date"], datetime)
                else datetime.fromisoformat(t["date"].replace("Z", "+00:00"))
            ),
        )

        # Add starting point at balance 0
        balance_data.append({"date": start_date, "balance": 0.0})

        for trade in sorted_trades:
            date = trade["date"]
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if hasattr(date, 'tzinfo') and date.tzinfo is not None:
                date = date.replace(tzinfo=None)

            # Skip trades outside date range
            if date < start_date or date > end_date:
                continue

            # Update cumulative balance
            quantity = trade["to_quantity"]
            cumulative_balance += quantity

            balance_data.append({"date": date, "balance": cumulative_balance})

        # Add endpoint at current date with final balance
        if balance_data:
            final_balance = balance_data[-1]["balance"]
            balance_data.append({"date": end_date, "balance": final_balance})

        # Check for negative balance
        for point in balance_data:
            if point["balance"] < -0.00000001:  # Allow for floating point errors
                warnings.warn(
                    f"Negative balance detected ({point['balance']:.8f} BTC) "
                    f"on {point['date'].strftime('%Y-%m-%d')}. "
                    "This may indicate data errors.",
                    RuntimeWarning
                )

        return balance_data

    def _create_plot(
        self,
        balance_data: list[dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> Figure:
        """Create the balance chart figure.

        Args:
            balance_data: List of balance points with date and balance
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # Extract dates and balances
        dates = [point["date"] for point in balance_data]
        balances = [point["balance"] for point in balance_data]

        # Plot balance line with area fill
        ax.plot(
            dates,
            balances,
            color="#FF9500",
            linewidth=2.5,
            label="BTC Balance",
        )
        ax.fill_between(
            dates,
            balances,
            alpha=0.3,
            color="#FF9500",
            label="Accumulated BTC",
        )

        # Add milestone markers
        current_balance = balances[-1] if balances else 0
        milestones = self._calculate_milestones(current_balance)

        for milestone in milestones:
            if milestone <= current_balance and milestone > 0:
                ax.axhline(
                    y=milestone,
                    color="gray",
                    linestyle=":",
                    linewidth=1,
                    alpha=0.5,
                )
                # Add label on right side
                ax.text(
                    end_date,
                    milestone,
                    f" {milestone:.2f} BTC",
                    va="center",
                    ha="left",
                    fontsize=9,
                    color="gray",
                    alpha=0.7,
                )

        # Configure axes
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("BTC Balance", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")

        # Add legend
        ax.legend(loc="upper left", fontsize=10)

        # Title with current balance
        title = "Bitcoin Stack Growth Over Time"
        subtitle = f"Current Balance: {current_balance:.8f} BTC"

        ax.set_title(f"{title}\n{subtitle}", fontsize=14, pad=20)

        # Format x-axis dates nicely
        fig.autofmt_xdate()

        return fig

    def _calculate_milestones(self, max_balance: float) -> list[float]:
        """Calculate milestone markers for the chart.

        Args:
            max_balance: Maximum balance to show

        Returns:
            List of milestone values (e.g., 0.1, 1, 10 BTC)
        """
        if max_balance <= 0:
            return []

        milestones = []

        # Standard milestones
        standard = [0.01, 0.1, 0.5, 1, 2, 5, 10, 21, 50, 100]

        for milestone in standard:
            if milestone <= max_balance * 1.1:  # Show milestones up to 110% of max
                milestones.append(milestone)

        # If very high balance, add more milestones
        if max_balance > 100:
            next_milestone = 200
            while next_milestone <= max_balance * 1.1:
                milestones.append(float(next_milestone))
                next_milestone += 100

        return milestones

    def _get_output_path(self) -> Path:
        """Get output file path for chart.

        Returns:
            Path to output PNG file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"btc_balance_{today}.png"
        return self.config.output_dir / filename

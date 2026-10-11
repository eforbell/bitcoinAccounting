"""Balance Chart - Bitcoin stack growth over time visualization.

Shows cumulative BTC balance as an area chart with milestone markers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
import warnings

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.figure import Figure

from db.backend import DatabaseBackend
from viz.config import VizConfig
from viz.series import BTC_EPSILON, HoldingsSeries, holdings_series, resolve_window


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

    def generate(self) -> Path:
        """Generate balance chart and save to file.

        Returns:
            Path to generated PNG file

        Raises:
            ValueError: If no transaction data available
            RuntimeError: If chart generation fails
        """
        window = resolve_window(self.backend, self.config.date_range)
        series = holdings_series(self.backend, window)
        if not series.has_transactions:
            raise ValueError("No Bitcoin transactions found. Start stacking sats!")

        for point in series.points:
            if point.total < -BTC_EPSILON:
                warnings.warn(
                    f"Negative balance detected ({point.total:.8f} BTC) "
                    f"on {point.when.strftime('%Y-%m-%d')}. "
                    "This may indicate data errors.",
                    RuntimeWarning,
                )

        fig = self._create_plot(series)

        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=self.config.dpi, bbox_inches="tight")
        plt.close(fig)

        return output_path

    def _create_plot(self, series: HoldingsSeries) -> Figure:
        """Create the balance chart figure."""
        fig, ax = plt.subplots(figsize=(10, 6))

        dates = [point.when for point in series.points]
        balances = [point.total for point in series.points]

        ax.plot(
            dates,
            balances,
            color="#FF9500",
            linewidth=2.5,
            label="BTC Balance",
            drawstyle="steps-post",
        )
        ax.fill_between(
            dates,
            balances,
            alpha=0.3,
            color="#FF9500",
            label="Accumulated BTC",
            step="post",
        )

        current_balance = series.latest.total
        for milestone in self._calculate_milestones(current_balance):
            if 0 < milestone <= current_balance:
                ax.axhline(
                    y=milestone,
                    color="gray",
                    linestyle=":",
                    linewidth=1,
                    alpha=0.5,
                )
                ax.text(
                    series.window.end,
                    milestone,
                    f" {milestone:.2f} BTC",
                    va="center",
                    ha="left",
                    fontsize=9,
                    color="gray",
                    alpha=0.7,
                )

        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("BTC Balance", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")
        ax.legend(loc="upper left", fontsize=10)

        title = "Bitcoin Stack Growth Over Time"
        subtitle = f"Current Balance: {current_balance:.8f} BTC"
        ax.set_title(f"{title}\n{subtitle}", fontsize=14, pad=20)

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

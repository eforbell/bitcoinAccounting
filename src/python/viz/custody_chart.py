"""Custody Chart - Bitcoin holdings by custody type over time.

Stacked area chart showing self-custodied, custodial, and multisig holdings.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.figure import Figure

from db.backend import DatabaseBackend
from viz.config import VizConfig
from viz.series import (
    BTC_EPSILON,
    CUSTODY_TYPES,
    HoldingsSeries,
    holdings_series,
    resolve_window,
)


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
            ValueError: If no BTC is held at the end of the window
            RuntimeError: If chart generation fails
        """
        window = resolve_window(self.backend, self.config.date_range)
        series = holdings_series(self.backend, window)

        fig = self._create_plot(series)

        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=self.config.dpi, bbox_inches="tight")
        plt.close(fig)

        return output_path

    def _create_plot(self, series: HoldingsSeries) -> Figure:
        """Create the custody breakdown chart figure."""
        current = series.latest.by_custody
        active = [ct for ct in CUSTODY_TYPES if current[ct] > BTC_EPSILON]
        if not active:
            raise ValueError("No Bitcoin balance found across any custody type")

        fig, ax = plt.subplots(figsize=(10, 6))

        # Stack from bottom: self-custodied, multisig, custodial, unknown
        ax.stackplot(
            [point.when for point in series.points],
            *[[point.by_custody[ct] for point in series.points] for ct in active],
            labels=[
                f"{ct.replace('-', ' ').title()}: {current[ct]:.8f} BTC"
                for ct in active
            ],
            colors=[self.CUSTODY_COLORS[ct] for ct in active],
            alpha=0.8,
            step="post",
        )

        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("BTC Balance", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")
        ax.legend(loc="upper left", fontsize=10)

        self_custody_pct = series.self_custody_pct() or 0.0
        title = "Bitcoin Holdings by Custody Type"
        subtitle = (
            f"Self-Sovereignty Index: {self_custody_pct:.1f}% self-custodied "
            "(including multisig)"
        )
        ax.set_title(f"{title}\n{subtitle}", fontsize=14, pad=20)

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

"""Orange Plot - Personal Bitcoin accumulation visualization.

Saylor-style chart showing BTC purchases and sales overlaid on BTC-USD price history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

from db.backend import DatabaseBackend
from db.queries import TradeQuery
from viz.config import VizConfig
from viz.data_fetcher import PriceDataFetcher
from viz.series import (
    AccumulationSeries,
    PricePoint,
    TradePoint,
    accumulation_series,
    nearest_price,
    price_series,
    resolve_window,
)


class OrangePlot:
    """Generate Saylor-style orange plot showing Bitcoin accumulation strategy."""

    def __init__(self, backend: DatabaseBackend, config: VizConfig) -> None:
        """Initialize orange plot generator.

        Args:
            backend: Database backend for querying transaction data
            config: Visualization configuration
        """
        self.backend = backend
        self.config = config
        self.trade_query = TradeQuery(backend)
        self.price_fetcher = PriceDataFetcher()

    def generate(self) -> Path:
        """Generate orange plot and save to file.

        Returns:
            Path to generated PNG file

        Raises:
            ValueError: If no transaction data available
            RuntimeError: If chart generation fails
        """
        window = resolve_window(self.backend, self.config.date_range)
        series = accumulation_series(self.backend, window, self.trade_query)
        if not series.has_trades:
            raise ValueError("No Bitcoin transactions found. Start stacking sats!")

        prices = price_series(self.price_fetcher, window)

        fig = self._create_plot(prices, series)

        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=self.config.dpi, bbox_inches="tight")
        plt.close(fig)

        return output_path

    def _scatter_trades(
        self,
        ax: Axes,
        trades: list[TradePoint],
        prices: list[PricePoint],
        color: str,
        label: str,
    ) -> None:
        if not trades:
            return
        ax.scatter(
            [t.when for t in trades],
            # Trades without a USD price sit on the market price line.
            [
                t.unit_price_usd if t.unit_price_usd is not None else nearest_price(prices, t.when)
                for t in trades
            ],
            # Marker area proportional to BTC amount, scaled for visibility.
            s=[t.btc * 500 for t in trades],
            c=color,
            alpha=0.6,
            edgecolors="black",
            linewidth=0.5,
            label=label,
            zorder=5,
        )

    def _create_plot(self, prices: list[PricePoint], series: AccumulationSeries) -> Figure:
        """Create the orange plot figure."""
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.plot(
            [p.when for p in prices],
            [p.close_usd for p in prices],
            color="#FF9500",
            linewidth=2,
            label="BTC-USD Price",
        )

        self._scatter_trades(ax, series.purchases, prices, "#FF9500", "Purchases")
        self._scatter_trades(ax, series.sales, prices, "#34C759", "Sales")

        if self.config.include_cost_basis and series.basis:
            ax.plot(
                [b.when for b in series.basis],
                [b.average_cost_usd for b in series.basis],
                color="#007AFF",
                linewidth=2,
                linestyle="--",
                label="Cost Basis",
                alpha=0.7,
                drawstyle="steps-post",
            )

        if self.config.log_scale:
            ax.set_yscale("log")

        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("USD", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")
        ax.legend(loc="upper left", fontsize=10)

        summary = series.summary
        valuation = summary.valuation(prices[-1].close_usd)
        if valuation.unrealized_gain_pct is None:
            gain_text = "n/a"
        else:
            sign = "+" if valuation.unrealized_gain_pct >= 0 else ""
            gain_text = f"{sign}{valuation.unrealized_gain_pct:.1f}%"

        # Escape "$": two of them in one string switch matplotlib into mathtext.
        title = "Personal Orange Plot - Bitcoin Accumulation Strategy"
        subtitle = (
            f"Total Invested: \\${summary.invested_usd:,.2f} | "
            f"Current Value: \\${valuation.current_value_usd:,.2f} | "
            f"Unrealized Gain: {gain_text}"
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
        filename = f"btc_orange_plot_{today}.png"
        return self.config.output_dir / filename

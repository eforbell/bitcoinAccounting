"""Orange Plot - Personal Bitcoin accumulation visualization.

Saylor-style chart showing BTC purchases and sales overlaid on BTC-USD price history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import pandas as pd

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from src.python.db.backend import DatabaseBackend
    from src.python.viz.config import VizConfig

from src.python.db.queries import TradeQuery
from src.python.viz.data_fetcher import PriceDataFetcher


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
        # Fetch BTC-USD price history
        start_date, end_date = self._resolve_date_range()
        price_data = self.price_fetcher.fetch_btc_price_history(start_date, end_date)

        if price_data.empty:
            raise RuntimeError(
                f"No BTC-USD price data available for range {start_date} to {end_date}"
            )

        # Get trade cost data
        trades = self.trade_query.get_trade_cost("BTC", "USD")

        if not trades:
            raise ValueError(
                "No Bitcoin transactions found. Start stacking sats!"
            )

        # Separate purchases and sales
        purchases = [t for t in trades if t["quantity"] > 0]
        sales = [t for t in trades if t["quantity"] < 0]

        # Filter to date range
        purchases = self._filter_to_date_range(purchases, start_date, end_date)
        sales = self._filter_to_date_range(sales, start_date, end_date)

        # Calculate cost basis if requested
        cost_basis_data = None
        if self.config.include_cost_basis and purchases:
            cost_basis_data = self._calculate_running_cost_basis(purchases)

        # Create the plot
        fig = self._create_plot(
            price_data, purchases, sales, cost_basis_data, start_date, end_date
        )

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

        # For string presets, VizConfig validation ensures these are valid
        # We'll get the actual dates from the first/last trade
        trades = self.trade_query.get_trade_cost("BTC", "USD")
        if not trades:
            # Default to last year if no trades
            end = datetime.now()
            start = datetime(end.year - 1, 1, 1)
            return start, end

        # Get min/max dates from trades
        dates = []
        for trade in trades:
            date = trade["date"]
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))
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

    def _filter_to_date_range(
        self, trades: list[dict[str, Any]], start_date: datetime, end_date: datetime
    ) -> list[dict[str, Any]]:
        """Filter trades to specified date range.

        Args:
            trades: List of trade dicts
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Filtered list of trades
        """
        filtered = []
        for trade in trades:
            date = trade["date"]
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))

            if start_date <= date <= end_date:
                filtered.append(trade)

        return filtered

    def _calculate_running_cost_basis(
        self, purchases: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calculate running weighted average cost basis.

        Args:
            purchases: List of purchase trades (quantity > 0)

        Returns:
            List of dicts with 'date' and 'basis' keys
        """
        running_basis = []
        cumulative_cost = 0.0
        cumulative_btc = 0.0

        # Sort purchases by date
        sorted_purchases = sorted(
            purchases,
            key=lambda t: (
                t["date"]
                if isinstance(t["date"], datetime)
                else datetime.fromisoformat(t["date"].replace("Z", "+00:00"))
            ),
        )

        for purchase in sorted_purchases:
            # Skip purchases with missing price data
            if purchase["unit_cost"] is None:
                continue

            cumulative_cost += purchase["unit_cost"] * purchase["quantity"]
            cumulative_btc += purchase["quantity"]

            if cumulative_btc > 0:
                avg_basis = cumulative_cost / cumulative_btc
                date = purchase["date"]
                if isinstance(date, str):
                    date = datetime.fromisoformat(date.replace("Z", "+00:00"))

                running_basis.append({"date": date, "basis": avg_basis})

        return running_basis

    def _create_plot(
        self,
        price_data: pd.DataFrame,
        purchases: list[dict[str, Any]],
        sales: list[dict[str, Any]],
        cost_basis_data: list[dict[str, Any]] | None,
        start_date: datetime,
        end_date: datetime,
    ) -> Figure:
        """Create the orange plot figure.

        Args:
            price_data: BTC-USD price DataFrame with date index
            purchases: List of purchase trades
            sales: List of sale trades
            cost_basis_data: Optional running cost basis data
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot BTC-USD price line
        ax.plot(
            price_data.index,
            price_data["close"],
            color="#FF9500",
            linewidth=2,
            label="BTC-USD Price",
        )

        # Plot purchases as scatter
        if purchases:
            purchase_dates = []
            purchase_prices = []
            purchase_sizes = []

            for p in purchases:
                date = p["date"]
                if isinstance(date, str):
                    date = datetime.fromisoformat(date.replace("Z", "+00:00"))
                purchase_dates.append(date)

                # Get BTC-USD price on purchase date
                # Use unit_cost if available, otherwise interpolate from price_data
                if p["unit_cost"] is not None:
                    purchase_prices.append(p["unit_cost"])
                else:
                    # Find closest price in price_data
                    closest_price = self._get_closest_price(price_data, date)
                    purchase_prices.append(closest_price)

                # Size proportional to BTC amount (scale for visibility)
                purchase_sizes.append(p["quantity"] * 500)

            ax.scatter(
                purchase_dates,
                purchase_prices,
                s=purchase_sizes,
                c="#FF9500",
                alpha=0.6,
                edgecolors="black",
                linewidth=0.5,
                label="Purchases",
                zorder=5,
            )

        # Plot sales as scatter
        if sales:
            sale_dates = []
            sale_prices = []
            sale_sizes = []

            for s in sales:
                date = s["date"]
                if isinstance(date, str):
                    date = datetime.fromisoformat(date.replace("Z", "+00:00"))
                sale_dates.append(date)

                # Get BTC-USD price on sale date
                if s["unit_cost"] is not None:
                    sale_prices.append(abs(s["unit_cost"]))
                else:
                    closest_price = self._get_closest_price(price_data, date)
                    sale_prices.append(closest_price)

                # Size proportional to BTC amount (use absolute value)
                sale_sizes.append(abs(s["quantity"]) * 500)

            ax.scatter(
                sale_dates,
                sale_prices,
                s=sale_sizes,
                c="#34C759",
                alpha=0.6,
                edgecolors="black",
                linewidth=0.5,
                label="Sales",
                zorder=5,
            )

        # Plot cost basis line if requested
        if cost_basis_data:
            basis_dates = [d["date"] for d in cost_basis_data]
            basis_values = [d["basis"] for d in cost_basis_data]

            ax.plot(
                basis_dates,
                basis_values,
                color="#007AFF",
                linewidth=2,
                linestyle="--",
                label="Cost Basis",
                alpha=0.7,
            )

        # Configure axes
        if self.config.log_scale:
            ax.set_yscale("log")

        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("USD", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle=":")

        # Add legend
        ax.legend(loc="upper left", fontsize=10)

        # Calculate summary stats
        total_btc_purchased = sum(p["quantity"] for p in purchases)
        total_usd_invested = sum(
            p["total_cost"] for p in purchases if p["total_cost"] is not None
        )

        # Get current BTC price
        current_price = price_data["close"].iloc[-1] if not price_data.empty else 0
        current_value = total_btc_purchased * current_price

        # Calculate unrealized gain
        if total_usd_invested > 0:
            unrealized_gain_pct = (
                (current_value - total_usd_invested) / total_usd_invested
            ) * 100
            gain_sign = "+" if unrealized_gain_pct >= 0 else ""
        else:
            unrealized_gain_pct = 0
            gain_sign = ""

        # Title with summary
        title = "Personal Orange Plot - Bitcoin Accumulation Strategy"
        subtitle = (
            f"Total Invested: ${total_usd_invested:,.2f} | "
            f"Current Value: ${current_value:,.2f} | "
            f"Unrealized Gain: {gain_sign}{unrealized_gain_pct:.1f}%"
        )

        ax.set_title(f"{title}\n{subtitle}", fontsize=14, pad=20)

        # Format x-axis dates nicely
        fig.autofmt_xdate()

        return fig

    def _get_closest_price(
        self, price_data: pd.DataFrame, target_date: datetime
    ) -> float:
        """Get closest BTC-USD price to target date.

        Args:
            price_data: Price DataFrame with date index
            target_date: Target date

        Returns:
            Closest price (close value)
        """
        # Find nearest date in price_data
        if price_data.empty:
            return 0.0

        # Convert target_date to match index type
        idx = price_data.index.get_indexer([target_date], method="nearest")[0]
        return float(price_data["close"].iloc[idx])

    def _get_output_path(self) -> Path:
        """Get output file path for chart.

        Returns:
            Path to output PNG file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"btc_orange_plot_{today}.png"
        return self.config.output_dir / filename

"""Bitcoin price data fetching and caching using yfinance."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    import yfinance as yf
else:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        pd = None  # type: ignore[assignment]
        yf = None  # type: ignore[assignment]


class PriceDataFetcher:
    """Fetches and caches BTC-USD price history from Yahoo Finance.

    Uses yfinance to fetch historical Bitcoin price data and caches
    it locally to minimize API calls.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize the price data fetcher.

        Args:
            cache_dir: Directory for caching price data.
                      Defaults to ~/.bitcoinaccounting/cache/.
        """
        if pd is None or yf is None:
            raise ImportError(
                "yfinance and pandas are required for price data fetching. "
                "Install with: pip install yfinance pandas"
            )

        if cache_dir is None:
            cache_dir = Path.home() / '.bitcoinaccounting' / 'cache'

        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / 'btc_prices.parquet'

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_btc_price_history(
        self,
        start_date: str | datetime,
        end_date: str | datetime
    ) -> pd.DataFrame:
        """Fetch BTC-USD price history for the specified date range.

        Retrieves data from cache when available and only fetches new data
        from Yahoo Finance for dates not in the cache.

        Args:
            start_date: Start date (YYYY-MM-DD string or datetime)
            end_date: End date (YYYY-MM-DD string or datetime)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            Index is date (datetime). All rows sorted by date ascending.

        Raises:
            ValueError: If start_date > end_date or dates are invalid
            RuntimeError: If yfinance API fails and no cached data available
        """
        # Convert to datetime if needed
        if isinstance(start_date, str):
            start_dt = datetime.fromisoformat(start_date)
        else:
            start_dt = start_date

        if isinstance(end_date, str):
            end_dt = datetime.fromisoformat(end_date)
        else:
            end_dt = end_date

        # Validate date range
        if start_dt > end_dt:
            raise ValueError(
                f"start_date ({start_dt}) must be <= end_date ({end_dt})"
            )

        # Try to load cached data
        cached_df = self._load_cache()

        # Determine what dates we need to fetch
        if cached_df is not None and not cached_df.empty:
            # Filter cached data to requested range
            mask = (cached_df.index >= start_dt) & (cached_df.index <= end_dt)
            range_df = cached_df[mask]

            # Check if we have all the data we need
            if not range_df.empty:
                cache_start = range_df.index.min()
                cache_end = range_df.index.max()

                # If cache covers our range, return it
                if cache_start <= start_dt and cache_end >= end_dt:
                    return range_df

        # Need to fetch data from Yahoo Finance
        try:
            new_df = self._fetch_from_yfinance(start_dt, end_dt)

            # Merge with cache and save
            if cached_df is not None and not cached_df.empty:
                # Combine old and new data, removing duplicates
                combined_df = pd.concat([cached_df, new_df])
                combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                combined_df = combined_df.sort_index()
            else:
                combined_df = new_df

            # Save updated cache
            self._save_cache(combined_df)

            # Return just the requested range
            mask = (combined_df.index >= start_dt) & (combined_df.index <= end_dt)
            return combined_df[mask]

        except Exception as e:
            # If fetch failed but we have some cached data, use that with warning
            if cached_df is not None and not cached_df.empty:
                mask = (cached_df.index >= start_dt) & (cached_df.index <= end_dt)
                range_df = cached_df[mask]
                if not range_df.empty:
                    # Return cached data with a note
                    return range_df

            # No cached data and fetch failed - raise error
            raise RuntimeError(
                f"Failed to fetch BTC price data from Yahoo Finance: {e}. "
                f"No cached data available for the requested date range."
            ) from e

    def _fetch_from_yfinance(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """Fetch data from Yahoo Finance API.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with BTC-USD price data
        """
        ticker = yf.Ticker("BTC-USD")
        df = ticker.history(start=start_date, end=end_date)

        if df.empty:
            raise RuntimeError(
                f"No data returned from Yahoo Finance for BTC-USD "
                f"between {start_date} and {end_date}"
            )

        # Standardize column names (yfinance uses capitalized names)
        df.columns = [col.lower() for col in df.columns]

        # Keep only the columns we need
        needed_cols = ['open', 'high', 'low', 'close', 'volume']
        df = df[needed_cols]

        # Convert timezone-aware index to timezone-naive
        # yfinance returns UTC timezone-aware dates, but we need naive for comparisons
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = pd.DatetimeIndex([dt.replace(tzinfo=None) for dt in df.index])

        return df

    def _load_cache(self) -> pd.DataFrame | None:
        """Load cached price data from parquet file.

        Returns:
            DataFrame with cached data, or None if cache doesn't exist
        """
        if not self.cache_file.exists():
            return None

        try:
            df = pd.read_parquet(self.cache_file)

            # Convert timezone-aware index to timezone-naive for consistency
            # Old cached data may have timezone info, strip it for comparisons
            if hasattr(df.index, 'tz') and df.index.tz is not None:
                df.index = pd.DatetimeIndex([dt.replace(tzinfo=None) for dt in df.index])

            return df
        except Exception:
            # Cache file corrupted or unreadable - ignore it
            return None

    def _save_cache(self, df: pd.DataFrame) -> None:
        """Save price data to parquet cache file.

        Args:
            df: DataFrame to cache
        """
        try:
            df.to_parquet(self.cache_file)
        except Exception as e:
            # Cache save failed - warn but don't crash
            import warnings
            warnings.warn(
                f"Failed to save price data cache to {self.cache_file}: {e}",
                RuntimeWarning
            )

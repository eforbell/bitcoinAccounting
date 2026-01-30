"""Tests for visualization infrastructure (VIZ-001)."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.python.viz.config import VizConfig
from src.python.viz.data_fetcher import PriceDataFetcher


class TestVizConfig:
    """Tests for VizConfig dataclass."""

    def test_default_values(self) -> None:
        """Test that VizConfig has sensible defaults."""
        config = VizConfig()

        assert config.date_range == 'all'
        assert config.output_dir == Path('output/viz')
        assert config.chart_types == ['all']
        assert config.include_cost_basis is True
        assert config.log_scale is False
        assert config.dpi == 300

    def test_custom_values(self) -> None:
        """Test VizConfig with custom values."""
        config = VizConfig(
            date_range='ytd',
            output_dir=Path('/tmp/charts'),
            chart_types=['orange', 'balance'],
            include_cost_basis=False,
            log_scale=True,
            dpi=150
        )

        assert config.date_range == 'ytd'
        assert config.output_dir == Path('/tmp/charts')
        assert config.chart_types == ['orange', 'balance']
        assert config.include_cost_basis is False
        assert config.log_scale is True
        assert config.dpi == 150

    def test_tuple_date_range(self) -> None:
        """Test VizConfig with tuple date range."""
        config = VizConfig(
            date_range=('2020-01-01', '2023-12-31')
        )

        assert config.date_range == ('2020-01-01', '2023-12-31')

    def test_output_dir_path_conversion(self) -> None:
        """Test that output_dir string is converted to Path."""
        config = VizConfig(output_dir='~/charts')  # type: ignore[arg-type]

        assert isinstance(config.output_dir, Path)
        assert config.output_dir == Path('~/charts')

    def test_dpi_validation_too_low(self) -> None:
        """Test that DPI below 72 raises ValueError."""
        with pytest.raises(ValueError, match="DPI must be between 72 and 600"):
            VizConfig(dpi=50)

    def test_dpi_validation_too_high(self) -> None:
        """Test that DPI above 600 raises ValueError."""
        with pytest.raises(ValueError, match="DPI must be between 72 and 600"):
            VizConfig(dpi=1200)

    def test_dpi_validation_boundaries(self) -> None:
        """Test that DPI boundaries (72 and 600) are valid."""
        config_low = VizConfig(dpi=72)
        config_high = VizConfig(dpi=600)

        assert config_low.dpi == 72
        assert config_high.dpi == 600

    def test_chart_type_validation_invalid(self) -> None:
        """Test that invalid chart types raise ValueError."""
        with pytest.raises(ValueError, match="Invalid chart type 'invalid'"):
            VizConfig(chart_types=['invalid'])

    def test_chart_type_validation_valid(self) -> None:
        """Test that all valid chart types are accepted."""
        for chart_type in ['orange', 'balance', 'custody', 'all']:
            config = VizConfig(chart_types=[chart_type])
            assert chart_type in config.chart_types

    def test_date_range_tuple_validation_wrong_length(self) -> None:
        """Test that date_range tuple with wrong length raises ValueError."""
        with pytest.raises(ValueError, match="must have exactly 2 elements"):
            VizConfig(date_range=('2020-01-01',))  # type: ignore[arg-type]


class TestPriceDataFetcher:
    """Tests for PriceDataFetcher class."""

    @pytest.fixture
    def temp_cache_dir(self) -> Path:
        """Create a temporary cache directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_price_data(self) -> pd.DataFrame:
        """Create sample BTC price data for testing."""
        dates = pd.date_range('2020-01-01', '2020-01-10', freq='D')
        df = pd.DataFrame({
            'open': [7200.0 + i * 100 for i in range(len(dates))],
            'high': [7300.0 + i * 100 for i in range(len(dates))],
            'low': [7100.0 + i * 100 for i in range(len(dates))],
            'close': [7250.0 + i * 100 for i in range(len(dates))],
            'volume': [1000000.0] * len(dates)
        }, index=dates)
        return df

    def test_init_creates_cache_dir(self, temp_cache_dir: Path) -> None:
        """Test that PriceDataFetcher creates cache directory if missing."""
        cache_dir = temp_cache_dir / 'new_dir'
        assert not cache_dir.exists()

        fetcher = PriceDataFetcher(cache_dir=cache_dir)

        assert cache_dir.exists()
        assert fetcher.cache_file == cache_dir / 'btc_prices.parquet'

    def test_init_default_cache_dir(self) -> None:
        """Test that PriceDataFetcher uses default cache directory."""
        fetcher = PriceDataFetcher()

        expected_dir = Path.home() / '.cryptoaccounting' / 'cache'
        assert fetcher.cache_dir == expected_dir
        assert fetcher.cache_file == expected_dir / 'btc_prices.parquet'

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_from_yfinance_success(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test successful fetch from yfinance API."""
        # Mock yfinance ticker
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_price_data.copy()
        mock_ticker.history.return_value.columns = [
            'Open', 'High', 'Low', 'Close', 'Volume'
        ]
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)
        result = fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')

        assert not result.empty
        assert len(result) == 10
        assert list(result.columns) == ['open', 'high', 'low', 'close', 'volume']
        mock_ticker.history.assert_called_once()

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_caches_data(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test that fetched data is cached to parquet file."""
        # Mock yfinance ticker
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_price_data.copy()
        mock_ticker.history.return_value.columns = [
            'Open', 'High', 'Low', 'Close', 'Volume'
        ]
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)
        fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')

        # Check cache file was created
        assert fetcher.cache_file.exists()

        # Load cache and verify data
        cached_df = pd.read_parquet(fetcher.cache_file)
        assert not cached_df.empty
        assert len(cached_df) == 10

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_uses_cache_for_second_request(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test that second fetch uses cache instead of API."""
        # Mock yfinance ticker
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_price_data.copy()
        mock_ticker.history.return_value.columns = [
            'Open', 'High', 'Low', 'Close', 'Volume'
        ]
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)

        # First fetch - should call API
        result1 = fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')
        assert mock_ticker.history.call_count == 1

        # Second fetch - should use cache
        result2 = fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')
        assert mock_ticker.history.call_count == 1  # Still 1, not called again

        # Results should be identical (ignoring index frequency which may differ)
        pd.testing.assert_frame_equal(result1, result2, check_freq=False)

    def test_fetch_validates_date_range(self, temp_cache_dir: Path) -> None:
        """Test that start_date > end_date raises ValueError."""
        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)

        with pytest.raises(ValueError, match="start_date .* must be <= end_date"):
            fetcher.fetch_btc_price_history('2020-12-31', '2020-01-01')

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_handles_empty_response(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path
    ) -> None:
        """Test that empty API response raises RuntimeError."""
        # Mock yfinance ticker to return empty DataFrame
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)

        with pytest.raises(RuntimeError, match="No data returned from Yahoo Finance"):
            fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_handles_api_failure_with_cache(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test that API failure falls back to cache if available."""
        # First, populate cache
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_price_data.copy()
        mock_ticker.history.return_value.columns = [
            'Open', 'High', 'Low', 'Close', 'Volume'
        ]
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)
        fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')

        # Now make API fail
        mock_ticker.history.side_effect = Exception("API Error")

        # Fetch should succeed using cache
        result = fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')
        assert not result.empty
        assert len(result) == 10

    @patch('src.python.viz.data_fetcher.yf.Ticker')
    def test_fetch_handles_api_failure_without_cache(
        self,
        mock_ticker_class: MagicMock,
        temp_cache_dir: Path
    ) -> None:
        """Test that API failure without cache raises RuntimeError."""
        # Mock API failure
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API Error")
        mock_ticker_class.return_value = mock_ticker

        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)

        with pytest.raises(RuntimeError, match="Failed to fetch BTC price data"):
            fetcher.fetch_btc_price_history('2020-01-01', '2020-01-10')

    def test_fetch_accepts_datetime_objects(
        self,
        temp_cache_dir: Path
    ) -> None:
        """Test that fetch accepts datetime objects in addition to strings."""
        fetcher = PriceDataFetcher(cache_dir=temp_cache_dir)

        start = datetime(2020, 1, 1)
        end = datetime(2020, 1, 10)

        # Should not raise - validation should work with datetime objects
        # (API call will fail without mock, but validation should pass)
        try:
            fetcher.fetch_btc_price_history(start, end)
        except RuntimeError:
            # Expected - no mock for yfinance, but date validation passed
            pass

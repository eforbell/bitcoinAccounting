"""Tests for visualization infrastructure (VIZ-001, VIZ-002, VIZ-003, and VIZ-004)."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.python.db import SqliteBackend
from src.python.viz.balance_chart import BalanceChart
from src.python.viz.config import VizConfig
from src.python.viz.custody_chart import CustodyChart
from src.python.viz.data_fetcher import PriceDataFetcher
from src.python.viz.orange_plot import OrangePlot


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

    def test_init_default_cache_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that PriceDataFetcher uses new default cache directory."""
        monkeypatch.setenv("HOME", str(tmp_path))
        fetcher = PriceDataFetcher()

        expected_dir = Path.home() / '.bitcoinaccounting' / 'cache'
        assert fetcher.cache_dir == expected_dir
        assert fetcher.cache_file == expected_dir / 'btc_prices.parquet'

    def test_init_default_cache_dir_ignores_legacy_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test default cache does not fall back to legacy cache path."""
        monkeypatch.setenv("HOME", str(tmp_path))
        legacy_cache_dir = tmp_path / ".cryptoaccounting" / "cache"
        legacy_cache_dir.mkdir(parents=True, exist_ok=True)
        (legacy_cache_dir / "btc_prices.parquet").write_text("x")

        fetcher = PriceDataFetcher()
        expected_dir = tmp_path / ".bitcoinaccounting" / "cache"
        assert fetcher.cache_dir == expected_dir

    def test_init_default_cache_dir_uses_new_when_both_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test new cache dir is used when both new and legacy cache exist."""
        monkeypatch.setenv("HOME", str(tmp_path))
        legacy_cache_dir = tmp_path / ".cryptoaccounting" / "cache"
        legacy_cache_dir.mkdir(parents=True, exist_ok=True)
        (legacy_cache_dir / "btc_prices.parquet").write_text("x")

        new_cache_dir = tmp_path / ".bitcoinaccounting" / "cache"
        new_cache_dir.mkdir(parents=True, exist_ok=True)

        fetcher = PriceDataFetcher()
        assert fetcher.cache_dir == new_cache_dir

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


class TestOrangePlot:
    """Tests for OrangePlot class (VIZ-002)."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_backend(self) -> SqliteBackend:
        """Create an in-memory SQLite backend with sample data."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add sample BTC trades
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            -- Purchase 1: 0.5 BTC at $10,000 on 2020-01-15
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coinbase', '', ''),
            -- Purchase 2: 0.3 BTC at $12,000 on 2020-06-01
            (:date2, 'Trade', 'BTC', 0.3, 'USD', 3600.0, '', 0, 'Coinbase', '', ''),
            -- Sale 1: 0.1 BTC at $15,000 on 2021-01-01
            (:date3, 'Trade', 'USD', 1500.0, 'BTC', 0.1, '', 0, 'Coinbase', '', '')
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
                'date3': '2021-01-01 09:00:00',
            }
        )

        # Add price data for cost basis calculations
        backend.execute(
            """
            INSERT INTO pair_price (date, to_curr, from_curr, price) VALUES
            (:date1, 'BTC', 'USD', 10000.0),
            (:date2, 'BTC', 'USD', 12000.0),
            (:date3, 'BTC', 'USD', 15000.0)
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
                'date3': '2021-01-01 09:00:00',
            }
        )

        return backend

    @pytest.fixture
    def sample_price_data(self) -> pd.DataFrame:
        """Create sample BTC-USD price data."""
        dates = pd.date_range('2020-01-01', '2021-12-31', freq='D')
        df = pd.DataFrame({
            'open': [10000.0 + i * 10 for i in range(len(dates))],
            'high': [10100.0 + i * 10 for i in range(len(dates))],
            'low': [9900.0 + i * 10 for i in range(len(dates))],
            'close': [10050.0 + i * 10 for i in range(len(dates))],
            'volume': [1000000.0] * len(dates)
        }, index=dates)
        return df

    def test_orange_plot_basic_generation(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test basic orange plot generation with purchases."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            include_cost_basis=False
        )

        plot = OrangePlot(sample_backend, config)

        # Mock price fetcher
        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            mock_fetch.return_value = sample_price_data

            output_path = plot.generate()

            # Verify file was created
            assert output_path.exists()
            assert output_path.suffix == '.png'
            assert 'btc_orange_plot' in output_path.name

    def test_orange_plot_with_cost_basis(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test orange plot with cost basis overlay."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            include_cost_basis=True
        )

        plot = OrangePlot(sample_backend, config)

        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            mock_fetch.return_value = sample_price_data

            output_path = plot.generate()

            assert output_path.exists()

    def test_orange_plot_log_scale(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test orange plot with logarithmic Y-axis."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            log_scale=True
        )

        plot = OrangePlot(sample_backend, config)

        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            mock_fetch.return_value = sample_price_data

            output_path = plot.generate()

            assert output_path.exists()

    def test_orange_plot_empty_ledger(
        self,
        temp_output_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test that empty ledger raises ValueError."""
        # Create empty backend
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        plot = OrangePlot(backend, config)

        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            mock_fetch.return_value = sample_price_data

            with pytest.raises(ValueError, match="No Bitcoin transactions found"):
                plot.generate()

    def test_orange_plot_no_price_data(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that missing price data raises RuntimeError."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        plot = OrangePlot(sample_backend, config)

        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            # Return empty DataFrame
            mock_fetch.return_value = pd.DataFrame()

            with pytest.raises(RuntimeError, match="No BTC-USD price data available"):
                plot.generate()

    def test_calculate_running_cost_basis(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test running cost basis calculation."""
        config = VizConfig(output_dir=temp_output_dir)
        plot = OrangePlot(sample_backend, config)

        # Get purchases from sample data
        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trade_cost('BTC', 'USD')
        purchases = [t for t in trades if t['quantity'] > 0]

        # Calculate cost basis
        cost_basis_data = plot._calculate_running_cost_basis(purchases)

        # Should have 2 cost basis points (2 purchases)
        assert len(cost_basis_data) == 2

        # First purchase: 0.5 BTC at $10,000 = $10,000 basis
        assert cost_basis_data[0]['basis'] == pytest.approx(10000.0)

        # Second purchase: (0.5*10000 + 0.3*12000) / (0.5 + 0.3) = 10750
        expected_basis = (0.5 * 10000 + 0.3 * 12000) / (0.5 + 0.3)
        assert cost_basis_data[1]['basis'] == pytest.approx(expected_basis)

    def test_calculate_running_cost_basis_skips_none_prices(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that cost basis calculation skips purchases with None unit_cost."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add a BTC-EUR trade (counter currency is EUR, not USD)
        # Request costs in USD, but don't add EUR-USD price data
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            (:date1, 'Trade', 'BTC', 0.5, 'EUR', 4500.0, '', 0, 'Kraken', '', '')
            """,
            {'date1': '2020-01-15 10:00:00'}
        )

        # Don't add EUR-USD price data - unit_cost will be None when requesting USD costs

        config = VizConfig(output_dir=temp_output_dir)
        plot = OrangePlot(backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(backend)
        # Request costs in USD, but trade is in EUR and no EUR-USD price available
        trades = trade_query.get_trade_cost('BTC', 'USD')
        purchases = [t for t in trades if t['quantity'] > 0]

        # Calculate cost basis
        cost_basis_data = plot._calculate_running_cost_basis(purchases)

        # Should be empty since unit_cost is None (no EUR-USD conversion available)
        assert len(cost_basis_data) == 0

    def test_filter_to_date_range(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test filtering trades to date range."""
        config = VizConfig(output_dir=temp_output_dir)
        plot = OrangePlot(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trade_cost('BTC', 'USD')

        # Filter to 2020 only
        start = datetime(2020, 1, 1)
        end = datetime(2020, 12, 31)
        filtered = plot._filter_to_date_range(trades, start, end)

        # Should have 2 trades (2 purchases in 2020)
        assert len(filtered) == 2

        # Sale in 2021 should be excluded
        for trade in filtered:
            date = trade['date']
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            assert start <= date <= end

    def test_resolve_date_range_all(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving 'all' date range preset."""
        config = VizConfig(date_range='all', output_dir=temp_output_dir)
        plot = OrangePlot(sample_backend, config)

        start, end = plot._resolve_date_range()

        # Should span from first trade (2020-01-15) to now
        assert start.year == 2020
        assert start.month == 1
        assert start.day == 15

    def test_resolve_date_range_ytd(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving 'ytd' date range preset."""
        config = VizConfig(date_range='ytd', output_dir=temp_output_dir)
        plot = OrangePlot(sample_backend, config)

        start, end = plot._resolve_date_range()

        # Should be Jan 1 of current year to now
        now = datetime.now()
        assert start.year == now.year
        assert start.month == 1
        assert start.day == 1

    def test_resolve_date_range_tuple(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving tuple date range."""
        start_date = datetime(2020, 6, 1)
        end_date = datetime(2021, 6, 1)

        config = VizConfig(
            date_range=(start_date, end_date),
            output_dir=temp_output_dir
        )
        plot = OrangePlot(sample_backend, config)

        start, end = plot._resolve_date_range()

        assert start == start_date
        assert end == end_date

    def test_output_path_includes_date(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that output path includes current date."""
        config = VizConfig(output_dir=temp_output_dir)
        plot = OrangePlot(sample_backend, config)

        output_path = plot._get_output_path()

        today = datetime.now().strftime('%Y-%m-%d')
        assert today in output_path.name
        assert output_path.name.startswith('btc_orange_plot_')
        assert output_path.suffix == '.png'

    def test_custom_dpi(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path,
        sample_price_data: pd.DataFrame
    ) -> None:
        """Test orange plot with custom DPI."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            dpi=150
        )

        plot = OrangePlot(sample_backend, config)

        with patch.object(plot.price_fetcher, 'fetch_btc_price_history') as mock_fetch:
            mock_fetch.return_value = sample_price_data

            output_path = plot.generate()

            assert output_path.exists()

class TestBalanceChart:
    """Tests for BalanceChart class (VIZ-003)."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_backend(self) -> SqliteBackend:
        """Create an in-memory SQLite backend with sample data."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add sample BTC trades over time
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            -- Purchase 1: 0.5 BTC on 2020-01-15
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coinbase', '', ''),
            -- Purchase 2: 0.3 BTC on 2020-06-01
            (:date2, 'Trade', 'BTC', 0.3, 'USD', 3600.0, '', 0, 'Coinbase', '', ''),
            -- Purchase 3: 0.2 BTC on 2021-01-01
            (:date3, 'Trade', 'BTC', 0.2, 'USD', 3000.0, '', 0, 'Coinbase', '', ''),
            -- Sale 1: 0.1 BTC on 2021-06-01
            (:date4, 'Trade', 'USD', 1500.0, 'BTC', 0.1, '', 0, 'Coinbase', '', '')
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
                'date3': '2021-01-01 09:00:00',
                'date4': '2021-06-01 12:00:00',
            }
        )

        return backend

    def test_balance_chart_basic_generation(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test basic balance chart generation."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = BalanceChart(sample_backend, config)
        output_path = chart.generate()

        # Verify file was created
        assert output_path.exists()
        assert output_path.suffix == '.png'
        assert 'btc_balance' in output_path.name

    def test_cumulative_balance_calculation(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test cumulative balance calculation."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trades('BTC')

        start = datetime(2020, 1, 1)
        end = datetime(2021, 12, 31)
        balance_data = chart._calculate_cumulative_balance(trades, start, end)

        # Should have: start point, 4 trades, end point = 6 points
        assert len(balance_data) >= 5

        # Verify cumulative balance progression
        # Start: 0, +0.5, +0.3, +0.2, -0.1 = 0.9 final
        final_balance = balance_data[-1]['balance']
        assert final_balance == pytest.approx(0.9)

    def test_balance_chart_empty_ledger(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that empty ledger raises ValueError."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = BalanceChart(backend, config)

        with pytest.raises(ValueError, match="No Bitcoin transactions found"):
            chart.generate()

    def test_balance_chart_single_transaction(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test balance chart with single transaction."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add single trade
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            (:date1, 'Trade', 'BTC', 1.0, 'USD', 10000.0, '', 0, 'Coinbase', '', '')
            """,
            {'date1': '2020-01-15 10:00:00'}
        )

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = BalanceChart(backend, config)
        output_path = chart.generate()

        assert output_path.exists()

    def test_balance_chart_negative_balance_warning(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that negative balance triggers warning."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add trades that result in negative balance
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            -- Purchase 0.5 BTC
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coinbase', '', ''),
            -- Sell 1.0 BTC (more than we have!)
            (:date2, 'Trade', 'USD', 10000.0, 'BTC', 1.0, '', 0, 'Coinbase', '', '')
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
            }
        )

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = BalanceChart(backend, config)

        # Should warn about negative balance
        with pytest.warns(RuntimeWarning, match="Negative balance detected"):
            output_path = chart.generate()

        assert output_path.exists()

    def test_milestone_calculation(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test milestone marker calculation."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        # Test with 0.9 BTC final balance
        milestones = chart._calculate_milestones(0.9)

        # Should include: 0.01, 0.1, 0.5
        assert 0.01 in milestones
        assert 0.1 in milestones
        assert 0.5 in milestones

        # Should not include 1 BTC (above max)
        assert 1 not in milestones

    def test_milestone_calculation_high_balance(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test milestone calculation with high balance."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        # Test with 150 BTC
        milestones = chart._calculate_milestones(150)

        # Should include standard milestones
        assert 21 in milestones  # Special Bitcoin number
        assert 100 in milestones

    def test_resolve_date_range_all(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving 'all' date range preset."""
        config = VizConfig(date_range='all', output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trades('BTC')

        start, end = chart._resolve_date_range(trades)

        # Should span from first trade (2020-01-15) to now
        assert start.year == 2020
        assert start.month == 1
        assert start.day == 15

    def test_resolve_date_range_ytd(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving 'ytd' date range preset."""
        config = VizConfig(date_range='ytd', output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trades('BTC')

        start, end = chart._resolve_date_range(trades)

        # Should be Jan 1 of current year to now
        now = datetime.now()
        assert start.year == now.year
        assert start.month == 1
        assert start.day == 1

    def test_resolve_date_range_tuple(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving tuple date range."""
        start_date = datetime(2020, 6, 1)
        end_date = datetime(2021, 6, 1)

        config = VizConfig(
            date_range=(start_date, end_date),
            output_dir=temp_output_dir
        )
        chart = BalanceChart(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trades('BTC')

        start, end = chart._resolve_date_range(trades)

        assert start == start_date
        assert end == end_date

    def test_output_path_includes_date(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that output path includes current date."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        output_path = chart._get_output_path()

        today = datetime.now().strftime('%Y-%m-%d')
        assert today in output_path.name
        assert output_path.name.startswith('btc_balance_')
        assert output_path.suffix == '.png'

    def test_custom_dpi(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test balance chart with custom DPI."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            dpi=150
        )

        chart = BalanceChart(sample_backend, config)
        output_path = chart.generate()

        assert output_path.exists()

    def test_date_range_filtering(
        self,
        sample_backend: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that trades outside date range are excluded."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = BalanceChart(sample_backend, config)

        from src.python.db.queries import TradeQuery
        trade_query = TradeQuery(sample_backend)
        trades = trade_query.get_trades('BTC')

        # Filter to 2020 only
        start = datetime(2020, 1, 1)
        end = datetime(2020, 12, 31)
        balance_data = chart._calculate_cumulative_balance(trades, start, end)

        # Should only include 2 trades from 2020 (+ start/end points)
        # Verify no 2021 trades included
        for point in balance_data:
            assert point['date'] <= end

class TestCustodyChart:
    """Tests for CustodyChart class (VIZ-004)."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_backend_with_wallets(self) -> SqliteBackend:
        """Create an in-memory SQLite backend with wallet metadata."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add wallet metadata
        backend.execute(
            """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, active) VALUES
            ('Coldcard', 'hardware', 'self-custodied', 'Hardware wallet', 1),
            ('Coinbase', 'exchange', 'custodial', 'Exchange account', 1),
            ('Casa', 'multisig', 'multisig', '2-of-3 multisig', 1)
            """
        )

        # Add sample BTC trades with different custody types
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            -- Self-custodied: 0.5 BTC
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coldcard', '', ''),
            -- Custodial: 0.3 BTC
            (:date2, 'Trade', 'BTC', 0.3, 'USD', 3600.0, '', 0, 'Coinbase', '', ''),
            -- Multisig: 0.2 BTC
            (:date3, 'Trade', 'BTC', 0.2, 'USD', 3000.0, '', 0, 'Casa', '', ''),
            -- Transfer from custodial to self-custodied: -0.1 from Coinbase
            (:date4, 'Trade', 'USD', 1500.0, 'BTC', 0.1, '', 0, 'Coinbase', '', ''),
            -- +0.1 to Coldcard
            (:date5, 'Trade', 'BTC', 0.1, 'USD', 1500.0, '', 0, 'Coldcard', '', '')
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
                'date3': '2021-01-01 09:00:00',
                'date4': '2021-06-01 12:00:00',
                'date5': '2021-06-01 12:05:00',
            }
        )

        return backend

    @pytest.fixture
    def sample_backend_no_wallets(self) -> SqliteBackend:
        """Create backend with trades but no wallet metadata."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add trades without wallet metadata
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'UnknownExchange', '', '')
            """,
            {'date1': '2020-01-15 10:00:00'}
        )

        return backend

    def test_custody_chart_basic_generation(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test basic custody chart generation with mixed custody types."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = CustodyChart(sample_backend_with_wallets, config)
        output_path = chart.generate()

        # Verify file was created
        assert output_path.exists()
        assert output_path.suffix == '.png'
        assert 'btc_custody' in output_path.name

    def test_custody_balance_calculation(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test custody balance calculation."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_with_wallets, config)

        start = datetime(2020, 1, 1)
        end = datetime(2021, 12, 31)
        custody_data = chart._get_custody_balances(start, end)

        # Should have: start, 5 trades, end = 7 points
        assert len(custody_data) >= 6

        # Verify final balances
        # Self-custodied: 0.5 + 0.1 = 0.6
        # Custodial: 0.3 - 0.1 = 0.2
        # Multisig: 0.2
        final = custody_data[-1]
        assert final['self-custodied'] == pytest.approx(0.6)
        assert final['custodial'] == pytest.approx(0.2)
        assert final['multisig'] == pytest.approx(0.2)
        assert final['unknown'] == pytest.approx(0.0)

    def test_custody_chart_empty_ledger(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that empty ledger raises ValueError."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = CustodyChart(backend, config)

        with pytest.raises(ValueError, match="No Bitcoin balance found"):
            chart.generate()

    def test_custody_chart_unknown_custody(
        self,
        sample_backend_no_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test custody chart with transactions lacking wallet metadata."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = CustodyChart(sample_backend_no_wallets, config)
        output_path = chart.generate()

        # Should succeed and show as "unknown" custody
        assert output_path.exists()

        # Verify custody data
        start = datetime(2020, 1, 1)
        end = datetime(2021, 1, 1)
        custody_data = chart._get_custody_balances(start, end)

        final = custody_data[-1]
        assert final['unknown'] == pytest.approx(0.5)
        assert final['self-custodied'] == pytest.approx(0.0)

    def test_custody_chart_single_custody_type(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test custody chart with all holdings in one custody type."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add wallet
        backend.execute(
            """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, active) VALUES
            ('Coldcard', 'hardware', 'self-custodied', 'Hardware wallet', 1)
            """
        )

        # Add trade
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            (:date1, 'Trade', 'BTC', 1.0, 'USD', 10000.0, '', 0, 'Coldcard', '', '')
            """,
            {'date1': '2020-01-15 10:00:00'}
        )

        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir
        )

        chart = CustodyChart(backend, config)
        output_path = chart.generate()

        # Should show single area (not stacked)
        assert output_path.exists()

    def test_wallet_custody_map(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test wallet custody mapping."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_with_wallets, config)

        wallet_map = chart._get_wallet_custody_map()

        assert wallet_map['Coldcard'] == 'self-custodied'
        assert wallet_map['Coinbase'] == 'custodial'
        assert wallet_map['Casa'] == 'multisig'

    def test_wallet_custody_map_no_wallets_table(
        self,
        sample_backend_no_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test wallet custody mapping when wallets table is empty."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_no_wallets, config)

        wallet_map = chart._get_wallet_custody_map()

        # Should return empty dict
        assert wallet_map == {}

    def test_resolve_date_range_all(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving 'all' date range preset."""
        config = VizConfig(date_range='all', output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_with_wallets, config)

        start, end = chart._resolve_date_range()

        # Should span from first trade (2020-01-15) to now
        assert start.year == 2020
        assert start.month == 1
        assert start.day == 15

    def test_resolve_date_range_tuple(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test resolving tuple date range."""
        start_date = datetime(2020, 6, 1)
        end_date = datetime(2021, 6, 1)

        config = VizConfig(
            date_range=(start_date, end_date),
            output_dir=temp_output_dir
        )
        chart = CustodyChart(sample_backend_with_wallets, config)

        start, end = chart._resolve_date_range()

        assert start == start_date
        assert end == end_date

    def test_output_path_includes_date(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that output path includes current date."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_with_wallets, config)

        output_path = chart._get_output_path()

        today = datetime.now().strftime('%Y-%m-%d')
        assert today in output_path.name
        assert output_path.name.startswith('btc_custody_')
        assert output_path.suffix == '.png'

    def test_custom_dpi(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test custody chart with custom DPI."""
        config = VizConfig(
            date_range='all',
            output_dir=temp_output_dir,
            dpi=150
        )

        chart = CustodyChart(sample_backend_with_wallets, config)
        output_path = chart.generate()

        assert output_path.exists()

    def test_custody_type_normalization(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that custody types are normalized correctly."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add wallets with various custody type names
        backend.execute(
            """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, active) VALUES
            ('HW1', 'hardware', 'self', 'Self custody variant', 1),
            ('HW2', 'hardware', 'cold', 'Cold storage', 1),
            ('EX1', 'exchange', 'exchange', 'Exchange variant', 1),
            ('MS1', 'multisig', 'multi-sig', 'Multisig variant', 1)
            """
        )

        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(backend, config)

        wallet_map = chart._get_wallet_custody_map()

        # All should be normalized to standard types
        assert wallet_map['HW1'] == 'self-custodied'
        assert wallet_map['HW2'] == 'self-custodied'
        assert wallet_map['EX1'] == 'custodial'
        assert wallet_map['MS1'] == 'multisig'

    def test_date_range_filtering(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that trades outside date range are excluded."""
        config = VizConfig(output_dir=temp_output_dir)
        chart = CustodyChart(sample_backend_with_wallets, config)

        # Filter to 2020 only
        start = datetime(2020, 1, 1)
        end = datetime(2020, 12, 31)
        custody_data = chart._get_custody_balances(start, end)

        # Should only include 2 trades from 2020
        # Self-custodied: 0.5, Custodial: 0.3
        final = custody_data[-1]
        assert final['self-custodied'] == pytest.approx(0.5)
        assert final['custodial'] == pytest.approx(0.3)
        assert final['multisig'] == pytest.approx(0.0)  # 2021 trade excluded


class TestPDFReport:
    """Tests for PDFReport class."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_backend_with_wallets(self) -> SqliteBackend:
        """Create an in-memory SQLite backend with wallet metadata."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)

        # Add wallet metadata
        backend.execute(
            """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, active) VALUES
            ('Coldcard', 'hardware', 'self-custodied', 'Hardware wallet', 1),
            ('Coinbase', 'exchange', 'custodial', 'Exchange account', 1)
            """
        )

        # Add sample BTC trades
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES
            (:date1, 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coldcard', '', ''),
            (:date2, 'Trade', 'BTC', 0.3, 'USD', 3600.0, '', 0, 'Coinbase', '', '')
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
            }
        )

        # Add pair_price data for cost basis
        backend.execute(
            """
            INSERT INTO pair_price (date, to_curr, from_curr, price) VALUES
            (:date1, 'BTC', 'USD', 10000.0),
            (:date2, 'BTC', 'USD', 12000.0)
            """,
            {
                'date1': '2020-01-15 10:00:00',
                'date2': '2020-06-01 14:30:00',
            }
        )

        return backend

    def test_pdf_report_basic_generation(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that PDF report generates successfully with sample data."""
        # Skip if reportlab not available
        try:
            from src.python.viz.report import PDFReport
        except ImportError:
            pytest.skip("reportlab not installed")

        config = VizConfig(output_dir=temp_output_dir)
        report = PDFReport(sample_backend_with_wallets, config)

        output_path = report.generate()

        # Verify output file exists
        assert output_path.exists()
        assert output_path.suffix == '.pdf'
        assert output_path.name.startswith('btc_report_')

        # Verify file is not empty
        assert output_path.stat().st_size > 0

    def test_pdf_report_empty_ledger(
        self,
        temp_output_dir: Path
    ) -> None:
        """Test that PDF report raises error with empty ledger."""
        try:
            from src.python.viz.report import PDFReport
        except ImportError:
            pytest.skip("reportlab not installed")

        backend = SqliteBackend(':memory:', auto_create_tables=True)
        config = VizConfig(output_dir=temp_output_dir)
        report = PDFReport(backend, config)

        with pytest.raises(ValueError, match="No Bitcoin transactions"):
            report.generate()

    def test_pdf_report_date_range(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test PDF report with custom date range."""
        try:
            from src.python.viz.report import PDFReport
        except ImportError:
            pytest.skip("reportlab not installed")

        start = datetime(2020, 1, 1)
        end = datetime(2020, 12, 31)
        config = VizConfig(
            date_range=(start, end),
            output_dir=temp_output_dir
        )
        report = PDFReport(sample_backend_with_wallets, config)

        output_path = report.generate()

        # Verify file was created
        assert output_path.exists()

    def test_pdf_report_output_path(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that PDF report uses correct output path."""
        try:
            from src.python.viz.report import PDFReport
        except ImportError:
            pytest.skip("reportlab not installed")

        config = VizConfig(output_dir=temp_output_dir)
        report = PDFReport(sample_backend_with_wallets, config)

        output_path = report._get_output_path()

        # Verify path structure
        assert output_path.parent == temp_output_dir
        assert output_path.name.startswith('btc_report_')
        assert output_path.suffix == '.pdf'

    def test_pdf_report_summary_stats(
        self,
        sample_backend_with_wallets: SqliteBackend,
        temp_output_dir: Path
    ) -> None:
        """Test that summary stats are calculated correctly."""
        try:
            from src.python.viz.report import PDFReport
        except ImportError:
            pytest.skip("reportlab not installed")

        config = VizConfig(output_dir=temp_output_dir)
        report = PDFReport(sample_backend_with_wallets, config)

        stats = report._get_summary_stats()

        # Verify stats keys
        assert "Total BTC Holdings" in stats
        assert "Purchases" in stats
        assert "Sales" in stats

        # Verify values
        assert "BTC" in stats["Total BTC Holdings"]
        assert int(stats["Purchases"]) > 0

"""Tests for the shared report data series (viz.series).

The matplotlib charts, the PDF report and the web reports all read these
series, so the numbers are tested here rather than through rendered images.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from db import SqliteBackend
from db.queries import BalanceCalculator
from viz.series import (
    DateWindow,
    PricePoint,
    accumulation_series,
    holdings_series,
    nearest_price,
    normalize_custody,
    price_series,
    resolve_window,
    to_naive_datetime,
    wallet_custody_map,
)

ALL_TIME = DateWindow(datetime(2019, 1, 1), datetime(2030, 1, 1))


def _ledger(backend: SqliteBackend, *rows: tuple) -> None:
    """Insert (date, trans_type, buy_curr, buy, sell_curr, sell, exchange) rows."""
    for when, trans_type, buy_curr, buy, sell_curr, sell, exchange in rows:
        backend.execute(
            """
            INSERT INTO ledger (
                createddate, trans_type, buy_curr, buy, sell_curr, sell,
                fee_curr, fee, exchange, "group", comment
            ) VALUES (:when, :trans_type, :buy_curr, :buy, :sell_curr, :sell,
                      '', 0, :exchange, '', '')
            """,
            {
                "when": when, "trans_type": trans_type, "buy_curr": buy_curr,
                "buy": buy, "sell_curr": sell_curr, "sell": sell, "exchange": exchange,
            },
        )


def _wallets(backend: SqliteBackend, *rows: tuple[str, str]) -> None:
    for wallet_id, custody in rows:
        backend.execute(
            """
            INSERT INTO wallets (wallet_id, wallet_type, custody, description, active)
            VALUES (:wallet_id, 'hardware', :custody, '', 1)
            """,
            {"wallet_id": wallet_id, "custody": custody},
        )


@pytest.fixture
def backend() -> SqliteBackend:
    b = SqliteBackend(":memory:", auto_create_tables=True)
    yield b
    b.close()


@pytest.fixture
def trades_backend(backend: SqliteBackend) -> SqliteBackend:
    """0.5 BTC @ $10k, 0.3 BTC @ $12k, then a 0.1 BTC sale @ $15k."""
    _ledger(
        backend,
        ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "USD", 5000.0, "Coinbase"),
        ("2020-06-01 14:30:00", "Trade", "BTC", 0.3, "USD", 3600.0, "Coinbase"),
        ("2021-01-01 09:00:00", "Trade", "USD", 1500.0, "BTC", 0.1, "Coinbase"),
    )
    return backend


@pytest.fixture
def custody_backend(backend: SqliteBackend) -> SqliteBackend:
    _wallets(
        backend,
        ("Coldcard", "self-custodied"), ("Coinbase", "custodial"), ("Casa", "multisig"),
    )
    _ledger(
        backend,
        ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "USD", 5000.0, "Coldcard"),
        ("2020-06-01 14:30:00", "Trade", "BTC", 0.3, "USD", 3600.0, "Coinbase"),
        ("2021-01-01 09:00:00", "Trade", "BTC", 0.2, "USD", 3000.0, "Casa"),
        ("2021-06-01 12:00:00", "Trade", "USD", 1500.0, "BTC", 0.1, "Coinbase"),
        ("2021-06-01 12:05:00", "Trade", "BTC", 0.1, "USD", 1500.0, "Coldcard"),
    )
    return backend


# ── Dates and windows ──


class TestToNaiveDatetime:
    def test_parses_iso_strings_and_strips_zulu(self) -> None:
        assert to_naive_datetime("2020-01-15T10:00:00Z") == datetime(2020, 1, 15, 10)

    def test_strips_timezone(self) -> None:
        aware = datetime(2020, 1, 15, 10, tzinfo=timezone.utc)
        assert to_naive_datetime(aware) == datetime(2020, 1, 15, 10)

    def test_accepts_dates_and_pandas_timestamps(self) -> None:
        assert to_naive_datetime(date(2020, 1, 15)) == datetime(2020, 1, 15)
        assert to_naive_datetime(pd.Timestamp("2020-01-15", tz="UTC")) == datetime(2020, 1, 15)


class TestResolveWindow:
    NOW = datetime(2026, 10, 11, 14, 30)

    def test_all_starts_at_first_btc_row_of_any_type(self, trades_backend: SqliteBackend) -> None:
        # A deposit before the first trade still opens the window.
        _ledger(trades_backend, ("2019-11-02 08:00:00", "Deposit", "BTC", 0.05, "", 0.0, "Coldcard"))
        window = resolve_window(trades_backend, "all", now=self.NOW)
        assert window == DateWindow(datetime(2019, 11, 2, 8), self.NOW)

    def test_all_starts_at_earliest_row_across_date_formats(self, backend: SqliteBackend) -> None:
        # SQLite compares TEXT: "2024-01-01T09:00" sorts after "2024-01-01 10:00".
        _ledger(
            backend,
            ("2024-01-01 10:00:00", "Trade", "BTC", 0.1, "USD", 4000.0, "Coinbase"),
            ("2024-01-01T09:00:00", "Trade", "BTC", 0.1, "USD", 4000.0, "Coinbase"),
        )
        window = resolve_window(backend, "all", now=self.NOW)
        assert window.start == datetime(2024, 1, 1, 9)
        assert len(accumulation_series(backend, window).purchases) == 2

    def test_all_on_empty_ledger_falls_back_to_last_year(self, backend: SqliteBackend) -> None:
        window = resolve_window(backend, "all", now=self.NOW)
        assert window.start == datetime(2025, 1, 1)

    def test_presets(self, backend: SqliteBackend) -> None:
        assert resolve_window(backend, "ytd", now=self.NOW).start == datetime(2026, 1, 1)
        assert resolve_window(backend, "1y", now=self.NOW).start == datetime(2025, 10, 11, 14, 30)
        assert resolve_window(backend, "5y", now=self.NOW).start == datetime(2021, 10, 11, 14, 30)

    def test_leap_day_does_not_crash(self, backend: SqliteBackend) -> None:
        leap = datetime(2028, 2, 29, 9)
        assert resolve_window(backend, "1y", now=leap).start == datetime(2027, 2, 28, 9)

    def test_tuple_passthrough_normalizes(self, backend: SqliteBackend) -> None:
        window = resolve_window(backend, ("2020-06-01", datetime(2021, 6, 1, tzinfo=timezone.utc)))
        assert window == DateWindow(datetime(2020, 6, 1), datetime(2021, 6, 1))

    def test_unknown_preset(self, backend: SqliteBackend) -> None:
        with pytest.raises(ValueError, match="Unknown date range"):
            resolve_window(backend, "2w")


# ── Holdings ──


class TestCustodyMapping:
    def test_wallet_custody_map(self, custody_backend: SqliteBackend) -> None:
        assert wallet_custody_map(custody_backend) == {
            "Coldcard": "self-custodied", "Coinbase": "custodial", "Casa": "multisig",
        }

    def test_empty_wallets_table(self, backend: SqliteBackend) -> None:
        assert wallet_custody_map(backend) == {}

    @pytest.mark.parametrize("label, expected", [
        ("self", "self-custodied"), ("Cold", "self-custodied"), ("hardware", "self-custodied"),
        ("exchange", "custodial"), ("third-party", "custodial"),
        ("multi-sig", "multisig"), ("collaborative", "multisig"),
        ("vault-ish", "unknown"), ("", "unknown"), (None, "unknown"),
    ])
    def test_normalize_custody(self, label: str | None, expected: str) -> None:
        assert normalize_custody(label) == expected


class TestHoldingsSeries:
    def test_final_balances_by_custody(self, custody_backend: SqliteBackend) -> None:
        series = holdings_series(custody_backend, DateWindow(datetime(2020, 1, 1), datetime(2021, 12, 31)))
        final = series.latest.by_custody
        assert final["self-custodied"] == pytest.approx(0.6)
        assert final["custodial"] == pytest.approx(0.2)
        assert final["multisig"] == pytest.approx(0.2)
        assert final["unknown"] == pytest.approx(0.0)
        assert series.latest.total == pytest.approx(1.0)
        assert series.self_custody_pct() == pytest.approx(80.0)

    def test_window_end_excludes_later_rows(self, custody_backend: SqliteBackend) -> None:
        series = holdings_series(custody_backend, DateWindow(datetime(2020, 1, 1), datetime(2020, 12, 31)))
        final = series.latest.by_custody
        assert final["self-custodied"] == pytest.approx(0.5)
        assert final["custodial"] == pytest.approx(0.3)
        assert final["multisig"] == pytest.approx(0.0)
        assert all(p.when <= datetime(2020, 12, 31) for p in series.points)

    def test_wallets_without_metadata_are_unknown(self, backend: SqliteBackend) -> None:
        _ledger(backend, ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "USD", 5000.0, "Mystery"))
        series = holdings_series(backend, ALL_TIME)
        assert series.latest.by_custody["unknown"] == pytest.approx(0.5)

    def test_counts_every_ledger_type_like_get_balance(self, backend: SqliteBackend) -> None:
        # The balance chart used to count Trade rows only, so mining, income,
        # spends and withdrawal fees never showed up in "Current Balance".
        _ledger(
            backend,
            ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "USD", 5000.0, "River"),
            ("2020-02-01 10:00:00", "Mining", "BTC", 0.02, "", 0.0, "Coldcard"),
            ("2020-03-01 10:00:00", "Interest Income", "BTC", 0.001, "", 0.0, "River"),
            ("2020-04-01 10:00:00", "Withdrawal", "", 0.0, "BTC", 0.3001, "River"),
            ("2020-04-01 10:30:00", "Deposit", "BTC", 0.3, "", 0.0, "Coldcard"),
            ("2020-05-01 10:00:00", "Spend", "", 0.0, "BTC", 0.01, "Coldcard"),
            ("2020-06-01 10:00:00", "Stake", "BTC", 0.25, "", 0.0, "River"),
        )
        series = holdings_series(backend, ALL_TIME)
        expected = BalanceCalculator(backend).get_balance("BTC")
        assert series.latest.total == pytest.approx(expected)
        assert series.latest.total == pytest.approx(0.5 + 0.02 + 0.001 - 0.3001 + 0.3 - 0.01)

    def test_same_day_transfer_does_not_dip(self, backend: SqliteBackend) -> None:
        _ledger(
            backend,
            ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "USD", 5000.0, "River"),
            ("2020-04-01 10:00:00", "Withdrawal", "", 0.0, "BTC", 0.5, "River"),
            ("2020-04-01 10:30:00", "Deposit", "BTC", 0.5, "", 0.0, "Coldcard"),
        )
        series = holdings_series(backend, DateWindow(datetime(2020, 2, 1), datetime(2020, 12, 31)))
        assert {round(p.total, 8) for p in series.points} == {0.5}

    def test_opening_point_seeds_prior_holdings(self, custody_backend: SqliteBackend) -> None:
        series = holdings_series(custody_backend, DateWindow(datetime(2020, 3, 1), datetime(2020, 12, 31)))
        opening = series.points[0]
        assert opening.when == datetime(2020, 3, 1)
        assert opening.by_custody["self-custodied"] == pytest.approx(0.5)
        assert opening.total == pytest.approx(0.5)

    def test_mid_day_window_start_keeps_points_ordered(self, backend: SqliteBackend) -> None:
        _ledger(backend, ("2025-10-11 15:00:00", "Trade", "BTC", 0.1, "USD", 6000.0, "River"))
        window = DateWindow(datetime(2025, 10, 11, 14, 30), datetime(2026, 10, 11, 14, 30))
        whens = [p.when for p in holdings_series(backend, window).points]
        assert whens == sorted(whens)
        assert whens[0] == window.start

    def test_empty_ledger(self, backend: SqliteBackend) -> None:
        series = holdings_series(backend, ALL_TIME)
        assert not series.has_transactions
        assert series.latest.total == 0.0
        assert series.self_custody_pct() is None


# ── Accumulation ──


class TestAccumulationSeries:
    def test_running_average_cost(self, trades_backend: SqliteBackend) -> None:
        series = accumulation_series(trades_backend, ALL_TIME)
        averages = [round(b.average_cost_usd, 6) for b in series.basis]
        # 10000, then (0.5*10000 + 0.3*12000) / 0.8, extended to the window end.
        assert averages == [10000.0, 10750.0, 10750.0]
        assert series.basis[-1].when == ALL_TIME.end
        assert series.summary.average_cost_usd == pytest.approx(10750.0)

    def test_trade_points_keep_wallet_and_ledger_id(self, trades_backend: SqliteBackend) -> None:
        series = accumulation_series(trades_backend, ALL_TIME)
        assert [p.btc for p in series.purchases] == pytest.approx([0.5, 0.3])
        sale = series.sales[0]
        assert (sale.side, sale.btc, sale.unit_price_usd, sale.total_usd) == ("sell", 0.1, 15000.0, 1500.0)
        assert sale.wallet == "Coinbase"
        assert isinstance(sale.ledger_id, int)

    def test_purchases_without_usd_price_are_skipped_in_basis(self, backend: SqliteBackend) -> None:
        # EUR trade with no EUR-USD rate: no USD cost is known.
        _ledger(backend, ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "EUR", 4500.0, "Kraken"))
        series = accumulation_series(backend, ALL_TIME)
        assert series.basis == []
        assert series.summary.average_cost_usd is None
        assert series.summary.purchases_missing_cost == 1
        assert series.purchases[0].unit_price_usd is None

    def test_narrow_window_continues_lifetime_basis(self, trades_backend: SqliteBackend) -> None:
        # Basis used to restart from the first in-window purchase.
        window = DateWindow(datetime(2020, 3, 1), datetime(2020, 12, 31))
        series = accumulation_series(trades_backend, window)
        assert series.basis[0].when == window.start
        assert series.basis[0].average_cost_usd == pytest.approx(10000.0)
        assert series.basis[1].average_cost_usd == pytest.approx(10750.0)
        assert [p.btc for p in series.purchases] == pytest.approx([0.3])
        assert series.summary.invested_usd == pytest.approx(8600.0)
        assert series.summary.invested_in_window_usd == pytest.approx(3600.0)

    def test_window_with_only_earlier_purchases_draws_flat_basis(self, trades_backend: SqliteBackend) -> None:
        window = DateWindow(datetime(2021, 1, 1), datetime(2021, 12, 31))
        series = accumulation_series(trades_backend, window)
        assert [(b.when, round(b.average_cost_usd, 6)) for b in series.basis] == [
            (window.start, 10750.0), (window.end, 10750.0),
        ]
        assert series.purchases == []
        assert len(series.sales) == 1

    def test_summary_stops_at_window_end(self, trades_backend: SqliteBackend) -> None:
        window = DateWindow(datetime(2020, 1, 1), datetime(2020, 12, 31))
        summary = accumulation_series(trades_backend, window).summary
        assert (summary.purchase_count, summary.sale_count) == (2, 0)
        assert summary.net_btc == pytest.approx(0.8)

    def test_valuation_prices_holdings(self, trades_backend: SqliteBackend) -> None:
        # Current Value used to price every BTC ever purchased, ignoring sales.
        summary = accumulation_series(trades_backend, ALL_TIME).summary
        holdings = holdings_series(trades_backend, ALL_TIME).latest.total
        valuation = summary.valuation(20000.0, holdings)
        assert holdings == pytest.approx(0.7)
        assert valuation.current_value_usd == pytest.approx(14000.0)
        assert valuation.position_cost_usd == pytest.approx(0.7 * 10750.0)
        assert valuation.unrealized_gain_usd == pytest.approx(14000.0 - 0.7 * 10750.0)
        assert valuation.unrealized_gain_pct == pytest.approx((20000.0 / 10750.0 - 1) * 100)

    def test_valuation_follows_spends(self, trades_backend: SqliteBackend) -> None:
        # A Spend isn't a trade, so net_btc misses it; the balance doesn't.
        _ledger(trades_backend, ("2022-03-01 12:00:00", "Spend", "", 0.0, "BTC", 0.7, "Coinbase"))
        summary = accumulation_series(trades_backend, ALL_TIME).summary
        holdings = holdings_series(trades_backend, ALL_TIME).latest.total
        assert summary.net_btc == pytest.approx(0.7)
        valuation = summary.valuation(20000.0, holdings)
        assert valuation.current_value_usd == pytest.approx(0.0)
        assert valuation.position_cost_usd == pytest.approx(0.0)

    def test_valuation_without_known_cost(self, backend: SqliteBackend) -> None:
        # No USD cost means the basis is unknown, not zero: no gain is invented.
        _ledger(backend, ("2020-01-15 10:00:00", "Trade", "BTC", 0.5, "EUR", 4500.0, "Kraken"))
        valuation = accumulation_series(backend, ALL_TIME).summary.valuation(20000.0, 0.5)
        assert valuation.current_value_usd == pytest.approx(10000.0)
        assert valuation.position_cost_usd is None
        assert valuation.unrealized_gain_usd is None
        assert valuation.unrealized_gain_pct is None

    def test_no_trades(self, backend: SqliteBackend) -> None:
        series = accumulation_series(backend, ALL_TIME)
        assert not series.has_trades
        assert series.basis == []


# ── Price feed ──


class _StubFetcher:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def fetch_btc_price_history(self, start: datetime, end: datetime) -> pd.DataFrame:
        return self.frame


class TestPriceSeries:
    def test_converts_frame_to_sorted_naive_points(self) -> None:
        index = pd.DatetimeIndex(["2020-01-02", "2020-01-01"], tz="UTC")
        frame = pd.DataFrame({"close": [7300.0, 7200.0]}, index=index)
        points = price_series(_StubFetcher(frame), ALL_TIME)
        assert points == [
            PricePoint(datetime(2020, 1, 1), 7200.0),
            PricePoint(datetime(2020, 1, 2), 7300.0),
        ]

    def test_clips_rows_outside_window(self) -> None:
        index = pd.DatetimeIndex(["2018-12-31", "2019-01-01", "2030-01-02"])
        frame = pd.DataFrame({"close": [3700.0, 3800.0, 1.0]}, index=index)
        points = price_series(_StubFetcher(frame), ALL_TIME)
        assert points == [PricePoint(datetime(2019, 1, 1), 3800.0)]

    def test_mid_day_window_keeps_first_days_close(self) -> None:
        frame = pd.DataFrame(
            {"close": [3800.0, 3900.0]},
            index=pd.DatetimeIndex(["2020-01-15", "2020-01-16"]),
        )
        window = DateWindow(datetime(2020, 1, 15, 14, 30), datetime(2020, 2, 1))
        points = price_series(_StubFetcher(frame), window)
        assert points[0] == PricePoint(datetime(2020, 1, 15), 3800.0)

    def test_empty_feed_raises(self) -> None:
        with pytest.raises(RuntimeError, match="No BTC-USD price data available"):
            price_series(_StubFetcher(pd.DataFrame()), ALL_TIME)

    def test_nearest_price(self) -> None:
        prices = [PricePoint(datetime(2020, 1, d), 7000.0 + d) for d in (1, 2, 5)]
        assert nearest_price(prices, datetime(2020, 1, 2, 11)) == 7002.0
        assert nearest_price(prices, datetime(2020, 1, 4)) == 7005.0
        assert nearest_price(prices, datetime(2019, 6, 1)) == 7001.0
        assert nearest_price(prices, datetime(2021, 6, 1)) == 7005.0
        assert nearest_price([], datetime(2020, 1, 1)) == 0.0

"""Regression tests for opening-balance seeding in balance/custody charts.

Narrow date ranges (1Y/YTD/5Y) must start from the holdings actually on hand at
the window's start, not from zero. Transactions before the window are folded
into an opening balance; the "all" range starts before any trade so its opening
is zero (backward compatible).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from viz.balance_chart import BalanceChart
from viz.config import VizConfig
from viz.custody_chart import CustodyChart


@pytest.fixture
def accounts() -> BitcoinAccounts:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    acc = BitcoinAccounts(backend=backend)
    acc.wallet_query.add_wallet(
        wallet_id="Coldcard", wallet_type="hardware",
        custody="self-custodied", description="vault",
    )
    acc.wallet_query.add_wallet(
        wallet_id="Nunchuk", wallet_type="multisig",
        custody="multisig", description="collaborative",
    )
    # 0.30 BTC before the 2022 window, 0.20 BTC after it.
    acc.execute_trade(trade_date=datetime(2021, 2, 10), buy=0.30,
                      sell=10000, exchange="Coldcard")
    acc.execute_trade(trade_date=datetime(2023, 6, 15), buy=0.20,
                      sell=8000, exchange="Nunchuk")
    yield acc
    acc.close()


def _config(start: datetime, end: datetime) -> VizConfig:
    return VizConfig(date_range=(start, end), output_dir="/tmp")


def test_balance_narrow_range_seeds_opening(accounts: BitcoinAccounts) -> None:
    start, end = datetime(2022, 1, 1), datetime(2022, 12, 31)  # no trades in-window
    chart = BalanceChart(accounts.backend, _config(start, end))
    trades = chart.trade_query.get_trades("BTC")
    data = chart._calculate_cumulative_balance(trades, start, end)

    assert data[0]["balance"] == pytest.approx(0.30)   # opening = prior holdings
    assert data[-1]["balance"] == pytest.approx(0.30)  # nothing added in-window


def test_balance_all_range_starts_from_zero(accounts: BitcoinAccounts) -> None:
    start, end = datetime(2020, 1, 1), datetime(2024, 1, 1)  # before any trade
    chart = BalanceChart(accounts.backend, _config(start, end))
    trades = chart.trade_query.get_trades("BTC")
    data = chart._calculate_cumulative_balance(trades, start, end)

    assert data[0]["balance"] == pytest.approx(0.0)
    assert data[-1]["balance"] == pytest.approx(0.50)


def test_custody_narrow_range_seeds_opening(accounts: BitcoinAccounts) -> None:
    start, end = datetime(2022, 1, 1), datetime(2022, 12, 31)
    chart = CustodyChart(accounts.backend, _config(start, end))
    data = chart._get_custody_balances(start, end)

    opening = data[0]
    assert opening["self-custodied"] == pytest.approx(0.30)  # from pre-window buy
    assert opening["multisig"] == pytest.approx(0.0)         # 2023 buy is later
    # No in-window activity, so the closing snapshot matches the opening.
    assert data[-1]["self-custodied"] == pytest.approx(0.30)


def test_custody_all_range_starts_from_zero(accounts: BitcoinAccounts) -> None:
    start, end = datetime(2020, 1, 1), datetime(2024, 1, 1)
    chart = CustodyChart(accounts.backend, _config(start, end))
    data = chart._get_custody_balances(start, end)

    assert data[0]["self-custodied"] == pytest.approx(0.0)
    assert data[0]["multisig"] == pytest.approx(0.0)
    assert data[-1]["self-custodied"] == pytest.approx(0.30)
    assert data[-1]["multisig"] == pytest.approx(0.20)

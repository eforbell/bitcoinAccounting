"""Regression tests for opening-balance seeding in the holdings series.

Narrow date ranges (1Y/YTD/5Y) must start from the holdings actually on hand at
the window's start, not from zero. Transactions before the window are folded
into an opening balance; the "all" range starts before any trade so its opening
is zero (backward compatible). The balance and custody charts both draw this
series.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from viz.series import DateWindow, holdings_series


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


def test_narrow_range_seeds_opening(accounts: BitcoinAccounts) -> None:
    window = DateWindow(datetime(2022, 1, 1), datetime(2022, 12, 31))  # no trades in-window
    points = holdings_series(accounts.backend, window).points

    opening = points[0]
    assert opening.total == pytest.approx(0.30)                      # prior holdings
    assert opening.by_custody["self-custodied"] == pytest.approx(0.30)
    assert opening.by_custody["multisig"] == pytest.approx(0.0)      # 2023 buy is later
    # No in-window activity, so the closing point matches the opening.
    assert points[-1].total == pytest.approx(0.30)
    assert points[-1].by_custody["self-custodied"] == pytest.approx(0.30)


def test_all_range_starts_from_zero(accounts: BitcoinAccounts) -> None:
    window = DateWindow(datetime(2020, 1, 1), datetime(2024, 1, 1))  # before any trade
    points = holdings_series(accounts.backend, window).points

    assert points[0].total == pytest.approx(0.0)
    assert points[-1].total == pytest.approx(0.50)
    assert points[-1].by_custody["self-custodied"] == pytest.approx(0.30)
    assert points[-1].by_custody["multisig"] == pytest.approx(0.20)

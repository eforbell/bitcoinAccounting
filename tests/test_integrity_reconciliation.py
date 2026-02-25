"""Tests for the ledger reconciliation engine (TIF-001)."""

from __future__ import annotations

import pytest

from src.python.db.sqlite import SqliteBackend
from src.python.db.schema import create_tables
from src.python.integrity.reconciliation import (
    CoinSummary,
    CoinWalletBalance,
    ReconciliationEngine,
    ReconciliationResult,
    ReconciliationSnapshot,
    DEFAULT_TOLERANCE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_backend() -> SqliteBackend:
    backend = SqliteBackend(":memory:", auto_create_tables=False)
    create_tables(backend)
    return backend


def _insert_tx(
    backend: SqliteBackend,
    *,
    trans_type: str = "Buy",
    buy: float | None = None,
    buy_curr: str | None = None,
    sell: float | None = None,
    sell_curr: str | None = None,
    fee: float | None = None,
    fee_curr: str | None = None,
    exchange: str = "wallet_a",
    createddate: str = "2025-01-01",
    deleted: int = 0,
) -> None:
    backend.execute(
        """
        INSERT INTO ledger (createddate, trans_type, buy, buy_curr,
                            sell, sell_curr, fee, fee_curr, exchange, deleted)
        VALUES (:createddate, :trans_type, :buy, :buy_curr,
                :sell, :sell_curr, :fee, :fee_curr, :exchange, :deleted)
        """,
        {
            "createddate": createddate,
            "trans_type": trans_type,
            "buy": buy,
            "buy_curr": buy_curr,
            "sell": sell,
            "sell_curr": sell_curr,
            "fee": fee,
            "fee_curr": fee_curr,
            "exchange": exchange,
            "deleted": deleted,
        },
    )
    backend.commit()


# ---------------------------------------------------------------------------
# ReconciliationSnapshot structure
# ---------------------------------------------------------------------------

class TestReconciliationSnapshot:
    def test_snapshot_has_run_id(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        assert isinstance(snap.run_id, str)
        assert len(snap.run_id) == 36  # UUID4 canonical form

    def test_snapshot_has_timestamp(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        assert isinstance(snap.timestamp, str)
        # ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
        assert snap.timestamp.endswith("Z")
        assert "T" in snap.timestamp

    def test_snapshot_has_result(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        assert isinstance(snap.result, ReconciliationResult)

    def test_two_runs_have_different_run_ids(self) -> None:
        backend = _make_backend()
        engine = ReconciliationEngine(backend)
        snap1 = engine.run()
        snap2 = engine.run()
        assert snap1.run_id != snap2.run_id

    def test_result_preserves_filters(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run(
            coin="BTC", wallet="cold_storage",
            start_date="2025-01-01", end_date="2025-12-31",
        )
        assert snap.result.coin_filter == "BTC"
        assert snap.result.wallet_filter == "cold_storage"
        assert snap.result.start_date == "2025-01-01"
        assert snap.result.end_date == "2025-12-31"


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------

class TestEmptyLedger:
    def test_empty_ledger_is_clean(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        assert snap.result.is_clean is True

    def test_empty_ledger_zero_counts(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        r = snap.result
        assert r.total_coins_checked == 0
        assert r.total_wallets_checked == 0
        assert r.discrepancy_count == 0
        assert r.negative_balance_count == 0

    def test_empty_ledger_no_balances_or_summaries(self) -> None:
        backend = _make_backend()
        snap = ReconciliationEngine(backend).run()
        assert snap.result.wallet_balances == []
        assert snap.result.coin_summaries == []


# ---------------------------------------------------------------------------
# Per-wallet balance computation
# ---------------------------------------------------------------------------

class TestWalletBalances:
    def test_single_buy_produces_positive_balance(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="hw_wallet")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        balances = snap.result.wallet_balances

        assert len(balances) == 1
        b = balances[0]
        assert b.coin == "BTC"
        assert b.wallet == "hw_wallet"
        assert abs(b.net_buy - 1.0) < DEFAULT_TOLERANCE
        assert abs(b.net_sell) < DEFAULT_TOLERANCE
        assert abs(b.balance - 1.0) < DEFAULT_TOLERANCE
        assert b.is_negative is False

    def test_sell_reduces_balance(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="exchange_a")
        _insert_tx(backend, sell=0.5, sell_curr="BTC", exchange="exchange_a")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        balances = snap.result.wallet_balances

        assert len(balances) == 1
        assert abs(balances[0].balance - 1.5) < DEFAULT_TOLERANCE

    def test_negative_balance_flagged(self) -> None:
        backend = _make_backend()
        # Sell without any buy — negative balance
        _insert_tx(backend, sell=1.0, sell_curr="BTC", exchange="exchange_a")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        assert snap.result.negative_balance_count == 1
        assert snap.result.wallet_balances[0].is_negative is True
        assert snap.result.is_clean is False

    def test_multiple_wallets_same_coin(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="wallet_b")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        balances = snap.result.wallet_balances

        by_wallet = {b.wallet: b for b in balances}
        assert abs(by_wallet["wallet_a"].balance - 1.0) < DEFAULT_TOLERANCE
        assert abs(by_wallet["wallet_b"].balance - 2.0) < DEFAULT_TOLERANCE

    def test_wallet_filter_restricts_balances(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="wallet_b")

        snap = ReconciliationEngine(backend).run(coin="BTC", wallet="wallet_a")
        balances = snap.result.wallet_balances

        assert len(balances) == 1
        assert balances[0].wallet == "wallet_a"

    def test_deleted_transactions_excluded(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=5.0, buy_curr="BTC", exchange="wallet_a", deleted=1)

        snap = ReconciliationEngine(backend).run(coin="BTC")
        # Soft-deleted tx contributes nothing to balances; result is clean
        assert snap.result.wallet_balances == []
        assert snap.result.negative_balance_count == 0
        assert snap.result.is_clean is True
        # Ledger total for BTC should be zero (deleted rows excluded)
        assert snap.result.coin_summaries[0].ledger_total == 0.0


# ---------------------------------------------------------------------------
# Coin summaries (cross-check)
# ---------------------------------------------------------------------------

class TestCoinSummaries:
    def test_balanced_coin_is_reconciled(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=3.0, buy_curr="BTC", exchange="wallet_a")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        summaries = snap.result.coin_summaries

        assert len(summaries) == 1
        s = summaries[0]
        assert s.coin == "BTC"
        assert s.is_reconciled is True
        assert abs(s.delta) < DEFAULT_TOLERANCE

    def test_summary_wallet_sum_matches_balances(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="wallet_b")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        s = snap.result.coin_summaries[0]
        wallet_sum_from_balances = sum(
            b.balance for b in snap.result.wallet_balances if b.coin == "BTC"
        )
        assert abs(s.wallet_sum - wallet_sum_from_balances) < DEFAULT_TOLERANCE

    def test_reconciled_count_and_discrepancy_count(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        assert snap.result.reconciled_count == 1
        assert snap.result.discrepancy_count == 0

    def test_multiple_coins_summarised_independently(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, buy=10.0, buy_curr="ETH", exchange="wallet_a")

        snap = ReconciliationEngine(backend).run()
        coins = {s.coin for s in snap.result.coin_summaries}
        assert "BTC" in coins
        assert "ETH" in coins
        assert snap.result.total_coins_checked == 2


# ---------------------------------------------------------------------------
# Date range filtering
# ---------------------------------------------------------------------------

class TestDateRangeFiltering:
    def test_start_date_excludes_earlier_transactions(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=10.0, buy_curr="BTC", exchange="w", createddate="2024-12-31")
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="w", createddate="2025-01-15")

        snap = ReconciliationEngine(backend).run(coin="BTC", start_date="2025-01-01")
        balances = snap.result.wallet_balances
        assert len(balances) == 1
        assert abs(balances[0].balance - 1.0) < DEFAULT_TOLERANCE

    def test_end_date_excludes_later_transactions(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="w", createddate="2025-06-01")
        _insert_tx(backend, buy=10.0, buy_curr="BTC", exchange="w", createddate="2025-12-31")

        snap = ReconciliationEngine(backend).run(coin="BTC", end_date="2025-06-30")
        balances = snap.result.wallet_balances
        assert len(balances) == 1
        assert abs(balances[0].balance - 1.0) < DEFAULT_TOLERANCE

    def test_end_date_is_inclusive(self) -> None:
        """Transaction on the end_date itself should be included."""
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="w", createddate="2025-06-30")

        snap = ReconciliationEngine(backend).run(coin="BTC", end_date="2025-06-30")
        assert len(snap.result.wallet_balances) == 1

    def test_date_range_no_transactions_is_clean(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="w", createddate="2024-01-01")

        snap = ReconciliationEngine(backend).run(coin="BTC", start_date="2025-01-01")
        # No transactions in range → empty balances, clean state
        assert snap.result.is_clean is True
        assert snap.result.wallet_balances == []
        assert snap.result.negative_balance_count == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_same_result_values(self) -> None:
        """Two runs on identical data should yield identical result content."""
        backend = _make_backend()
        _insert_tx(backend, buy=1.5, buy_curr="BTC", exchange="cold_storage")

        engine = ReconciliationEngine(backend)
        snap1 = engine.run(coin="BTC")
        snap2 = engine.run(coin="BTC")

        r1, r2 = snap1.result, snap2.result
        assert r1.total_coins_checked == r2.total_coins_checked
        assert r1.total_wallets_checked == r2.total_wallets_checked
        assert r1.is_clean == r2.is_clean
        assert r1.discrepancy_count == r2.discrepancy_count
        assert r1.negative_balance_count == r2.negative_balance_count

        b1 = snap1.result.wallet_balances[0]
        b2 = snap2.result.wallet_balances[0]
        assert b1.coin == b2.coin
        assert b1.wallet == b2.wallet
        assert abs(b1.balance - b2.balance) < DEFAULT_TOLERANCE

    def test_different_data_produces_different_results(self) -> None:
        backend1 = _make_backend()
        _insert_tx(backend1, buy=1.0, buy_curr="BTC", exchange="w")

        backend2 = _make_backend()
        _insert_tx(backend2, buy=2.0, buy_curr="BTC", exchange="w")

        snap1 = ReconciliationEngine(backend1).run(coin="BTC")
        snap2 = ReconciliationEngine(backend2).run(coin="BTC")

        b1 = snap1.result.wallet_balances[0].balance
        b2 = snap2.result.wallet_balances[0].balance
        assert abs(b1 - b2) > DEFAULT_TOLERANCE


# ---------------------------------------------------------------------------
# Custom tolerance
# ---------------------------------------------------------------------------

class TestCustomTolerance:
    def test_wide_tolerance_marks_small_delta_as_reconciled(self) -> None:
        """With a wide tolerance, tiny floating-point differences reconcile."""
        backend = _make_backend()
        # Insert two tiny transactions that produce a negligible balance
        _insert_tx(backend, buy=0.000000001, buy_curr="BTC", exchange="w")

        snap = ReconciliationEngine(backend, tolerance=0.01).run(coin="BTC")
        # Single wallet, no discrepancy possible; mainly checks no error raised
        assert snap.result.is_clean is True


# ---------------------------------------------------------------------------
# Regression: unattributed transactions must not suppress discrepancy signal
# ---------------------------------------------------------------------------

class TestUnattributedWalletRegression:
    def test_null_exchange_excluded_from_wallet_sum(self) -> None:
        """A transaction with no exchange must not silently absorb into wallet_sum.

        Before the fix, NULL-exchange rows were grouped under an empty wallet
        and counted in wallet_sum, making it equal to ledger_total and hiding
        the fact that some transactions lacked wallet attribution.
        """
        backend = _make_backend()
        # Attributed transaction
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        # Unattributed transaction (no exchange value)
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy, buy_curr, deleted)
               VALUES ('2025-01-01', 'Deposit', 0.5, 'BTC', 0)"""
        )
        backend.commit()

        snap = ReconciliationEngine(backend).run(coin="BTC")
        r = snap.result

        # wallet_sum covers only the attributed 1.0; ledger_total is 1.5
        # → delta should be non-zero, coin is NOT reconciled
        btc_summary = next(s for s in r.coin_summaries if s.coin == "BTC")
        assert btc_summary.wallet_sum == pytest.approx(1.0)
        assert btc_summary.ledger_total == pytest.approx(1.5)
        assert not btc_summary.is_reconciled
        assert not r.is_clean

    def test_empty_string_exchange_excluded_from_wallet_sum(self) -> None:
        """An empty-string exchange is also treated as unattributed."""
        backend = _make_backend()
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="wallet_a")
        backend.execute(
            """INSERT INTO ledger (createddate, trans_type, buy, buy_curr,
                                  exchange, deleted)
               VALUES ('2025-01-01', 'Deposit', 1.0, 'BTC', '', 0)"""
        )
        backend.commit()

        snap = ReconciliationEngine(backend).run(coin="BTC")
        btc_summary = next(
            s for s in snap.result.coin_summaries if s.coin == "BTC"
        )
        assert btc_summary.wallet_sum == pytest.approx(2.0)
        assert btc_summary.ledger_total == pytest.approx(3.0)
        assert not btc_summary.is_reconciled

    def test_fully_attributed_ledger_still_reconciles(self) -> None:
        """When every transaction has a wallet, reconciliation must still pass."""
        backend = _make_backend()
        _insert_tx(backend, buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, buy=2.0, buy_curr="BTC", exchange="wallet_b")

        snap = ReconciliationEngine(backend).run(coin="BTC")
        btc_summary = next(
            s for s in snap.result.coin_summaries if s.coin == "BTC"
        )
        assert btc_summary.wallet_sum == pytest.approx(3.0)
        assert btc_summary.is_reconciled
        assert snap.result.is_clean

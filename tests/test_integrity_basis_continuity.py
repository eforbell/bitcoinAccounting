"""Tests for the cost-basis continuity monitor (TIF-003)."""

from __future__ import annotations

import pytest

from src.python.db.sqlite import SqliteBackend
from src.python.db.schema import create_tables
from src.python.integrity.basis_continuity import (
    BasisContinuityMonitor,
    BasisContinuityResult,
    BasisContinuitySnapshot,
    BasisIssue,
    BasisIssueType,
    CoinBasisSummary,
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
    trans_type: str,
    buy: float | None = None,
    buy_curr: str | None = None,
    sell: float | None = None,
    sell_curr: str | None = None,
    fee: float | None = None,
    fee_curr: str | None = None,
    exchange: str = "wallet_a",
    createddate: str = "2025-01-01",
    deleted: int = 0,
) -> int:
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
    row = backend.execute_scalar("SELECT last_insert_rowid()")
    return int(row)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BasisContinuitySnapshot structure
# ---------------------------------------------------------------------------


class TestBasisContinuitySnapshot:
    def test_snapshot_has_run_id(self) -> None:
        snap = BasisContinuityMonitor(_make_backend()).run()
        assert isinstance(snap.run_id, str)
        assert len(snap.run_id) == 36

    def test_snapshot_has_timestamp(self) -> None:
        snap = BasisContinuityMonitor(_make_backend()).run()
        assert snap.timestamp.endswith("Z")
        assert "T" in snap.timestamp

    def test_snapshot_has_result(self) -> None:
        snap = BasisContinuityMonitor(_make_backend()).run()
        assert isinstance(snap.result, BasisContinuityResult)

    def test_two_runs_have_different_run_ids(self) -> None:
        monitor = BasisContinuityMonitor(_make_backend())
        assert monitor.run().run_id != monitor.run().run_id

    def test_result_preserves_filters(self) -> None:
        snap = BasisContinuityMonitor(_make_backend()).run(
            coin="BTC", wallet="cold", start_date="2025-01-01", end_date="2025-12-31"
        )
        r = snap.result
        assert r.coin_filter == "BTC"
        assert r.wallet_filter == "cold"
        assert r.start_date == "2025-01-01"
        assert r.end_date == "2025-12-31"


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------


class TestEmptyLedger:
    def test_empty_is_clean(self) -> None:
        assert BasisContinuityMonitor(_make_backend()).run().result.is_clean is True

    def test_empty_zero_counts(self) -> None:
        r = BasisContinuityMonitor(_make_backend()).run().result
        assert r.total_coins_checked == 0
        assert r.total_issues == 0
        assert r.issues == []
        assert r.coin_summaries == []

    def test_sell_only_no_buy_not_checked(self) -> None:
        """A sell with no buy side should not appear as a coin to check."""
        backend = _make_backend()
        # Only sell, no buy_curr recorded
        _insert_tx(backend, trans_type="Sell",
                   sell=1.0, sell_curr="BTC", exchange="a")
        r = BasisContinuityMonitor(backend).run().result
        # BTC only appears from buy_curr discovery; sell-only rows don't trigger it
        assert r.total_coins_checked == 0


# ---------------------------------------------------------------------------
# Missing cost (Buy/Trade without price)
# ---------------------------------------------------------------------------


class TestMissingCost:
    def test_buy_without_sell_amount_flagged(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   exchange="exchange_a", createddate="2025-01-15")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.is_clean is False
        assert r.missing_cost_count == 1
        issues = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert len(issues) == 1

    def test_buy_without_sell_issue_fields(self) -> None:
        backend = _make_backend()
        tx_id = _insert_tx(backend, trans_type="Buy",
                            buy=0.5, buy_curr="BTC",
                            exchange="exchange_a", createddate="2025-03-10")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issue = next(i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST)
        assert issue.coin == "BTC"
        assert issue.wallet == "exchange_a"
        assert issue.tx_id == tx_id
        assert issue.createddate == "2025-03-10"
        assert issue.trans_type == "Buy"
        assert issue.amount == pytest.approx(0.5, abs=1e-8)
        assert "sell" in issue.remediation_hint.lower() or "cost" in issue.remediation_hint.lower()

    def test_buy_with_sell_amount_not_flagged(self) -> None:
        """Buy with a proper cost (sell=USD) should not be flagged."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   sell=50000.0, sell_curr="USD",
                   exchange="exchange_a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        missing = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert missing == []

    def test_trade_without_cost_flagged(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Trade",
                   buy=0.1, buy_curr="BTC",
                   exchange="exchange_a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issues = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert len(issues) == 1
        assert issues[0].trans_type == "Trade"

    def test_trade_with_cost_not_flagged(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Trade",
                   buy=0.1, buy_curr="BTC",
                   sell=5000.0, sell_curr="USD",
                   exchange="exchange_a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        missing = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert missing == []

    def test_multiple_no_cost_buys(self) -> None:
        backend = _make_backend()
        for i in range(3):
            _insert_tx(backend, trans_type="Buy",
                       buy=float(i + 1), buy_curr="BTC",
                       exchange="exchange_a", createddate=f"2025-0{i+1}-01")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.missing_cost_count == 3

    def test_deleted_no_cost_buy_excluded(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   exchange="a", deleted=1)
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.is_clean is True
        assert r.missing_cost_count == 0


# ---------------------------------------------------------------------------
# Ambiguous source (Deposit / Mining / Reward)
# ---------------------------------------------------------------------------


class TestAmbiguousSource:
    def test_deposit_flagged_as_ambiguous(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.25, buy_curr="BTC",
                   exchange="hw_wallet")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issues = [i for i in r.issues
                  if i.issue_type == BasisIssueType.AMBIGUOUS_SOURCE]
        assert len(issues) == 1
        assert issues[0].trans_type == "Deposit"

    def test_mining_flagged_as_ambiguous(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Mining",
                   buy=0.001, buy_curr="BTC",
                   exchange="mining_pool")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issues = [i for i in r.issues
                  if i.issue_type == BasisIssueType.AMBIGUOUS_SOURCE]
        assert len(issues) == 1
        assert issues[0].trans_type == "Mining"

    def test_reward_flagged_as_ambiguous(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Reward",
                   buy=0.01, buy_curr="BTC",
                   exchange="exchange_a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issues = [i for i in r.issues
                  if i.issue_type == BasisIssueType.AMBIGUOUS_SOURCE]
        assert len(issues) == 1

    def test_ambiguous_source_remediation_hint_mentions_transfer(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC",
                   exchange="wallet_b")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        issue = next(i for i in r.issues
                     if i.issue_type == BasisIssueType.AMBIGUOUS_SOURCE)
        hint = issue.remediation_hint.lower()
        assert "transfer" in hint or "withdrawal" in hint

    def test_ambiguous_source_count(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Mining",
                   buy=0.005, buy_curr="BTC", exchange="b")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.ambiguous_source_count == 2


# ---------------------------------------------------------------------------
# Coverage gap
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_sells_exceed_known_cost_acquisitions(self) -> None:
        """Selling more than was bought with recorded cost → coverage gap."""
        backend = _make_backend()
        # Buy 1 BTC without cost
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        # Buy another 1 BTC with known cost
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   sell=50000.0, sell_curr="USD", exchange="a")
        # Sell 1.5 BTC → gap = 1.5 - 1.0 (known) = 0.5
        _insert_tx(backend, trans_type="Sell",
                   sell=1.5, sell_curr="BTC",
                   buy=75000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        gap_issues = [i for i in r.issues
                      if i.issue_type == BasisIssueType.COVERAGE_GAP]
        assert len(gap_issues) == 1
        assert gap_issues[0].amount == pytest.approx(0.5, abs=1e-6)

    def test_sells_within_known_cost_no_gap(self) -> None:
        """Selling less than was bought with recorded cost → no gap."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=2.0, buy_curr="BTC",
                   sell=100000.0, sell_curr="USD", exchange="a")
        _insert_tx(backend, trans_type="Sell",
                   sell=1.0, sell_curr="BTC",
                   buy=60000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        gap_issues = [i for i in r.issues
                      if i.issue_type == BasisIssueType.COVERAGE_GAP]
        assert gap_issues == []

    def test_no_sells_no_gap(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        gap_issues = [i for i in r.issues
                      if i.issue_type == BasisIssueType.COVERAGE_GAP]
        assert gap_issues == []

    def test_coverage_gap_remediation_hint_contains_amounts(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Sell",
                   sell=0.5, sell_curr="BTC",
                   buy=25000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        gap_issues = [i for i in r.issues
                      if i.issue_type == BasisIssueType.COVERAGE_GAP]
        assert gap_issues
        hint = gap_issues[0].remediation_hint
        assert "BTC" in hint
        assert "0.5" in hint or "gap" in hint.lower()

    def test_coverage_gap_count(self) -> None:
        backend = _make_backend()
        for coin in ("BTC", "ETH"):
            _insert_tx(backend, trans_type="Sell",
                       sell=1.0, sell_curr=coin,
                       buy=1000.0, buy_curr="USD", exchange="a")
        # BTC and ETH both have sells with no acquisition history → gap per coin
        r = BasisContinuityMonitor(backend).run().result
        # The monitor only checks coins with buy_curr records; sells only don't appear
        # Re-insert with buy side to trigger discovery
        backend2 = _make_backend()
        for coin in ("BTC", "ETH"):
            _insert_tx(backend2, trans_type="Buy",
                       buy=0.1, buy_curr=coin, exchange="a")  # no cost
            _insert_tx(backend2, trans_type="Sell",
                       sell=0.5, sell_curr=coin,
                       buy=1000.0, buy_curr="USD", exchange="a")
        r2 = BasisContinuityMonitor(backend2).run().result
        assert r2.coverage_gap_count == 2


# ---------------------------------------------------------------------------
# Coin summaries
# ---------------------------------------------------------------------------


class TestCoinSummaries:
    def test_summary_fields_populated(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=2.0, buy_curr="BTC",
                   sell=100000.0, sell_curr="USD", exchange="a")
        _insert_tx(backend, trans_type="Sell",
                   sell=0.5, sell_curr="BTC",
                   buy=30000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert len(r.coin_summaries) == 1
        s = r.coin_summaries[0]
        assert s.coin == "BTC"
        assert s.total_acquired == pytest.approx(2.0, abs=1e-8)
        assert s.acquired_with_cost == pytest.approx(2.0, abs=1e-8)
        assert s.total_sold == pytest.approx(0.5, abs=1e-8)
        assert s.coverage_gap == pytest.approx(0.0, abs=1e-8)
        assert s.has_gap is False

    def test_summary_has_gap_true_when_sells_exceed_known(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")  # no cost
        _insert_tx(backend, trans_type="Sell",
                   sell=0.8, sell_curr="BTC",
                   buy=40000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        s = r.coin_summaries[0]
        assert s.acquired_with_cost == pytest.approx(0.0, abs=1e-8)
        assert s.has_gap is True
        assert s.coverage_gap == pytest.approx(0.8, abs=1e-6)

    def test_multiple_coins_separate_summaries(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Buy",
                   buy=10.0, buy_curr="ETH", exchange="a")
        r = BasisContinuityMonitor(backend).run().result
        coins = {s.coin for s in r.coin_summaries}
        assert "BTC" in coins
        assert "ETH" in coins
        assert r.total_coins_checked == 2

    def test_summary_missing_cost_count(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")  # no cost
        _insert_tx(backend, trans_type="Buy",
                   buy=2.0, buy_curr="BTC", exchange="a")  # no cost
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        s = r.coin_summaries[0]
        assert s.missing_cost_count == 2


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    def test_coin_filter(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Buy",
                   buy=10.0, buy_curr="ETH", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.total_coins_checked == 1
        assert r.coin_summaries[0].coin == "BTC"

    def test_wallet_filter(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="wallet_a")
        _insert_tx(backend, trans_type="Buy",
                   buy=2.0, buy_curr="BTC", exchange="wallet_b")
        r = BasisContinuityMonitor(backend).run(
            coin="BTC", wallet="wallet_a"
        ).result
        # Only wallet_a row should appear
        issues = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert all(i.wallet == "wallet_a" for i in issues)
        assert len(issues) == 1

    def test_date_start_filter(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=5.0, buy_curr="BTC",
                   exchange="a", createddate="2024-12-31")
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   exchange="a", createddate="2025-01-15")
        r = BasisContinuityMonitor(backend).run(
            coin="BTC", start_date="2025-01-01"
        ).result
        assert r.missing_cost_count == 1
        assert r.issues[0].amount == pytest.approx(1.0, abs=1e-8)

    def test_date_end_filter_inclusive(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC",
                   exchange="a", createddate="2025-06-30")
        _insert_tx(backend, trans_type="Buy",
                   buy=5.0, buy_curr="BTC",
                   exchange="a", createddate="2025-12-31")
        r = BasisContinuityMonitor(backend).run(
            coin="BTC", end_date="2025-06-30"
        ).result
        assert r.missing_cost_count == 1
        assert r.issues[0].amount == pytest.approx(1.0, abs=1e-8)


# ---------------------------------------------------------------------------
# Issue structure
# ---------------------------------------------------------------------------


class TestIssueStructure:
    def test_issue_has_uuid_id(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.issues
        assert len(r.issues[0].issue_id) == 36

    def test_all_issues_are_basis_issue_instances(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.5, buy_curr="BTC", exchange="b")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        for issue in r.issues:
            assert isinstance(issue, BasisIssue)

    def test_issue_types_are_valid(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Sell",
                   sell=0.8, sell_curr="BTC",
                   buy=40000.0, buy_curr="USD", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        valid = set(BasisIssueType)
        for issue in r.issues:
            assert issue.issue_type in valid

    def test_issue_ids_are_unique(self) -> None:
        backend = _make_backend()
        for i in range(3):
            _insert_tx(backend, trans_type="Buy",
                       buy=float(i + 1), buy_curr="BTC",
                       exchange="a", createddate=f"2025-0{i+1}-01")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        ids = [i.issue_id for i in r.issues]
        assert len(ids) == len(set(ids))

    def test_remediation_hint_is_nonempty_string(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        for issue in r.issues:
            assert isinstance(issue.remediation_hint, str)
            assert len(issue.remediation_hint) > 0

    def test_total_issues_matches_issues_list(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy",
                   buy=1.0, buy_curr="BTC", exchange="a")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.5, buy_curr="BTC", exchange="b")
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        assert r.total_issues == len(r.issues)


# ---------------------------------------------------------------------------
# Regression: blank sell_curr must be treated as missing cost
# ---------------------------------------------------------------------------


class TestBlankSellCurrRegression:
    def test_empty_string_sell_curr_flagged_as_missing_cost(self) -> None:
        """A Buy with sell_curr='' must be reported as missing_cost.

        Before the fix the predicate only checked ``sell_curr IS NULL``, so
        rows with an empty string were considered to have valid cost data and
        were silently skipped.
        """
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0, buy_curr="BTC",
            sell=50000.0, sell_curr="",  # blank — cost currency unknown
            exchange="wallet_a",
        )
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        missing = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert len(missing) == 1
        assert missing[0].coin == "BTC"

    def test_null_sell_curr_still_flagged(self) -> None:
        """NULL sell_curr continues to be reported as missing_cost (regression guard)."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=0.5, buy_curr="BTC",
            sell=25000.0, sell_curr=None,
            exchange="wallet_a",
        )
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        missing = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert len(missing) == 1

    def test_valid_sell_curr_not_flagged(self) -> None:
        """A Buy with a real sell_curr must not appear in missing_cost issues."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0, buy_curr="BTC",
            sell=60000.0, sell_curr="USD",
            exchange="wallet_a",
        )
        r = BasisContinuityMonitor(backend).run(coin="BTC").result
        missing = [i for i in r.issues if i.issue_type == BasisIssueType.MISSING_COST]
        assert missing == []

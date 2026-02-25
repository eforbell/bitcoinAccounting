"""Tests for the transfer-pair integrity checker (TIF-002)."""

from __future__ import annotations

import pytest

from src.python.db.sqlite import SqliteBackend
from src.python.db.schema import create_tables
from src.python.integrity.transfer_pairs import (
    DEFAULT_AMOUNT_TOLERANCE,
    DEFAULT_FEE_ANOMALY_THRESHOLD,
    DEFAULT_TIME_WINDOW_HOURS,
    Severity,
    TransferFinding,
    TransferPairChecker,
    TransferPairResult,
    TransferPairSnapshot,
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
# TransferPairSnapshot structure
# ---------------------------------------------------------------------------


class TestTransferPairSnapshot:
    def test_snapshot_has_run_id(self) -> None:
        backend = _make_backend()
        snap = TransferPairChecker(backend).run()
        assert isinstance(snap.run_id, str)
        assert len(snap.run_id) == 36

    def test_snapshot_has_timestamp(self) -> None:
        backend = _make_backend()
        snap = TransferPairChecker(backend).run()
        assert isinstance(snap.timestamp, str)
        assert snap.timestamp.endswith("Z")
        assert "T" in snap.timestamp

    def test_snapshot_has_result(self) -> None:
        backend = _make_backend()
        snap = TransferPairChecker(backend).run()
        assert isinstance(snap.result, TransferPairResult)

    def test_two_runs_have_different_run_ids(self) -> None:
        backend = _make_backend()
        checker = TransferPairChecker(backend)
        snap1 = checker.run()
        snap2 = checker.run()
        assert snap1.run_id != snap2.run_id

    def test_result_preserves_filters(self) -> None:
        backend = _make_backend()
        snap = TransferPairChecker(backend).run(
            coin="BTC",
            wallet="cold_storage",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        r = snap.result
        assert r.coin_filter == "BTC"
        assert r.wallet_filter == "cold_storage"
        assert r.start_date == "2025-01-01"
        assert r.end_date == "2025-12-31"

    def test_result_preserves_tolerance_config(self) -> None:
        backend = _make_backend()
        snap = TransferPairChecker(
            backend,
            time_window_hours=72,
            amount_tolerance=0.005,
            fee_anomaly_threshold=0.10,
        ).run()
        r = snap.result
        assert r.time_window_hours == 72
        assert r.amount_tolerance == 0.005
        assert r.fee_anomaly_threshold == 0.10


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------


class TestEmptyLedger:
    def test_empty_ledger_is_clean(self) -> None:
        snap = TransferPairChecker(_make_backend()).run()
        assert snap.result.is_clean is True

    def test_empty_ledger_zero_counts(self) -> None:
        r = TransferPairChecker(_make_backend()).run().result
        assert r.total_transfers_checked == 0
        assert r.matched_pairs == 0
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0
        assert r.findings == []

    def test_non_transfer_transactions_ignored(self) -> None:
        """Buy/Sell/Trade transactions should not appear in transfer checks."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy", buy=1.0, buy_curr="BTC")
        _insert_tx(backend, trans_type="Sell", sell=0.5, sell_curr="BTC")
        _insert_tx(backend, trans_type="Trade", buy=1.0, buy_curr="BTC",
                   sell=50000.0, sell_curr="USD")
        snap = TransferPairChecker(backend).run()
        assert snap.result.total_transfers_checked == 0
        assert snap.result.is_clean is True


# ---------------------------------------------------------------------------
# Clean matched pairs
# ---------------------------------------------------------------------------


class TestMatchedPairs:
    def test_matched_pair_is_clean(self) -> None:
        """Withdrawal on wallet_a + matching Deposit on wallet_b → clean."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0001, fee_curr="BTC",
                   exchange="wallet_a", createddate="2025-06-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9999, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-06-01")
        snap = TransferPairChecker(backend).run(coin="BTC")
        r = snap.result
        assert r.is_clean is True
        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0
        assert r.findings == []

    def test_total_transfers_checked(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-06-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-06-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.total_transfers_checked == 2

    def test_multiple_clean_pairs(self) -> None:
        backend = _make_backend()
        for i in range(3):
            _insert_tx(backend, trans_type="Withdrawal",
                       sell=float(i + 1), sell_curr="BTC",
                       exchange="wallet_a", createddate=f"2025-0{i+1}-01")
            _insert_tx(backend, trans_type="Deposit",
                       buy=float(i + 1), buy_curr="BTC",
                       exchange="wallet_b", createddate=f"2025-0{i+1}-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.is_clean is True
        assert r.matched_pairs == 3

    def test_deleted_transfers_excluded(self) -> None:
        """Soft-deleted transactions must not contribute to checks."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01",
                   deleted=1)
        snap = TransferPairChecker(backend).run(coin="BTC")
        assert snap.result.total_transfers_checked == 0
        assert snap.result.is_clean is True


# ---------------------------------------------------------------------------
# One-sided send
# ---------------------------------------------------------------------------


class TestOneSidedSend:
    def test_unmatched_send_is_critical(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.is_clean is False
        assert r.unmatched_sends == 1
        assert len(r.findings) >= 1
        critical = [f for f in r.findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 1

    def test_one_sided_send_category(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=2.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        finding = next(f for f in r.findings if f.severity == Severity.CRITICAL)
        assert finding.category == "one_sided_send"
        assert finding.coin == "BTC"
        assert finding.send_wallet == "wallet_a"
        assert finding.receive_wallet is None
        assert finding.send_tx_id is not None
        assert finding.receive_tx_id is None

    def test_unmatched_send_preserves_amount(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=0.5, sell_curr="BTC",
                   exchange="cold", createddate="2025-03-15")
        r = TransferPairChecker(backend).run(coin="BTC").result
        finding = next(f for f in r.findings if f.severity == Severity.CRITICAL)
        assert finding.send_amount == pytest.approx(0.5, abs=1e-8)


# ---------------------------------------------------------------------------
# One-sided receive
# ---------------------------------------------------------------------------


class TestOneSidedReceive:
    def test_unmatched_receive_is_warning(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.is_clean is False
        assert r.unmatched_receives == 1
        warnings = [f for f in r.findings if f.severity == Severity.WARNING]
        assert len(warnings) >= 1

    def test_one_sided_receive_category(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.75, buy_curr="BTC",
                   exchange="hw_wallet", createddate="2025-05-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        finding = next(f for f in r.findings if f.category == "one_sided_receive")
        assert finding.severity == Severity.WARNING
        assert finding.receive_wallet == "hw_wallet"
        assert finding.send_wallet is None
        assert finding.receive_tx_id is not None
        assert finding.send_tx_id is None

    def test_one_sided_receive_preserves_amount(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.12345678, buy_curr="BTC",
                   exchange="exchange", createddate="2025-01-10")
        r = TransferPairChecker(backend).run(coin="BTC").result
        finding = next(f for f in r.findings if f.category == "one_sided_receive")
        assert finding.receive_amount == pytest.approx(0.12345678, abs=1e-8)


# ---------------------------------------------------------------------------
# Amount mismatch
# ---------------------------------------------------------------------------


class TestAmountMismatch:
    def test_large_amount_diff_generates_warning(self) -> None:
        """Matched pair with receive > 1% below expected should be flagged."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0,
                   exchange="wallet_a", createddate="2025-01-01")
        # Receive only 0.98 BTC instead of expected 1.0 (2% shortage)
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.98, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend, amount_tolerance=0.01).run(coin="BTC").result
        assert r.matched_pairs == 1
        mismatch = [f for f in r.findings if f.category == "amount_mismatch"]
        assert len(mismatch) == 1
        assert mismatch[0].severity == Severity.WARNING

    def test_amount_mismatch_finding_fields(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=2.0, sell_curr="BTC", fee=0.0,
                   exchange="hot_wallet", createddate="2025-02-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.9, buy_curr="BTC",
                   exchange="cold_storage", createddate="2025-02-01")
        r = TransferPairChecker(backend, amount_tolerance=0.01).run(coin="BTC").result
        f = next(x for x in r.findings if x.category == "amount_mismatch")
        assert f.send_wallet == "hot_wallet"
        assert f.receive_wallet == "cold_storage"
        assert f.send_amount == pytest.approx(2.0, abs=1e-8)
        assert f.receive_amount == pytest.approx(1.9, abs=1e-8)

    def test_small_amount_diff_within_tolerance_is_clean(self) -> None:
        """Receive that is within tolerance of expected should not be flagged."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0001,
                   exchange="wallet_a", createddate="2025-01-01")
        # Receive exactly gross minus fee = 0.9999
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9999, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        mismatch = [f for f in r.findings if f.category == "amount_mismatch"]
        assert mismatch == []
        assert r.is_clean is True

    def test_amount_mismatches_counter(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0,
                   exchange="a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.8, buy_curr="BTC",
                   exchange="b", createddate="2025-01-01")
        r = TransferPairChecker(backend, amount_tolerance=0.01).run(coin="BTC").result
        assert r.amount_mismatches == 1


# ---------------------------------------------------------------------------
# Fee anomaly
# ---------------------------------------------------------------------------


class TestFeeAnomaly:
    def test_high_fee_ratio_generates_info(self) -> None:
        """Fee above threshold on a matched send should produce INFO finding."""
        backend = _make_backend()
        # 10% fee → above default 5% threshold
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.1, fee_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        fee_findings = [f for f in r.findings if f.category == "fee_anomaly"]
        assert len(fee_findings) == 1
        assert fee_findings[0].severity == Severity.INFO

    def test_fee_anomaly_on_unmatched_send(self) -> None:
        """Fee anomaly should still be reported even when send is unmatched."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.2, fee_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        fee_findings = [f for f in r.findings if f.category == "fee_anomaly"]
        assert len(fee_findings) == 1
        assert fee_findings[0].fee_amount == pytest.approx(0.2, abs=1e-8)

    def test_low_fee_does_not_trigger_anomaly(self) -> None:
        """Fee below threshold should not produce a fee_anomaly finding."""
        backend = _make_backend()
        # 0.01% fee → well below default 5% threshold
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0001, fee_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9999, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        fee_findings = [f for f in r.findings if f.category == "fee_anomaly"]
        assert fee_findings == []

    def test_fee_anomalies_counter(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.1, fee_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.fee_anomalies == 1


# ---------------------------------------------------------------------------
# Time window
# ---------------------------------------------------------------------------


class TestTimeWindow:
    def test_receive_outside_window_not_matched(self) -> None:
        """Deposit 3 days after send exceeds 48h default window → unmatched."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-04")
        r = TransferPairChecker(backend, time_window_hours=48).run(coin="BTC").result
        assert r.matched_pairs == 0
        assert r.unmatched_sends == 1
        assert r.unmatched_receives == 1

    def test_receive_within_extended_window_is_matched(self) -> None:
        """Extending to 96h should match a deposit 3 days after send."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=1.0, buy_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-04")
        r = TransferPairChecker(backend, time_window_hours=96).run(coin="BTC").result
        assert r.matched_pairs == 1
        assert r.is_clean is True

    def test_receive_on_same_day_matched(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=0.5, sell_curr="BTC",
                   exchange="exchange_a", createddate="2025-06-15")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.5, buy_curr="BTC",
                   exchange="exchange_b", createddate="2025-06-15")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.matched_pairs == 1


# ---------------------------------------------------------------------------
# Configurable tolerances
# ---------------------------------------------------------------------------


class TestConfigurableTolerances:
    def test_zero_tolerance_flags_tiny_diff(self) -> None:
        """Strict zero tolerance should flag even a tiny amount difference."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0,
                   exchange="a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.999999, buy_curr="BTC",
                   exchange="b", createddate="2025-01-01")
        r = TransferPairChecker(backend, amount_tolerance=0.0).run(coin="BTC").result
        mismatch = [f for f in r.findings if f.category == "amount_mismatch"]
        assert len(mismatch) == 1

    def test_wide_tolerance_suppresses_mismatch(self) -> None:
        """Wide tolerance (5%) should accept a 2% shortfall as clean."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.0,
                   exchange="a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.98, buy_curr="BTC",
                   exchange="b", createddate="2025-01-01")
        r = TransferPairChecker(backend, amount_tolerance=0.05).run(coin="BTC").result
        mismatch = [f for f in r.findings if f.category == "amount_mismatch"]
        assert mismatch == []

    def test_custom_fee_anomaly_threshold(self) -> None:
        """Raising threshold to 15% should suppress a 10% fee finding."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.1, fee_curr="BTC",
                   exchange="a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.9, buy_curr="BTC",
                   exchange="b", createddate="2025-01-01")
        r = TransferPairChecker(
            backend, fee_anomaly_threshold=0.15
        ).run(coin="BTC").result
        fee_findings = [f for f in r.findings if f.category == "fee_anomaly"]
        assert fee_findings == []


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    def test_coin_filter(self) -> None:
        """coin='ETH' filter should ignore BTC transfers."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="ETH").result
        assert r.total_transfers_checked == 0
        assert r.is_clean is True

    def test_wallet_filter_send(self) -> None:
        """Wallet filter restricts send-side to matching wallet only."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="wallet_a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=2.0, sell_curr="BTC",
                   exchange="wallet_b", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC", wallet="wallet_a").result
        # Only wallet_a send is checked
        assert r.unmatched_sends == 1
        f = next(x for x in r.findings if x.category == "one_sided_send")
        assert f.send_wallet == "wallet_a"

    def test_date_range_start(self) -> None:
        """start_date should exclude earlier transfers."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=5.0, sell_curr="BTC",
                   exchange="a", createddate="2024-12-31")
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="a", createddate="2025-01-15")
        r = TransferPairChecker(backend).run(
            coin="BTC", start_date="2025-01-01"
        ).result
        assert r.unmatched_sends == 1
        f = next(x for x in r.findings if x.category == "one_sided_send")
        assert f.send_amount == pytest.approx(1.0, abs=1e-8)

    def test_date_range_end(self) -> None:
        """end_date should exclude later transfers (inclusive end)."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="a", createddate="2025-06-30")
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=5.0, sell_curr="BTC",
                   exchange="a", createddate="2025-12-31")
        r = TransferPairChecker(backend).run(
            coin="BTC", end_date="2025-06-30"
        ).result
        assert r.unmatched_sends == 1
        f = next(x for x in r.findings if x.category == "one_sided_send")
        assert f.send_amount == pytest.approx(1.0, abs=1e-8)

    def test_end_date_is_inclusive(self) -> None:
        """Transfer on the end_date itself should be included."""
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="a", createddate="2025-06-30")
        r = TransferPairChecker(backend).run(
            coin="BTC", end_date="2025-06-30"
        ).result
        assert r.unmatched_sends == 1


# ---------------------------------------------------------------------------
# Finding structure
# ---------------------------------------------------------------------------


class TestFindingStructure:
    def test_finding_has_uuid_id(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC",
                   exchange="a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.findings
        f = r.findings[0]
        assert isinstance(f.finding_id, str)
        assert len(f.finding_id) == 36

    def test_all_findings_are_transfer_finding_instances(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.1,
                   exchange="a", createddate="2025-01-01")
        _insert_tx(backend, trans_type="Deposit",
                   buy=0.8, buy_curr="BTC",
                   exchange="b", createddate="2025-01-01")
        r = TransferPairChecker(backend, amount_tolerance=0.01).run(coin="BTC").result
        for finding in r.findings:
            assert isinstance(finding, TransferFinding)

    def test_severity_values_are_valid(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal",
                   sell=1.0, sell_curr="BTC", fee=0.1,
                   exchange="a", createddate="2025-01-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        valid = {Severity.INFO, Severity.WARNING, Severity.CRITICAL}
        for finding in r.findings:
            assert finding.severity in valid

    def test_findings_unique_ids(self) -> None:
        """All findings in a single run must have distinct IDs."""
        backend = _make_backend()
        for i in range(3):
            _insert_tx(backend, trans_type="Withdrawal",
                       sell=float(i + 1), sell_curr="BTC",
                       exchange="a", createddate=f"2025-0{i+1}-01")
        r = TransferPairChecker(backend).run(coin="BTC").result
        ids = [f.finding_id for f in r.findings]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Regression: cross-currency fee must not corrupt coin matching expectation
# ---------------------------------------------------------------------------

class TestCrossCurrencyFeeRegression:
    def test_usd_fee_on_btc_transfer_does_not_block_match(self) -> None:
        """A USD-denominated fee on a BTC transfer must not affect BTC matching.

        Before the fix, expected_receive = gross_send - fee subtracted the USD
        fee from the BTC amount, producing an absurd expectation (e.g. -9 BTC)
        that caused a valid pair to be rejected as one_sided_send.
        """
        backend = _make_backend()
        # Send 1 BTC with a $10 USD fee — receive should be the full 1 BTC
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0, sell_curr="BTC",
            fee=10.0, fee_curr="USD",
            exchange="wallet_a",
            createddate="2025-01-01",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=1.0, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-01-01",
        )

        r = TransferPairChecker(backend).run(coin="BTC").result

        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0
        assert r.is_clean

    def test_usd_fee_does_not_trigger_false_fee_anomaly(self) -> None:
        """A cross-currency fee must not generate a fee_anomaly finding."""
        backend = _make_backend()
        # Fee is 100 USD on a 1 BTC send — ratio is meaningless across currencies
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0, sell_curr="BTC",
            fee=100.0, fee_curr="USD",
            exchange="wallet_a",
            createddate="2025-01-01",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=1.0, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-01-01",
        )

        r = TransferPairChecker(backend).run(coin="BTC").result

        assert r.fee_anomalies == 0
        fee_anomaly_findings = [
            f for f in r.findings if f.category == "fee_anomaly"
        ]
        assert fee_anomaly_findings == []

    def test_btc_fee_on_btc_transfer_still_applied(self) -> None:
        """A same-currency fee must still be subtracted from expected receive."""
        backend = _make_backend()
        # Send 1.0 BTC with 0.001 BTC fee → expect 0.999 BTC to arrive
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0, sell_curr="BTC",
            fee=0.001, fee_curr="BTC",
            exchange="wallet_a",
            createddate="2025-01-01",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=0.999, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-01-01",
        )

        r = TransferPairChecker(backend).run(coin="BTC").result

        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.is_clean

    def test_none_fee_curr_treated_as_coin_currency(self) -> None:
        """A fee with no fee_curr (legacy records) is assumed to be in the transfer coin."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0, sell_curr="BTC",
            fee=0.001, fee_curr=None,
            exchange="wallet_a",
            createddate="2025-01-01",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=0.999, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-01-01",
        )

        r = TransferPairChecker(backend).run(coin="BTC").result

        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0


# ---------------------------------------------------------------------------
# Regression: fractional-second timestamps must not drop time precision
# ---------------------------------------------------------------------------


class TestFractionalSecondTimestampRegression:
    def test_space_separated_fractional_second_matched_within_window(self) -> None:
        """Timestamps like '2025-01-01 10:00:00.123456' must parse with full precision.

        Before the fix, _parse_date() fell back to date_str[:10] for these
        formats, truncating all time information.
        """
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0, sell_curr="BTC",
            exchange="wallet_a",
            createddate="2025-01-01 10:00:00.500000",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=1.0, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-01-01 10:00:01.000000",
        )
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0

    def test_iso_fractional_second_matched_within_window(self) -> None:
        """ISO-format fractional timestamps ('2025-01-01T10:00:00.5') parse correctly."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=0.5, sell_curr="BTC",
            exchange="wallet_a",
            createddate="2025-06-15T08:30:00.123456",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=0.5, buy_curr="BTC",
            exchange="wallet_b",
            createddate="2025-06-15T08:30:02.000000",
        )
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0

    def test_z_suffix_utc_timestamp_matched_within_window(self) -> None:
        """Timestamps ending in 'Z' (e.g. '2021-04-08T19:18:37.381Z') parse correctly.

        Before the fix, the 'Z' suffix caused all format matches to fail and
        the parser fell back to date_str[:10], discarding all time information.
        """
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=0.02, sell_curr="BTC",
            exchange="CC",
            createddate="2021-04-08T19:18:37.381Z",
        )
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=0.02, buy_curr="BTC",
            exchange="Ledger",
            createddate="2021-04-08T20:00:00.000Z",
        )
        r = TransferPairChecker(backend).run(coin="BTC").result
        assert r.matched_pairs == 1
        assert r.unmatched_sends == 0
        assert r.unmatched_receives == 0

"""Tests for the treasury health score and policy thresholds (TIF-004)."""

from __future__ import annotations

import pytest

from src.python.db.schema import create_tables
from src.python.db.sqlite import SqliteBackend
from src.python.integrity.basis_continuity import BasisContinuityMonitor
from src.python.integrity.health_score import (
    DEFAULT_CRITICAL_MIN,
    DEFAULT_WEIGHTS,
    DEFAULT_WARNING_MIN,
    HealthScoreResult,
    HealthScoreSnapshot,
    HealthThresholds,
    HealthTier,
    SubScore,
    TreasuryHealthScorer,
)
from src.python.integrity.reconciliation import ReconciliationEngine
from src.python.integrity.transfer_pairs import TransferPairChecker


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _run_all_checks(backend: SqliteBackend) -> HealthScoreSnapshot:
    """Run all three integrity checks and return a health score snapshot."""
    recon_snap = ReconciliationEngine(backend).run()
    transfer_snap = TransferPairChecker(backend).run()
    basis_snap = BasisContinuityMonitor(backend).run()
    return TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)


# ---------------------------------------------------------------------------
# HealthScoreSnapshot structure
# ---------------------------------------------------------------------------


class TestHealthScoreSnapshotStructure:
    def test_snapshot_has_run_id(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.run_id, str)
        assert len(snap.run_id) == 36

    def test_snapshot_has_timestamp(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.timestamp, str)
        assert snap.timestamp.endswith("Z")
        assert "T" in snap.timestamp

    def test_snapshot_has_result(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.result, HealthScoreResult)

    def test_result_has_three_sub_scores(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert len(snap.result.sub_scores) == 3

    def test_sub_score_names(self) -> None:
        snap = _run_all_checks(_make_backend())
        names = {s.name for s in snap.result.sub_scores}
        assert names == {"reconciliation", "transfer_integrity", "basis_continuity"}

    def test_sub_scores_are_subscore_instances(self) -> None:
        snap = _run_all_checks(_make_backend())
        for s in snap.result.sub_scores:
            assert isinstance(s, SubScore)

    def test_result_has_overall_score(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.result.overall_score, float)

    def test_result_has_tier(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.result.tier, HealthTier)

    def test_result_has_thresholds(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert isinstance(snap.result.thresholds, HealthThresholds)

    def test_result_has_source_run_ids(self) -> None:
        backend = _make_backend()
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        score_snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        assert score_snap.result.recon_run_id == recon_snap.run_id
        assert score_snap.result.transfer_run_id == transfer_snap.run_id
        assert score_snap.result.basis_run_id == basis_snap.run_id

    def test_each_run_produces_unique_run_id(self) -> None:
        backend = _make_backend()
        snap1 = _run_all_checks(backend)
        snap2 = _run_all_checks(backend)
        assert snap1.run_id != snap2.run_id


# ---------------------------------------------------------------------------
# Clean ledger — perfect score
# ---------------------------------------------------------------------------


class TestCleanLedgerScore:
    def test_empty_ledger_overall_score_is_100(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert snap.result.overall_score == 100.0

    def test_empty_ledger_tier_is_healthy(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert snap.result.tier == HealthTier.HEALTHY

    def test_empty_ledger_all_sub_scores_100(self) -> None:
        snap = _run_all_checks(_make_backend())
        for s in snap.result.sub_scores:
            assert s.value == 100.0

    def test_buy_then_sell_roundtrip_score_is_100(self) -> None:
        """Buy 1 BTC for USD, then sell 1 BTC for USD — perfectly balanced."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
            exchange="coinbase",
        )
        # Sell same BTC back via a Trade → balances net to zero
        _insert_tx(
            backend,
            trans_type="Trade",
            sell=1.0,
            sell_curr="BTC",
            buy=55000.0,
            buy_curr="USD",
            exchange="coinbase",
        )
        snap = _run_all_checks(backend)
        assert snap.result.overall_score == 100.0
        assert snap.result.tier == HealthTier.HEALTHY


# ---------------------------------------------------------------------------
# Reconciliation sub-score
# ---------------------------------------------------------------------------


class TestReconciliationSubScore:
    def test_discrepancy_lowers_recon_score(self) -> None:
        """Negative balance (USD spend) reduces recon sub-score below 100."""
        backend = _make_backend()
        # A Buy depletes fiat → USD wallet goes negative in reconciliation
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
            exchange="wallet_a",
        )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        score_snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        # USD balance is negative → negative_balance_count > 0 → penalty applied
        assert recon_snap.result.negative_balance_count > 0
        recon_sub = next(
            s for s in score_snap.result.sub_scores if s.name == "reconciliation"
        )
        assert recon_sub.value < 100.0
        assert recon_sub.details["negative_balance_count"] > 0

    def test_recon_sub_score_details_populated(self) -> None:
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
        )
        snap = _run_all_checks(backend)
        recon_sub = next(
            s for s in snap.result.sub_scores if s.name == "reconciliation"
        )
        assert "total_coins_checked" in recon_sub.details
        assert "reconciled_count" in recon_sub.details
        assert "discrepancy_count" in recon_sub.details
        assert "negative_balance_count" in recon_sub.details
        assert "is_clean" in recon_sub.details

    def test_recon_sub_score_uses_configured_weight(self) -> None:
        custom = HealthThresholds(
            weights={"reconciliation": 0.5, "transfer_integrity": 0.3, "basis_continuity": 0.2}
        )
        backend = _make_backend()
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer(thresholds=custom).score(
            recon_snap, transfer_snap, basis_snap
        )
        recon_sub = next(
            s for s in snap.result.sub_scores if s.name == "reconciliation"
        )
        assert recon_sub.weight == 0.5


# ---------------------------------------------------------------------------
# Transfer integrity sub-score
# ---------------------------------------------------------------------------


class TestTransferIntegritySubScore:
    def test_unmatched_send_lowers_transfer_score(self) -> None:
        """An unmatched send creates a CRITICAL finding → penalty 15 pts."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0,
            sell_curr="BTC",
            exchange="wallet_a",
        )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        transfer_sub = next(
            s for s in snap.result.sub_scores if s.name == "transfer_integrity"
        )
        assert transfer_sub.value < 100.0
        assert transfer_sub.details["critical_findings"] >= 1

    def test_transfer_sub_score_details_populated(self) -> None:
        snap = _run_all_checks(_make_backend())
        transfer_sub = next(
            s for s in snap.result.sub_scores if s.name == "transfer_integrity"
        )
        assert "total_transfers_checked" in transfer_sub.details
        assert "matched_pairs" in transfer_sub.details
        assert "unmatched_sends" in transfer_sub.details
        assert "unmatched_receives" in transfer_sub.details
        assert "critical_findings" in transfer_sub.details
        assert "warning_findings" in transfer_sub.details
        assert "fee_anomalies" in transfer_sub.details
        assert "is_clean" in transfer_sub.details

    def test_five_unmatched_sends_caps_at_75_penalty(self) -> None:
        """Five CRITICALs = 5 × 15 = 75 pts penalty → score == 25.0."""
        backend = _make_backend()
        for _ in range(5):
            _insert_tx(
                backend,
                trans_type="Withdrawal",
                sell=1.0,
                sell_curr="BTC",
                exchange="wallet_a",
            )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        transfer_sub = next(
            s for s in snap.result.sub_scores if s.name == "transfer_integrity"
        )
        assert transfer_sub.value == 25.0

    def test_six_unmatched_sends_score_capped_not_below_zero(self) -> None:
        """Six CRITICALs would be 90 pts but cap is 75 → score still 25.0."""
        backend = _make_backend()
        for _ in range(6):
            _insert_tx(
                backend,
                trans_type="Withdrawal",
                sell=1.0,
                sell_curr="BTC",
                exchange="wallet_a",
            )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        transfer_sub = next(
            s for s in snap.result.sub_scores if s.name == "transfer_integrity"
        )
        assert transfer_sub.value == 25.0


# ---------------------------------------------------------------------------
# Basis continuity sub-score
# ---------------------------------------------------------------------------


class TestBasisContinuitySubScore:
    def test_missing_cost_lowers_basis_score(self) -> None:
        """A Buy with no sell amount → MISSING_COST issue → 3 pt penalty."""
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            # no sell → missing cost
        )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        basis_sub = next(
            s for s in snap.result.sub_scores if s.name == "basis_continuity"
        )
        assert basis_sub.value < 100.0
        assert basis_sub.details["missing_cost_count"] >= 1

    def test_basis_sub_score_details_populated(self) -> None:
        snap = _run_all_checks(_make_backend())
        basis_sub = next(
            s for s in snap.result.sub_scores if s.name == "basis_continuity"
        )
        assert "total_coins_checked" in basis_sub.details
        assert "total_issues" in basis_sub.details
        assert "missing_cost_count" in basis_sub.details
        assert "ambiguous_source_count" in basis_sub.details
        assert "coverage_gap_count" in basis_sub.details
        assert "is_clean" in basis_sub.details

    def test_three_coverage_gaps_caps_at_60_penalty(self) -> None:
        """Three coverage gaps = 3 × 20 = 60 pts penalty → score == 40.0."""
        backend = _make_backend()
        # Add sells without corresponding priced buys for 3 different coins
        for coin in ("BTC", "ETH", "LTC"):
            _insert_tx(
                backend,
                trans_type="Buy",
                buy=0.1,
                buy_curr=coin,
                sell=100.0,
                sell_curr="USD",
            )
            # Sell more than was priced-acquired → coverage gap
            _insert_tx(
                backend,
                trans_type="Trade",
                sell=5.0,
                sell_curr=coin,
                buy=500.0,
                buy_curr="USD",
            )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer().score(recon_snap, transfer_snap, basis_snap)
        basis_sub = next(
            s for s in snap.result.sub_scores if s.name == "basis_continuity"
        )
        assert basis_sub.value == 40.0


# ---------------------------------------------------------------------------
# Weighted aggregate score
# ---------------------------------------------------------------------------


class TestWeightedAggregate:
    def test_overall_score_is_weighted_sum_of_sub_scores(self) -> None:
        """Verify the overall score equals the manual weighted sum."""
        snap = _run_all_checks(_make_backend())
        expected = sum(s.value * s.weight for s in snap.result.sub_scores)
        assert abs(snap.result.overall_score - round(expected, 4)) < 1e-6

    def test_default_weights_sum_to_one(self) -> None:
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_custom_weights_affect_overall_score(self) -> None:
        """Different weights → different overall score for same sub-scores."""
        backend = _make_backend()
        # Create a situation where sub-scores differ
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=1.0,
            sell_curr="BTC",
            exchange="wallet_a",
        )
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()

        snap_default = TreasuryHealthScorer().score(
            recon_snap, transfer_snap, basis_snap
        )
        # Heavily weight transfer_integrity
        heavy_transfer = HealthThresholds(
            weights={"reconciliation": 0.1, "transfer_integrity": 0.8, "basis_continuity": 0.1}
        )
        snap_heavy = TreasuryHealthScorer(thresholds=heavy_transfer).score(
            recon_snap, transfer_snap, basis_snap
        )
        # Transfer had a critical finding → heavy weighting → lower overall score
        assert snap_heavy.result.overall_score < snap_default.result.overall_score

    def test_overall_score_bounded_0_to_100(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert 0.0 <= snap.result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Health tier classification
# ---------------------------------------------------------------------------


class TestHealthTierClassification:
    def test_default_thresholds(self) -> None:
        thresholds = HealthThresholds()
        assert thresholds.warning_min == DEFAULT_WARNING_MIN
        assert thresholds.critical_min == DEFAULT_CRITICAL_MIN

    def test_score_at_warning_min_is_healthy(self) -> None:
        thresholds = HealthThresholds(warning_min=80.0, critical_min=60.0)
        scorer = TreasuryHealthScorer(thresholds=thresholds)
        assert scorer._classify(80.0) == HealthTier.HEALTHY

    def test_score_above_warning_min_is_healthy(self) -> None:
        scorer = TreasuryHealthScorer()
        assert scorer._classify(95.0) == HealthTier.HEALTHY

    def test_score_just_below_warning_min_is_warning(self) -> None:
        thresholds = HealthThresholds(warning_min=80.0, critical_min=60.0)
        scorer = TreasuryHealthScorer(thresholds=thresholds)
        assert scorer._classify(79.9) == HealthTier.WARNING

    def test_score_at_critical_min_is_warning(self) -> None:
        thresholds = HealthThresholds(warning_min=80.0, critical_min=60.0)
        scorer = TreasuryHealthScorer(thresholds=thresholds)
        assert scorer._classify(60.0) == HealthTier.WARNING

    def test_score_just_below_critical_min_is_critical(self) -> None:
        thresholds = HealthThresholds(warning_min=80.0, critical_min=60.0)
        scorer = TreasuryHealthScorer(thresholds=thresholds)
        assert scorer._classify(59.9) == HealthTier.CRITICAL

    def test_score_zero_is_critical(self) -> None:
        scorer = TreasuryHealthScorer()
        assert scorer._classify(0.0) == HealthTier.CRITICAL

    def test_custom_thresholds_affect_tier(self) -> None:
        """With warning_min=50, a score of 60 should be HEALTHY."""
        thresholds = HealthThresholds(warning_min=50.0, critical_min=30.0)
        scorer = TreasuryHealthScorer(thresholds=thresholds)
        assert scorer._classify(60.0) == HealthTier.HEALTHY

    def test_empty_ledger_tier_is_healthy(self) -> None:
        snap = _run_all_checks(_make_backend())
        assert snap.result.tier == HealthTier.HEALTHY

    def test_tier_enum_values(self) -> None:
        assert HealthTier.HEALTHY.value == "healthy"
        assert HealthTier.WARNING.value == "warning"
        assert HealthTier.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------


class TestSnapshotPersistence:
    def test_persist_requires_backend(self) -> None:
        snap = _run_all_checks(_make_backend())
        scorer = TreasuryHealthScorer()  # no backend
        with pytest.raises(RuntimeError, match="database backend"):
            scorer.persist(snap)

    def test_load_snapshots_requires_backend(self) -> None:
        scorer = TreasuryHealthScorer()
        with pytest.raises(RuntimeError, match="database backend"):
            scorer.load_snapshots()

    def test_persist_and_load_single_snapshot(self) -> None:
        backend = _make_backend()
        snap = _run_all_checks(backend)
        scorer = TreasuryHealthScorer(backend=backend)
        scorer.persist(snap)

        rows = scorer.load_snapshots()
        assert len(rows) == 1
        assert rows[0]["run_id"] == snap.run_id
        assert rows[0]["overall_score"] == snap.result.overall_score
        assert rows[0]["tier"] == snap.result.tier.value

    def test_persist_stores_sub_scores(self) -> None:
        backend = _make_backend()
        snap = _run_all_checks(backend)
        scorer = TreasuryHealthScorer(backend=backend)
        scorer.persist(snap)

        rows = scorer.load_snapshots()
        row = rows[0]
        assert "recon_score" in row
        assert "transfer_score" in row
        assert "basis_score" in row
        assert row["recon_score"] == 100.0
        assert row["transfer_score"] == 100.0
        assert row["basis_score"] == 100.0

    def test_persist_stores_thresholds(self) -> None:
        backend = _make_backend()
        thresholds = HealthThresholds(warning_min=75.0, critical_min=50.0)
        recon_snap = ReconciliationEngine(backend).run()
        transfer_snap = TransferPairChecker(backend).run()
        basis_snap = BasisContinuityMonitor(backend).run()
        snap = TreasuryHealthScorer(thresholds=thresholds).score(
            recon_snap, transfer_snap, basis_snap
        )
        scorer = TreasuryHealthScorer(thresholds=thresholds, backend=backend)
        scorer.persist(snap)

        rows = scorer.load_snapshots()
        assert rows[0]["warning_min"] == 75.0
        assert rows[0]["critical_min"] == 50.0

    def test_load_snapshots_ordered_most_recent_first(self) -> None:
        backend = _make_backend()
        scorer = TreasuryHealthScorer(backend=backend)

        for ts in ("2025-01-01T00:00:00Z", "2025-06-15T12:00:00Z", "2025-12-31T23:59:00Z"):
            snap = _run_all_checks(backend)
            # Patch the timestamp for ordering test
            from dataclasses import replace
            snap = replace(snap, timestamp=ts)
            scorer.persist(snap)

        rows = scorer.load_snapshots()
        assert len(rows) == 3
        assert rows[0]["timestamp"] == "2025-12-31T23:59:00Z"
        assert rows[1]["timestamp"] == "2025-06-15T12:00:00Z"
        assert rows[2]["timestamp"] == "2025-01-01T00:00:00Z"

    def test_load_snapshots_limit_respected(self) -> None:
        backend = _make_backend()
        scorer = TreasuryHealthScorer(backend=backend)
        for _ in range(5):
            scorer.persist(_run_all_checks(backend))
        rows = scorer.load_snapshots(limit=3)
        assert len(rows) == 3

    def test_persist_is_idempotent_on_separate_snaps(self) -> None:
        """Two separate snapshots can be persisted independently."""
        backend = _make_backend()
        scorer = TreasuryHealthScorer(backend=backend)
        scorer.persist(_run_all_checks(backend))
        scorer.persist(_run_all_checks(backend))
        rows = scorer.load_snapshots()
        assert len(rows) == 2

    def test_persist_duplicate_run_id_raises(self) -> None:
        """Persisting the same snapshot twice should raise (UNIQUE constraint)."""
        backend = _make_backend()
        scorer = TreasuryHealthScorer(backend=backend)
        snap = _run_all_checks(backend)
        scorer.persist(snap)
        with pytest.raises(Exception):
            scorer.persist(snap)

    def test_table_exists_after_create_tables(self) -> None:
        """integrity_health_snapshots is part of the standard schema."""
        backend = _make_backend()
        tables = backend.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='integrity_health_snapshots'"
        )
        assert len(tables) == 1

    def test_persist_inserts_a_row(self) -> None:
        """persist() stores exactly one row per snapshot."""
        backend = _make_backend()
        scorer = TreasuryHealthScorer(backend=backend)
        scorer.persist(_run_all_checks(backend))

        rows = backend.execute("SELECT run_id FROM integrity_health_snapshots")
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# HealthThresholds defaults
# ---------------------------------------------------------------------------


class TestHealthThresholdsDefaults:
    def test_default_warning_min(self) -> None:
        assert HealthThresholds().warning_min == 80.0

    def test_default_critical_min(self) -> None:
        assert HealthThresholds().critical_min == 60.0

    def test_default_weights_match_module_constants(self) -> None:
        t = HealthThresholds()
        assert t.weights == DEFAULT_WEIGHTS

    def test_default_weights_are_independent_copies(self) -> None:
        """Modifying one instance's weights should not affect another."""
        t1 = HealthThresholds()
        t2 = HealthThresholds()
        t1.weights["reconciliation"] = 0.99
        assert t2.weights["reconciliation"] == DEFAULT_WEIGHTS["reconciliation"]

    def test_custom_thresholds_persisted(self) -> None:
        t = HealthThresholds(warning_min=70.0, critical_min=40.0)
        assert t.warning_min == 70.0
        assert t.critical_min == 40.0

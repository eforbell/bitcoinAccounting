"""Treasury health score and policy thresholds (TIF-004).

Computes a weighted aggregate health score from reconciliation,
transfer-pair integrity, and basis-continuity snapshots.  Supports
configurable thresholds for HEALTHY/WARNING/CRITICAL tier classification
and optional snapshot persistence for trend tracking.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from .transfer_pairs import Severity

if TYPE_CHECKING:
    from ..db.backend import DatabaseBackend
    from .basis_continuity import BasisContinuitySnapshot
    from .reconciliation import ReconciliationSnapshot
    from .transfer_pairs import TransferPairSnapshot

# Default sub-score weights (must sum to 1.0)
DEFAULT_WEIGHTS: dict[str, float] = {
    "reconciliation": 0.40,
    "transfer_integrity": 0.35,
    "basis_continuity": 0.25,
}

# Default threshold values
DEFAULT_WARNING_MIN: float = 80.0
DEFAULT_CRITICAL_MIN: float = 60.0


class HealthTier(str, Enum):
    """Health tier classification for the overall treasury score."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthThresholds:
    """Configurable thresholds and weights for health score tiers.

    Attributes:
        warning_min: Minimum score for HEALTHY tier (default 80.0).
            Scores between ``critical_min`` and ``warning_min`` are WARNING.
        critical_min: Minimum score for WARNING tier (default 60.0).
            Scores below this are CRITICAL.
        weights: Per-component weight mapping.  Keys must include
            ``"reconciliation"``, ``"transfer_integrity"``, and
            ``"basis_continuity"``.  Values should sum to 1.0.
    """

    warning_min: float = DEFAULT_WARNING_MIN
    critical_min: float = DEFAULT_CRITICAL_MIN
    weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )


@dataclass
class SubScore:
    """Score for a single integrity component.

    Attributes:
        name: Component name (``"reconciliation"``, ``"transfer_integrity"``,
            or ``"basis_continuity"``).
        value: Score from 0.0 to 100.0 (100 = perfect).
        weight: Weight applied to this sub-score in the aggregate.
        details: Key metrics used to compute this sub-score.
    """

    name: str
    value: float
    weight: float
    details: dict[str, Any]


@dataclass
class HealthScoreResult:
    """Full treasury health score result.

    Attributes:
        sub_scores: Sub-scores for each integrity component.
        overall_score: Weighted aggregate score (0.0–100.0).
        tier: Overall health tier based on thresholds.
        thresholds: Thresholds used for tier classification.
        recon_run_id: Run ID of the reconciliation snapshot consumed.
        transfer_run_id: Run ID of the transfer-pair snapshot consumed.
        basis_run_id: Run ID of the basis-continuity snapshot consumed.
    """

    sub_scores: list[SubScore]
    overall_score: float
    tier: HealthTier
    thresholds: HealthThresholds
    recon_run_id: str
    transfer_run_id: str
    basis_run_id: str


@dataclass
class HealthScoreSnapshot:
    """Immutable timestamped snapshot of a health score result.

    Attributes:
        run_id: Unique identifier (UUID4).
        timestamp: ISO 8601 UTC timestamp.
        result: Underlying health score result.
    """

    run_id: str
    timestamp: str
    result: HealthScoreResult


class TreasuryHealthScorer:
    """Compute and persist treasury health scores.

    Accepts pre-computed snapshots from the three integrity checkers and
    produces a weighted :class:`HealthScoreSnapshot`.  Optionally persists
    snapshots to the database for trend tracking.

    Args:
        thresholds: Health tier thresholds and sub-score weights.  Uses
            :class:`HealthThresholds` defaults when not provided.
        backend: Optional database backend for snapshot persistence.
    """

    def __init__(
        self,
        thresholds: HealthThresholds | None = None,
        backend: DatabaseBackend | None = None,
    ) -> None:
        self._thresholds = thresholds or HealthThresholds()
        self._backend = backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        recon_snap: ReconciliationSnapshot,
        transfer_snap: TransferPairSnapshot,
        basis_snap: BasisContinuitySnapshot,
    ) -> HealthScoreSnapshot:
        """Compute a health score from pre-computed integrity snapshots.

        Args:
            recon_snap: Snapshot from :meth:`.ReconciliationEngine.run`.
            transfer_snap: Snapshot from :meth:`.TransferPairChecker.run`.
            basis_snap: Snapshot from :meth:`.BasisContinuityMonitor.run`.

        Returns:
            :class:`HealthScoreSnapshot` with weighted score and tier.
        """
        sub_scores = [
            self._recon_sub_score(recon_snap),
            self._transfer_sub_score(transfer_snap),
            self._basis_sub_score(basis_snap),
        ]
        overall = round(sum(s.value * s.weight for s in sub_scores), 4)
        tier = self._classify(overall)

        result = HealthScoreResult(
            sub_scores=sub_scores,
            overall_score=overall,
            tier=tier,
            thresholds=self._thresholds,
            recon_run_id=recon_snap.run_id,
            transfer_run_id=transfer_snap.run_id,
            basis_run_id=basis_snap.run_id,
        )
        return HealthScoreSnapshot(
            run_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            result=result,
        )

    def persist(self, snap: HealthScoreSnapshot) -> None:
        """Persist a health score snapshot to the database.

        Creates the ``integrity_health_snapshots`` table if it does not
        already exist.

        Args:
            snap: :class:`HealthScoreSnapshot` to store.

        Raises:
            RuntimeError: If no backend was provided at construction.
        """
        if self._backend is None:
            raise RuntimeError(
                "TreasuryHealthScorer requires a database backend for persistence."
            )
        self._ensure_table()
        r = snap.result
        sub_map = {s.name: s.value for s in r.sub_scores}
        self._backend.execute(
            """
            INSERT INTO integrity_health_snapshots
                (run_id, timestamp, overall_score, tier,
                 recon_score, transfer_score, basis_score,
                 warning_min, critical_min, details_json)
            VALUES
                (:run_id, :timestamp, :overall_score, :tier,
                 :recon_score, :transfer_score, :basis_score,
                 :warning_min, :critical_min, :details_json)
            """,
            {
                "run_id": snap.run_id,
                "timestamp": snap.timestamp,
                "overall_score": r.overall_score,
                "tier": r.tier.value,
                "recon_score": sub_map.get("reconciliation", 0.0),
                "transfer_score": sub_map.get("transfer_integrity", 0.0),
                "basis_score": sub_map.get("basis_continuity", 0.0),
                "warning_min": r.thresholds.warning_min,
                "critical_min": r.thresholds.critical_min,
                "details_json": _snapshot_to_json(snap),
            },
        )
        self._backend.commit()

    def load_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        """Load recent health score snapshots for trend tracking.

        Args:
            limit: Maximum number of rows to return (most recent first).

        Returns:
            List of dicts with keys ``run_id``, ``timestamp``,
            ``overall_score``, ``tier``, ``recon_score``,
            ``transfer_score``, ``basis_score``, ``warning_min``,
            ``critical_min``.

        Raises:
            RuntimeError: If no backend was provided at construction.
        """
        if self._backend is None:
            raise RuntimeError(
                "TreasuryHealthScorer requires a database backend for load_snapshots."
            )
        self._ensure_table()
        return list(
            self._backend.execute(
                """
                SELECT run_id, timestamp, overall_score, tier,
                       recon_score, transfer_score, basis_score,
                       warning_min, critical_min
                FROM integrity_health_snapshots
                ORDER BY timestamp DESC
                LIMIT :limit
                """,
                {"limit": limit},
            )
        )

    # ------------------------------------------------------------------
    # Sub-score computation
    # ------------------------------------------------------------------

    def _recon_sub_score(self, snap: ReconciliationSnapshot) -> SubScore:
        """Compute reconciliation sub-score (0–100).

        Scoring:
        - Empty ledger: 100.0
        - Base: 100.0 * (reconciled_count / total_coins_checked)
        - Negative balance penalty: up to 40 pts (10 pts each, capped)
        """
        r = snap.result
        w = self._thresholds.weights.get(
            "reconciliation", DEFAULT_WEIGHTS["reconciliation"]
        )
        if r.total_coins_checked == 0:
            value = 100.0
        else:
            recon_ratio = r.reconciled_count / r.total_coins_checked
            neg_penalty = min(r.negative_balance_count * 10.0, 40.0)
            value = max(0.0, 100.0 * recon_ratio - neg_penalty)

        return SubScore(
            name="reconciliation",
            value=round(value, 4),
            weight=w,
            details={
                "total_coins_checked": r.total_coins_checked,
                "reconciled_count": r.reconciled_count,
                "discrepancy_count": r.discrepancy_count,
                "negative_balance_count": r.negative_balance_count,
                "is_clean": r.is_clean,
            },
        )

    def _transfer_sub_score(self, snap: TransferPairSnapshot) -> SubScore:
        """Compute transfer integrity sub-score (0–100).

        Scoring:
        - No transfers: 100.0
        - Critical finding penalty: 15 pts each, capped at 75
        - Warning finding penalty: 5 pts each, capped at 25
        """
        r = snap.result
        w = self._thresholds.weights.get(
            "transfer_integrity", DEFAULT_WEIGHTS["transfer_integrity"]
        )
        critical_count = sum(
            1 for f in r.findings if f.severity == Severity.CRITICAL
        )
        warning_count = sum(
            1 for f in r.findings if f.severity == Severity.WARNING
        )
        penalty = min(critical_count * 15.0, 75.0) + min(warning_count * 5.0, 25.0)
        value = max(0.0, 100.0 - penalty)

        return SubScore(
            name="transfer_integrity",
            value=round(value, 4),
            weight=w,
            details={
                "total_transfers_checked": r.total_transfers_checked,
                "matched_pairs": r.matched_pairs,
                "unmatched_sends": r.unmatched_sends,
                "unmatched_receives": r.unmatched_receives,
                "critical_findings": critical_count,
                "warning_findings": warning_count,
                "fee_anomalies": r.fee_anomalies,
                "is_clean": r.is_clean,
            },
        )

    def _basis_sub_score(self, snap: BasisContinuitySnapshot) -> SubScore:
        """Compute basis continuity sub-score (0–100).

        Scoring:
        - Coverage gap penalty: 20 pts each, capped at 60
        - Missing cost penalty: 3 pts each, capped at 24
        - Ambiguous source penalty: 1 pt each, capped at 16
        """
        r = snap.result
        w = self._thresholds.weights.get(
            "basis_continuity", DEFAULT_WEIGHTS["basis_continuity"]
        )
        gap_penalty = min(r.coverage_gap_count * 20.0, 60.0)
        missing_penalty = min(r.missing_cost_count * 3.0, 24.0)
        ambiguous_penalty = min(r.ambiguous_source_count * 1.0, 16.0)
        value = max(0.0, 100.0 - gap_penalty - missing_penalty - ambiguous_penalty)

        return SubScore(
            name="basis_continuity",
            value=round(value, 4),
            weight=w,
            details={
                "total_coins_checked": r.total_coins_checked,
                "total_issues": r.total_issues,
                "missing_cost_count": r.missing_cost_count,
                "ambiguous_source_count": r.ambiguous_source_count,
                "coverage_gap_count": r.coverage_gap_count,
                "is_clean": r.is_clean,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify(self, score: float) -> HealthTier:
        """Classify a numeric score into a :class:`HealthTier`."""
        if score >= self._thresholds.warning_min:
            return HealthTier.HEALTHY
        if score >= self._thresholds.critical_min:
            return HealthTier.WARNING
        return HealthTier.CRITICAL

    def _ensure_table(self) -> None:
        """Create the persistence table if it does not exist.

        Uses ``run_id TEXT PRIMARY KEY`` rather than a serial integer so the
        DDL is identical on SQLite and PostgreSQL — neither backend requires
        auto-increment behaviour here since every snapshot already carries a
        UUID primary key.
        """
        assert self._backend is not None
        self._backend.execute(
            """
            CREATE TABLE IF NOT EXISTS integrity_health_snapshots (
                run_id TEXT NOT NULL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                overall_score REAL NOT NULL,
                tier TEXT NOT NULL,
                recon_score REAL NOT NULL,
                transfer_score REAL NOT NULL,
                basis_score REAL NOT NULL,
                warning_min REAL NOT NULL,
                critical_min REAL NOT NULL,
                details_json TEXT
            )
            """
        )
        self._backend.commit()


def _snapshot_to_json(snap: HealthScoreSnapshot) -> str:
    """Serialize a :class:`HealthScoreSnapshot` to a JSON string for storage."""
    r = snap.result
    return json.dumps(
        {
            "run_id": snap.run_id,
            "timestamp": snap.timestamp,
            "overall_score": r.overall_score,
            "tier": r.tier.value,
            "recon_run_id": r.recon_run_id,
            "transfer_run_id": r.transfer_run_id,
            "basis_run_id": r.basis_run_id,
            "sub_scores": [
                {
                    "name": s.name,
                    "value": s.value,
                    "weight": s.weight,
                    "details": s.details,
                }
                for s in r.sub_scores
            ],
            "thresholds": {
                "warning_min": r.thresholds.warning_min,
                "critical_min": r.thresholds.critical_min,
                "weights": r.thresholds.weights,
            },
        }
    )

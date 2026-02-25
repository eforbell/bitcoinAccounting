"""Cost-basis continuity monitor for treasury integrity.

Identifies holdings/lots with missing or ambiguous cost basis, summarises
impacted coins, wallets, and dates, and provides remediation hints tied to
the import source or transaction class.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..db.backend import DatabaseBackend

# Transaction types that should carry a cost basis (an acquisition price)
_PRICED_ACQUISITION_TYPES: frozenset[str] = frozenset({"Buy", "Trade"})

# Transaction types that are acquisitions but may not carry a price
_UNPRICED_ACQUISITION_TYPES: frozenset[str] = frozenset(
    {"Deposit", "Mining", "Reward", "Income", "Staking"}
)

# Remediation hint templates keyed by BasisIssueType value
_HINTS: dict[str, str] = {
    "missing_cost": (
        "Add the purchase cost (sell_curr and sell amount) to this {trans_type} "
        "transaction so capital-gains calculations can use the correct basis."
    ),
    "ambiguous_source": (
        "Classify this {trans_type}: if it is an internal transfer, match it with "
        "a corresponding Withdrawal; if it is an external acquisition (mining, "
        "gift, reward), record the fair market value at receipt date."
    ),
    "coverage_gap": (
        "Acquisition records with known cost cover {known:.8f} {coin} but "
        "{sold:.8f} {coin} has been disposed; import missing purchase history "
        "or add manual cost-basis adjustments to close the gap of "
        "{gap:.8f} {coin}."
    ),
}


class BasisIssueType(str, Enum):
    """Category of a cost-basis continuity issue."""

    MISSING_COST = "missing_cost"
    AMBIGUOUS_SOURCE = "ambiguous_source"
    COVERAGE_GAP = "coverage_gap"


@dataclass
class BasisIssue:
    """A single cost-basis continuity issue.

    Attributes:
        issue_id: Unique identifier (UUID4).
        issue_type: :class:`BasisIssueType` category.
        coin: Currency code affected (e.g. ``'BTC'``).
        wallet: Exchange/wallet name, or ``None`` for aggregate findings.
        tx_id: Ledger row ID, or ``None`` for aggregate findings.
        createddate: Transaction date, or ``None`` for aggregate findings.
        trans_type: Transaction type string from the ledger, or ``None``.
        amount: Amount of coin affected (positive).
        remediation_hint: Actionable guidance for resolving this issue.
    """

    issue_id: str
    issue_type: BasisIssueType
    coin: str
    wallet: str | None
    tx_id: int | None
    createddate: str | None
    trans_type: str | None
    amount: float
    remediation_hint: str


@dataclass
class CoinBasisSummary:
    """Cost-basis coverage summary for a single coin.

    Attributes:
        coin: Currency code.
        total_acquired: Total units of this coin ever acquired (all types).
        acquired_with_cost: Units acquired with a recorded purchase cost.
        total_sold: Total units disposed of (sells, trades).
        coverage_gap: Max(0, total_sold - acquired_with_cost).
        missing_cost_count: Number of no-cost acquisition transactions.
        ambiguous_source_count: Number of ambiguous-source transactions.
        has_gap: ``True`` when coverage_gap > tolerance.
    """

    coin: str
    total_acquired: float
    acquired_with_cost: float
    total_sold: float
    coverage_gap: float
    missing_cost_count: int
    ambiguous_source_count: int
    has_gap: bool


@dataclass
class BasisContinuityResult:
    """Full cost-basis continuity scan result.

    Attributes:
        coin_filter: Coin filter applied, or ``None`` for all coins.
        wallet_filter: Wallet filter applied, or ``None`` for all wallets.
        start_date: Inclusive start date, or ``None``.
        end_date: Inclusive end date, or ``None``.
        issues: List of :class:`BasisIssue` findings.
        coin_summaries: Per-coin coverage summaries.
        total_coins_checked: Number of distinct coins evaluated.
        total_issues: Total count of issues found.
        missing_cost_count: Issues of type ``missing_cost``.
        ambiguous_source_count: Issues of type ``ambiguous_source``.
        coverage_gap_count: Issues of type ``coverage_gap``.
        is_clean: ``True`` when no issues exist.
    """

    coin_filter: str | None
    wallet_filter: str | None
    start_date: str | None
    end_date: str | None
    issues: list[BasisIssue] = field(default_factory=list)
    coin_summaries: list[CoinBasisSummary] = field(default_factory=list)
    total_coins_checked: int = 0
    total_issues: int = 0
    missing_cost_count: int = 0
    ambiguous_source_count: int = 0
    coverage_gap_count: int = 0
    is_clean: bool = True


@dataclass
class BasisContinuitySnapshot:
    """Immutable timestamped snapshot wrapping a :class:`BasisContinuityResult`.

    Attributes:
        run_id: Unique identifier for this scan run (UUID4).
        timestamp: ISO 8601 UTC timestamp of when the snapshot was taken.
        result: The underlying continuity result.
    """

    run_id: str
    timestamp: str
    result: BasisContinuityResult


class BasisContinuityMonitor:
    """Identify holdings and lots with missing or ambiguous cost basis.

    Each call to :meth:`run` produces a :class:`BasisContinuitySnapshot` with
    a fresh ``run_id`` and ``timestamp``.

    Args:
        backend: Database backend used for all queries.
        tolerance: Minimum coverage gap (in coin units) that triggers a
            ``coverage_gap`` issue.  Defaults to ``1e-8``.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        tolerance: float = 1e-8,
    ) -> None:
        self._backend = backend
        self._tolerance = tolerance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        coin: str | None = None,
        wallet: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> BasisContinuitySnapshot:
        """Run cost-basis continuity check and return a timestamped snapshot.

        Args:
            coin: Restrict to this coin. ``None`` = all coins.
            wallet: Restrict to this wallet. ``None`` = all wallets.
            start_date: Inclusive start date (``YYYY-MM-DD``). ``None`` = no
                lower bound.
            end_date: Inclusive end date (``YYYY-MM-DD``). ``None`` = no
                upper bound.

        Returns:
            :class:`BasisContinuitySnapshot` with a unique run_id.
        """
        exclusive_end = self._exclusive_end(end_date)

        coins = self._discover_coins(coin, wallet, start_date, exclusive_end)
        issues: list[BasisIssue] = []
        coin_summaries: list[CoinBasisSummary] = []

        for c in coins:
            coin_issues, summary = self._check_coin(
                c, wallet, start_date, exclusive_end
            )
            issues.extend(coin_issues)
            coin_summaries.append(summary)

        missing_cost_count = sum(
            1 for i in issues if i.issue_type == BasisIssueType.MISSING_COST
        )
        ambiguous_source_count = sum(
            1 for i in issues if i.issue_type == BasisIssueType.AMBIGUOUS_SOURCE
        )
        coverage_gap_count = sum(
            1 for i in issues if i.issue_type == BasisIssueType.COVERAGE_GAP
        )

        result = BasisContinuityResult(
            coin_filter=coin,
            wallet_filter=wallet,
            start_date=start_date,
            end_date=end_date,
            issues=issues,
            coin_summaries=coin_summaries,
            total_coins_checked=len(coins),
            total_issues=len(issues),
            missing_cost_count=missing_cost_count,
            ambiguous_source_count=ambiguous_source_count,
            coverage_gap_count=coverage_gap_count,
            is_clean=(len(issues) == 0),
        )

        return BasisContinuitySnapshot(
            run_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            result=result,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _exclusive_end(end_date: str | None) -> str | None:
        if end_date is None:
            return None
        dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        return (dt + timedelta(days=1)).strftime("%Y-%m-%d")

    def _discover_coins(
        self,
        coin_filter: str | None,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[str]:
        """Return sorted list of distinct acquired coins in the ledger."""
        if coin_filter is not None:
            return [coin_filter]

        clauses, params = self._base_clauses(None, wallet_filter, start_date, exclusive_end)
        clauses.append("buy_curr IS NOT NULL")
        clauses.append("buy_curr != ''")
        clauses.append("buy > 0")
        where = "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT DISTINCT buy_curr AS coin
            FROM ledger
            {where}
            ORDER BY buy_curr
        """
        rows = self._backend.execute(query, params or None)
        return [r["coin"] for r in rows]

    def _check_coin(
        self,
        coin: str,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> tuple[list[BasisIssue], CoinBasisSummary]:
        """Run all basis checks for a single coin and return (issues, summary)."""
        issues: list[BasisIssue] = []

        # -- Per-transaction checks --
        missing = self._find_no_cost_acquisitions(
            coin, wallet_filter, start_date, exclusive_end
        )
        for row in missing:
            trans_type = row["trans_type"] or "Buy"
            issues.append(
                BasisIssue(
                    issue_id=str(uuid.uuid4()),
                    issue_type=BasisIssueType.MISSING_COST,
                    coin=coin,
                    wallet=row["wallet"] or "",
                    tx_id=int(row["tx_id"]),
                    createddate=row["createddate"],
                    trans_type=trans_type,
                    amount=float(row["amount"]),
                    remediation_hint=_HINTS["missing_cost"].format(
                        trans_type=trans_type
                    ),
                )
            )

        ambiguous = self._find_ambiguous_acquisitions(
            coin, wallet_filter, start_date, exclusive_end
        )
        for row in ambiguous:
            trans_type = row["trans_type"] or "Deposit"
            issues.append(
                BasisIssue(
                    issue_id=str(uuid.uuid4()),
                    issue_type=BasisIssueType.AMBIGUOUS_SOURCE,
                    coin=coin,
                    wallet=row["wallet"] or "",
                    tx_id=int(row["tx_id"]),
                    createddate=row["createddate"],
                    trans_type=trans_type,
                    amount=float(row["amount"]),
                    remediation_hint=_HINTS["ambiguous_source"].format(
                        trans_type=trans_type
                    ),
                )
            )

        # -- Aggregate coverage-gap check --
        totals = self._compute_coin_totals(
            coin, wallet_filter, start_date, exclusive_end
        )
        total_acquired = totals["total_acquired"]
        acquired_with_cost = totals["acquired_with_cost"]
        total_sold = totals["total_sold"]
        gap = max(0.0, total_sold - acquired_with_cost)
        has_gap = gap > self._tolerance

        if has_gap:
            issues.append(
                BasisIssue(
                    issue_id=str(uuid.uuid4()),
                    issue_type=BasisIssueType.COVERAGE_GAP,
                    coin=coin,
                    wallet=None,
                    tx_id=None,
                    createddate=None,
                    trans_type=None,
                    amount=gap,
                    remediation_hint=_HINTS["coverage_gap"].format(
                        coin=coin,
                        known=acquired_with_cost,
                        sold=total_sold,
                        gap=gap,
                    ),
                )
            )

        summary = CoinBasisSummary(
            coin=coin,
            total_acquired=total_acquired,
            acquired_with_cost=acquired_with_cost,
            total_sold=total_sold,
            coverage_gap=gap,
            missing_cost_count=len(missing),
            ambiguous_source_count=len(ambiguous),
            has_gap=has_gap,
        )
        return issues, summary

    def _find_no_cost_acquisitions(
        self,
        coin: str,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[dict[str, Any]]:
        """Return Buy/Trade rows where the acquisition cost (sell) is absent."""
        type_placeholders = ", ".join(
            f":ptype_{i}" for i in range(len(_PRICED_ACQUISITION_TYPES))
        )
        clauses, params = self._base_clauses(
            coin, wallet_filter, start_date, exclusive_end
        )
        clauses.append(f"trans_type IN ({type_placeholders})")
        clauses.append("buy_curr = :coin_nc")
        clauses.append("buy > 0")
        clauses.append("(sell IS NULL OR sell = 0 OR sell_curr IS NULL OR sell_curr = '')")
        params.update(
            {f"ptype_{i}": t for i, t in enumerate(sorted(_PRICED_ACQUISITION_TYPES))}
        )
        params["coin_nc"] = coin
        where = "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT id AS tx_id, createddate, trans_type,
                   buy AS amount, exchange AS wallet
            FROM ledger
            {where}
            ORDER BY createddate, id
        """
        return list(self._backend.execute(query, params))

    def _find_ambiguous_acquisitions(
        self,
        coin: str,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[dict[str, Any]]:
        """Return Deposit/Mining/Reward rows for this coin."""
        type_placeholders = ", ".join(
            f":utype_{i}" for i in range(len(_UNPRICED_ACQUISITION_TYPES))
        )
        clauses, params = self._base_clauses(
            coin, wallet_filter, start_date, exclusive_end
        )
        clauses.append(f"trans_type IN ({type_placeholders})")
        clauses.append("buy_curr = :coin_ua")
        clauses.append("buy > 0")
        params.update(
            {
                f"utype_{i}": t
                for i, t in enumerate(sorted(_UNPRICED_ACQUISITION_TYPES))
            }
        )
        params["coin_ua"] = coin
        where = "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT id AS tx_id, createddate, trans_type,
                   buy AS amount, exchange AS wallet
            FROM ledger
            {where}
            ORDER BY createddate, id
        """
        return list(self._backend.execute(query, params))

    def _compute_coin_totals(
        self,
        coin: str,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> dict[str, float]:
        """Compute aggregate acquisition and disposal totals for a coin."""
        # Build type placeholders for both sets
        priced_ph = ", ".join(
            f":cptype_{i}" for i in range(len(_PRICED_ACQUISITION_TYPES))
        )
        clauses, params = self._base_clauses(
            coin, wallet_filter, start_date, exclusive_end
        )
        params.update(
            {
                f"cptype_{i}": t
                for i, t in enumerate(sorted(_PRICED_ACQUISITION_TYPES))
            }
        )
        params["coin_tot"] = coin

        where = "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT
                COALESCE(SUM(CASE WHEN buy_curr = :coin_tot AND buy > 0
                                  THEN buy ELSE 0 END), 0.0)
                    AS total_acquired,
                COALESCE(SUM(CASE WHEN buy_curr = :coin_tot AND buy > 0
                                  AND trans_type IN ({priced_ph})
                                  AND sell IS NOT NULL AND sell > 0
                                  AND sell_curr IS NOT NULL
                             THEN buy ELSE 0 END), 0.0)
                    AS acquired_with_cost,
                COALESCE(SUM(CASE WHEN sell_curr = :coin_tot AND sell > 0
                                  THEN sell ELSE 0 END), 0.0)
                    AS total_sold
            FROM ledger
            {where}
        """
        rows = self._backend.execute(query, params)
        row = rows[0] if rows else {}
        return {
            "total_acquired": float(row.get("total_acquired") or 0.0),
            "acquired_with_cost": float(row.get("acquired_with_cost") or 0.0),
            "total_sold": float(row.get("total_sold") or 0.0),
        }

    @staticmethod
    def _base_clauses(
        coin: str | None,
        wallet: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Build shared WHERE clauses and params for all ledger queries."""
        clauses: list[str] = ["(deleted = 0 OR deleted IS NULL)"]
        params: dict[str, Any] = {}

        if wallet is not None:
            clauses.append("exchange = :wallet")
            params["wallet"] = wallet

        if start_date is not None:
            clauses.append("createddate >= :start_date")
            params["start_date"] = start_date

        if exclusive_end is not None:
            clauses.append("createddate < :exclusive_end")
            params["exclusive_end"] = exclusive_end

        return clauses, params

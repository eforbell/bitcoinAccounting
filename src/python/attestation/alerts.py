"""Rule-based alerts and finding lifecycle tracking (TAM-004).

Provides an alert rule engine that evaluates integrity findings and health
scores against user-defined thresholds, and a finding lifecycle tracker
that persists finding states (new → acknowledged → resolved) in the
database.

Usage::

    from attestation.alerts import AlertRule, AlertEngine, FindingTracker

    # Define rules
    rules = [
        AlertRule("critical-score", score_below=60.0),
        AlertRule("critical-finding", severity="critical"),
        AlertRule("missing-cost", category="missing_cost"),
    ]
    engine = AlertEngine(rules)
    alerts = engine.evaluate(bundle)

    # Track lifecycle
    tracker = FindingTracker(backend)
    tracker.open_or_refresh(finding_id, finding_dict)
    tracker.acknowledge(finding_id)
    tracker.resolve(finding_id)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from attestation.generator import AttestationBundle
    from db.backend import DatabaseBackend


# ---------------------------------------------------------------------------
# Finding lifecycle
# ---------------------------------------------------------------------------


class FindingState(str, Enum):
    """Lifecycle state of a tracked finding."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class FindingRecord:
    """Persisted state for a single finding.

    Attributes:
        finding_id: Stable identifier derived from finding source+category+coin.
        state: Current lifecycle state.
        source: Integrity check that produced the finding.
        severity: Finding severity (critical/warning/info).
        category: Finding category (e.g. one_sided_send, missing_cost).
        coin: Coin the finding relates to, or ``None``.
        description: Human-readable finding summary.
        first_seen: ISO 8601 UTC timestamp when first recorded.
        last_seen: ISO 8601 UTC timestamp of most recent observation.
        acknowledged_at: ISO 8601 UTC timestamp of acknowledgement, or ``None``.
        resolved_at: ISO 8601 UTC timestamp of resolution, or ``None``.
    """

    finding_id: str
    state: FindingState
    source: str
    severity: str
    category: str
    coin: str | None
    description: str
    first_seen: str
    last_seen: str
    acknowledged_at: str | None = None
    resolved_at: str | None = None


# ---------------------------------------------------------------------------
# Alert rules
# ---------------------------------------------------------------------------


@dataclass
class AlertRule:
    """User-defined alert rule evaluated against an integrity report.

    A rule fires when **any** of its non-None conditions match.  Multiple
    conditions in the same rule are ORed together.

    Attributes:
        name: Human-readable rule identifier.
        score_below: Fire if ``overall_score < score_below``.
        severity: Fire if any finding has this severity level.
        category: Fire if any finding has this category.
        source: Fire if any finding comes from this integrity check source.
    """

    name: str
    score_below: float | None = None
    severity: str | None = None
    category: str | None = None
    source: str | None = None


@dataclass
class AlertFired:
    """A fired alert from the rule engine.

    Attributes:
        rule_name: Name of the rule that fired.
        reason: Human-readable description of why the rule fired.
        matching_findings: Findings that triggered the alert (empty if
            triggered by score threshold alone).
    """

    rule_name: str
    reason: str
    matching_findings: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[ALERT] {self.rule_name}: {self.reason}"


# ---------------------------------------------------------------------------
# AlertEngine
# ---------------------------------------------------------------------------


class AlertEngine:
    """Evaluate alert rules against an attestation bundle.

    Args:
        rules: List of :class:`AlertRule` definitions to evaluate.
    """

    def __init__(self, rules: list[AlertRule]) -> None:
        self._rules = rules

    def evaluate(self, bundle: AttestationBundle) -> list[AlertFired]:
        """Evaluate all rules against *bundle* and return fired alerts.

        Args:
            bundle: :class:`~attestation.generator.AttestationBundle` to
                evaluate.

        Returns:
            List of :class:`AlertFired` for each rule that matched.
        """
        fired: list[AlertFired] = []
        score = bundle.report.health_snap.result.overall_score
        findings = bundle.unresolved_findings

        for rule in self._rules:
            alert = self._evaluate_rule(rule, score, findings)
            if alert is not None:
                fired.append(alert)
        return fired

    def _evaluate_rule(
        self,
        rule: AlertRule,
        score: float,
        findings: list[dict[str, Any]],
    ) -> AlertFired | None:
        """Evaluate a single rule; return ``AlertFired`` or ``None``."""

        # Score threshold check
        if rule.score_below is not None and score < rule.score_below:
            return AlertFired(
                rule_name=rule.name,
                reason=f"Score {score:.1f} is below threshold {rule.score_below:.1f}",
            )

        # Finding-level checks (OR across conditions)
        matches: list[dict[str, Any]] = []
        for f in findings:
            if rule.severity and f.get("severity") == rule.severity:
                matches.append(f)
            elif rule.category and f.get("category") == rule.category:
                matches.append(f)
            elif rule.source and f.get("source") == rule.source:
                matches.append(f)

        if matches:
            parts: list[str] = []
            if rule.severity:
                parts.append(f"severity={rule.severity}")
            if rule.category:
                parts.append(f"category={rule.category}")
            if rule.source:
                parts.append(f"source={rule.source}")
            return AlertFired(
                rule_name=rule.name,
                reason=f"{len(matches)} finding(s) matched ({', '.join(parts)})",
                matching_findings=matches,
            )

        return None

    def format_summary(self, alerts: list[AlertFired]) -> str:
        """Format a list of fired alerts as a concise multi-line string.

        Args:
            alerts: Alerts to format.

        Returns:
            Human-readable summary; empty string when no alerts fired.
        """
        if not alerts:
            return "No alerts fired."
        lines = [f"Alerts fired: {len(alerts)}"]
        for a in alerts:
            lines.append(f"  • {a}")
            for f in a.matching_findings[:3]:
                lines.append(
                    f"      [{f.get('severity','?').upper()}] "
                    f"{f.get('source','?')}/{f.get('category','?')}: "
                    f"{str(f.get('description',''))[:60]}"
                )
            if len(a.matching_findings) > 3:
                lines.append(f"      … and {len(a.matching_findings) - 3} more")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# FindingTracker — lifecycle persistence
# ---------------------------------------------------------------------------

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS attestation_findings (
    finding_id      TEXT NOT NULL PRIMARY KEY,
    state           TEXT NOT NULL DEFAULT 'new',
    source          TEXT NOT NULL,
    severity        TEXT NOT NULL,
    category        TEXT NOT NULL,
    coin            TEXT,
    description     TEXT NOT NULL,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    acknowledged_at TEXT,
    resolved_at     TEXT,
    extra_json      TEXT
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_finding_id(finding: dict[str, Any]) -> str:
    """Derive a stable finding ID from its source, category, coin, and wallet.

    Uses MD5 → UUID (same approach as :func:`~attestation.generator._period_run_id`)
    so the ID is deterministic and collision-resistant.  The same finding
    detected in different runs maps to the same database record.
    """
    key = ":".join([
        finding.get("source", ""),
        finding.get("category", ""),
        finding.get("coin", "") or "",
        finding.get("wallet", "") or "",
    ])
    digest = hashlib.md5(key.encode()).hexdigest()
    return str(uuid.UUID(digest))


class FindingTracker:
    """Persist and transition finding lifecycle states.

    Each unique finding (identified by source+category+coin+wallet) maps to
    one row in ``attestation_findings``.  Re-observing a finding updates
    ``last_seen`` without changing the state.  Calling
    :meth:`acknowledge` or :meth:`resolve` advances the state.

    Args:
        backend: Database backend for persistence.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        self._backend = backend
        self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_or_refresh(self, finding: dict[str, Any]) -> FindingRecord:
        """Record a finding observation, creating or updating its row.

        If the finding is new, inserts it with state ``new``.  If already
        tracked, updates ``last_seen`` and resets state to ``new`` only when
        it was previously ``resolved`` (re-emergence).

        Args:
            finding: Finding dict (same structure as
                :func:`~attestation.generator._extract_unresolved` output).

        Returns:
            Current :class:`FindingRecord` for the finding.
        """
        fid = _stable_finding_id(finding)
        now = _now()
        existing = self._load(fid)

        if existing is None:
            record = FindingRecord(
                finding_id=fid,
                state=FindingState.NEW,
                source=finding.get("source", ""),
                severity=finding.get("severity", ""),
                category=finding.get("category", ""),
                coin=finding.get("coin"),
                description=str(finding.get("description", "")),
                first_seen=now,
                last_seen=now,
            )
            self._insert(record)
        else:
            # Re-emerging finding: reset to new if previously resolved
            new_state = FindingState.NEW if existing.state == FindingState.RESOLVED else existing.state
            self._backend.execute(
                "UPDATE attestation_findings SET last_seen = :ts, state = :state "
                "WHERE finding_id = :fid",
                {"ts": now, "state": new_state.value, "fid": fid},
            )
            self._backend.commit()
            existing.last_seen = now
            existing.state = new_state
            record = existing

        return record

    def acknowledge(self, finding_id: str) -> FindingRecord:
        """Transition a finding from ``new`` to ``acknowledged``.

        Args:
            finding_id: ID of the finding to acknowledge.

        Returns:
            Updated :class:`FindingRecord`.

        Raises:
            KeyError: If the finding does not exist.
            ValueError: If the finding is not in state ``new``.
        """
        record = self._require(finding_id)
        if record.state != FindingState.NEW:
            raise ValueError(
                f"Cannot acknowledge finding in state {record.state.value!r}; "
                "expected 'new'."
            )
        now = _now()
        self._backend.execute(
            "UPDATE attestation_findings SET state = 'acknowledged', acknowledged_at = :ts "
            "WHERE finding_id = :fid",
            {"ts": now, "fid": finding_id},
        )
        self._backend.commit()
        record.state = FindingState.ACKNOWLEDGED
        record.acknowledged_at = now
        return record

    def resolve(self, finding_id: str) -> FindingRecord:
        """Transition a finding to ``resolved``.

        Allowed from both ``new`` and ``acknowledged`` states.

        Args:
            finding_id: ID of the finding to resolve.

        Returns:
            Updated :class:`FindingRecord`.

        Raises:
            KeyError: If the finding does not exist.
            ValueError: If the finding is already resolved.
        """
        record = self._require(finding_id)
        if record.state == FindingState.RESOLVED:
            raise ValueError("Finding is already resolved.")
        now = _now()
        self._backend.execute(
            "UPDATE attestation_findings SET state = 'resolved', resolved_at = :ts "
            "WHERE finding_id = :fid",
            {"ts": now, "fid": finding_id},
        )
        self._backend.commit()
        record.state = FindingState.RESOLVED
        record.resolved_at = now
        return record

    def load_all(
        self,
        state: FindingState | None = None,
    ) -> list[FindingRecord]:
        """Load tracked findings, optionally filtered by state.

        Args:
            state: Filter to this state only, or ``None`` for all.

        Returns:
            List of :class:`FindingRecord` objects ordered by ``last_seen``
            descending.
        """
        self._ensure_table()
        if state is not None:
            rows = list(self._backend.execute(
                "SELECT * FROM attestation_findings WHERE state = :state "
                "ORDER BY last_seen DESC",
                {"state": state.value},
            ))
        else:
            rows = list(self._backend.execute(
                "SELECT * FROM attestation_findings ORDER BY last_seen DESC"
            ))
        return [self._row_to_record(r) for r in rows]

    def sync_findings(self, findings: list[dict[str, Any]]) -> list[FindingRecord]:
        """Synchronise a full findings list: open/refresh observed findings.

        Args:
            findings: All currently-unresolved findings from an integrity
                check.

        Returns:
            List of :class:`FindingRecord` for each finding processed.
        """
        return [self.open_or_refresh(f) for f in findings]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._backend.execute(_TABLE_DDL)
        self._backend.commit()

    def _insert(self, record: FindingRecord) -> None:
        self._backend.execute(
            """
            INSERT INTO attestation_findings
                (finding_id, state, source, severity, category, coin,
                 description, first_seen, last_seen, acknowledged_at, resolved_at)
            VALUES
                (:finding_id, :state, :source, :severity, :category, :coin,
                 :description, :first_seen, :last_seen, :acknowledged_at, :resolved_at)
            """,
            {
                "finding_id": record.finding_id,
                "state": record.state.value,
                "source": record.source,
                "severity": record.severity,
                "category": record.category,
                "coin": record.coin,
                "description": record.description,
                "first_seen": record.first_seen,
                "last_seen": record.last_seen,
                "acknowledged_at": record.acknowledged_at,
                "resolved_at": record.resolved_at,
            },
        )
        self._backend.commit()

    def _load(self, finding_id: str) -> FindingRecord | None:
        rows = list(self._backend.execute(
            "SELECT * FROM attestation_findings WHERE finding_id = :fid",
            {"fid": finding_id},
        ))
        if not rows:
            return None
        return self._row_to_record(rows[0])

    def _require(self, finding_id: str) -> FindingRecord:
        record = self._load(finding_id)
        if record is None:
            raise KeyError(f"Finding {finding_id!r} not found.")
        return record

    def _row_to_record(self, row: Any) -> FindingRecord:
        if hasattr(row, "keys"):
            d = dict(row)
        else:
            cols = [
                "finding_id", "state", "source", "severity", "category",
                "coin", "description", "first_seen", "last_seen",
                "acknowledged_at", "resolved_at", "extra_json",
            ]
            d = dict(zip(cols, row))
        return FindingRecord(
            finding_id=str(d["finding_id"]),
            state=FindingState(str(d["state"])),
            source=str(d["source"]),
            severity=str(d["severity"]),
            category=str(d["category"]),
            coin=str(d["coin"]) if d.get("coin") else None,
            description=str(d["description"]),
            first_seen=str(d["first_seen"]),
            last_seen=str(d["last_seen"]),
            acknowledged_at=str(d["acknowledged_at"]) if d.get("acknowledged_at") else None,
            resolved_at=str(d["resolved_at"]) if d.get("resolved_at") else None,
        )

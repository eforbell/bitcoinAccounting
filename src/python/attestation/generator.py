"""Monthly attestation artifact generator (TAM-001).

Generates month-end attestation bundles that combine treasury integrity
snapshots with structured metadata and unresolved findings lists.  Each
bundle carries a deterministic run_id derived from the period and filters
so that the same attestation period always maps to the same identifier,
enabling reliable audit traceability across re-runs.

Usage::

    from attestation.generator import AttestationGenerator

    gen = AttestationGenerator(backend)
    bundle = gen.generate(year=2024, month=12)
    print(gen.export_bundle_json(bundle))
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from integrity.cli import IntegrityReport, export_json, run_integrity_check

if TYPE_CHECKING:
    from db.backend import DatabaseBackend


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AttestationMetadata:
    """Metadata envelope for an attestation bundle.

    Attributes:
        run_id: Deterministic UUID derived from ``period_label``, ``coin``,
            and ``wallet``.  Identical inputs always produce the same ID.
        period_label: ISO year-month string, e.g. ``"2024-12"``.
        period_start: First day of the period as ``YYYY-MM-DD``.
        period_end: Last day of the period as ``YYYY-MM-DD``.
        generated_at: ISO 8601 UTC timestamp of bundle creation.
        coin: Coin filter applied during generation, or ``None``.
        wallet: Wallet filter applied during generation, or ``None``.
    """

    run_id: str
    period_label: str
    period_start: str
    period_end: str
    generated_at: str
    coin: str | None
    wallet: str | None


@dataclass
class AttestationBundle:
    """Complete month-end attestation artifact.

    Attributes:
        metadata: Attestation metadata and audit identifiers.
        report: Full integrity report for the period.
        unresolved_findings: Flattened list of all findings/issues from all
            three integrity checks.
    """

    metadata: AttestationMetadata
    report: IntegrityReport
    unresolved_findings: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _period_run_id(
    period_label: str,
    coin: str | None,
    wallet: str | None,
) -> str:
    """Generate a deterministic run ID for a given period and optional filters.

    Uses MD5 of a stable key string converted to a UUID, guaranteeing the
    same period + filters always yield the same identifier without requiring
    database lookups.

    Args:
        period_label: ISO year-month, e.g. ``"2024-12"``.
        coin: Optional coin filter.
        wallet: Optional wallet filter.

    Returns:
        UUID4-format string derived deterministically from the inputs.
    """
    key = f"attestation:{period_label}:{coin or ''}:{wallet or ''}"
    digest = hashlib.md5(key.encode()).hexdigest()
    return str(uuid.UUID(digest))


def _period_bounds(year: int, month: int) -> tuple[str, str]:
    """Return ``(period_start, period_end)`` as ``YYYY-MM-DD`` strings.

    Args:
        year: Four-digit year.
        month: Month number (1–12).

    Returns:
        Tuple of ``(first_day, last_day)`` for the given month.
    """
    _, last_day = calendar.monthrange(year, month)
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start, end


def _extract_unresolved(report: IntegrityReport) -> list[dict[str, Any]]:
    """Extract all unresolved findings from an integrity report.

    Collects findings from transfer-pair integrity, basis-continuity, and
    reconciliation checks into a uniform structure.

    Args:
        report: :class:`~integrity.cli.IntegrityReport` to inspect.

    Returns:
        List of finding dicts with keys ``source``, ``severity``,
        ``category``, ``coin``, ``wallet``, ``tx_id``, ``description``.
    """
    findings: list[dict[str, Any]] = []

    for f in report.transfer_snap.result.findings:
        findings.append(
            {
                "source": "transfer_integrity",
                "severity": f.severity.value,
                "category": f.category,
                "coin": f.coin,
                "wallet": f.send_wallet or f.receive_wallet,
                "tx_id": f.send_tx_id or f.receive_tx_id,
                "description": f.description,
            }
        )

    for i in report.basis_snap.result.issues:
        findings.append(
            {
                "source": "basis_continuity",
                "severity": "warning",
                "category": i.issue_type.value,
                "coin": i.coin,
                "wallet": i.wallet,
                "tx_id": i.tx_id,
                "description": i.remediation_hint,
            }
        )

    for s in report.recon_snap.result.coin_summaries:
        if not s.is_reconciled:
            findings.append(
                {
                    "source": "reconciliation",
                    "severity": "critical",
                    "category": "discrepancy",
                    "coin": s.coin,
                    "wallet": None,
                    "tx_id": None,
                    "description": (
                        f"Coin {s.coin}: wallet_sum={s.wallet_sum:.8f} "
                        f"ledger_total={s.ledger_total:.8f} "
                        f"delta={s.delta:.8f}"
                    ),
                }
            )

    for b in report.recon_snap.result.wallet_balances:
        if b.is_negative:
            findings.append(
                {
                    "source": "reconciliation",
                    "severity": "warning",
                    "category": "negative_balance",
                    "coin": b.coin,
                    "wallet": b.wallet,
                    "tx_id": None,
                    "description": (
                        f"Negative balance for {b.coin} in {b.wallet}: {b.balance:.8f}"
                    ),
                }
            )

    return findings


# ---------------------------------------------------------------------------
# AttestationGenerator
# ---------------------------------------------------------------------------


class AttestationGenerator:
    """Generate and export monthly attestation bundles.

    Composes treasury integrity checks and packages all results into an
    exportable artifact with deterministic run identifiers for audit
    traceability.

    Args:
        backend: Database backend to query.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        self._backend = backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        year: int,
        month: int,
        coin: str | None = None,
        wallet: str | None = None,
        persist: bool = False,
    ) -> AttestationBundle:
        """Generate a month-end attestation bundle.

        Runs all four integrity checks scoped to the given month and
        packages the results together with structured metadata and a
        deterministic run identifier.

        Args:
            year: Four-digit year (e.g. ``2024``).
            month: Month number 1–12.
            coin: Optional coin filter applied to all checks.
            wallet: Optional wallet filter applied to all checks.
            persist: When ``True``, persist the health snapshot to the DB.

        Returns:
            :class:`AttestationBundle` with metadata, report, and findings.
        """
        period_label = f"{year:04d}-{month:02d}"
        period_start, period_end = _period_bounds(year, month)
        run_id = _period_run_id(period_label, coin, wallet)

        report = run_integrity_check(
            backend=self._backend,
            coin=coin,
            wallet=wallet,
            start_date=period_start,
            end_date=period_end,
            persist=persist,
        )

        metadata = AttestationMetadata(
            run_id=run_id,
            period_label=period_label,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            coin=coin,
            wallet=wallet,
        )

        unresolved = _extract_unresolved(report)

        return AttestationBundle(
            metadata=metadata,
            report=report,
            unresolved_findings=unresolved,
        )

    def export_bundle_json(self, bundle: AttestationBundle) -> str:
        """Serialize the full attestation bundle to a JSON string.

        The document includes the attestation metadata envelope, all
        unresolved findings, and the full nested integrity report.

        Args:
            bundle: :class:`AttestationBundle` to serialize.

        Returns:
            Pretty-printed JSON string.
        """
        m = bundle.metadata
        doc: dict[str, Any] = {
            "attestation_run_id": m.run_id,
            "period_label": m.period_label,
            "period_start": m.period_start,
            "period_end": m.period_end,
            "generated_at": m.generated_at,
            "coin_filter": m.coin,
            "wallet_filter": m.wallet,
            "unresolved_finding_count": len(bundle.unresolved_findings),
            "unresolved_findings": bundle.unresolved_findings,
            "integrity": json.loads(export_json(bundle.report)),
        }
        return json.dumps(doc, indent=2)

    def export_bundle_csv(self, bundle: AttestationBundle) -> str:
        """Serialize unresolved findings to a flat CSV string.

        Columns: ``attestation_run_id``, ``period_label``, ``source``,
        ``severity``, ``category``, ``coin``, ``wallet``, ``tx_id``,
        ``description``.

        Args:
            bundle: :class:`AttestationBundle` to serialize.

        Returns:
            CSV text with header row.
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "attestation_run_id",
                "period_label",
                "source",
                "severity",
                "category",
                "coin",
                "wallet",
                "tx_id",
                "description",
            ]
        )
        m = bundle.metadata
        for f in bundle.unresolved_findings:
            writer.writerow(
                [
                    m.run_id,
                    m.period_label,
                    f["source"],
                    f["severity"],
                    f["category"],
                    f.get("coin") or "",
                    f.get("wallet") or "",
                    f.get("tx_id") or "",
                    f["description"],
                ]
            )
        return buf.getvalue()

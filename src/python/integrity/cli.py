"""Integrity CLI report command (TIF-005).

Runs all four treasury integrity checks and prints a concise terminal
summary with top issues and remediation counts.  Optionally exports the
full results as JSON or CSV.

Usage::

    bitcoin-integrity [options]

    --coin COIN           Restrict to this coin (default: all)
    --wallet WALLET       Restrict to this wallet (default: all)
    --start-date DATE     Inclusive start date YYYY-MM-DD (default: none)
    --end-date DATE       Inclusive end date YYYY-MM-DD (default: none)
    --format {json,csv}   Export format (default: no file export)
    --output PATH         Write export to this file (default: stdout when
                          --format is given)
    --persist             Save health score snapshot to the database
    --warning-min FLOAT   Minimum score for HEALTHY tier (default: 80.0)
    --critical-min FLOAT  Minimum score for WARNING tier (default: 60.0)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .basis_continuity import BasisContinuityMonitor, BasisContinuitySnapshot
from .health_score import HealthScoreSnapshot, HealthThresholds, TreasuryHealthScorer
from .reconciliation import ReconciliationEngine, ReconciliationSnapshot
from .transfer_pairs import Severity, TransferPairChecker, TransferPairSnapshot

if TYPE_CHECKING:
    from ..db.backend import DatabaseBackend

# Number of top findings to include in the terminal summary
_TOP_ISSUES_LIMIT: int = 5


@dataclass
class IntegrityReport:
    """Combined result of all four integrity checks.

    Attributes:
        health_snap: Health score snapshot (weighted aggregate).
        recon_snap: Reconciliation snapshot.
        transfer_snap: Transfer-pair integrity snapshot.
        basis_snap: Basis-continuity snapshot.
    """

    health_snap: HealthScoreSnapshot
    recon_snap: ReconciliationSnapshot
    transfer_snap: TransferPairSnapshot
    basis_snap: BasisContinuitySnapshot


# ---------------------------------------------------------------------------
# Core runner (importable for tests / TUI integration)
# ---------------------------------------------------------------------------


def run_integrity_check(
    backend: DatabaseBackend,
    coin: str | None = None,
    wallet: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    persist: bool = False,
    thresholds: HealthThresholds | None = None,
) -> IntegrityReport:
    """Run all integrity checks and return a combined report.

    Args:
        backend: Database backend to query.
        coin: Optional coin filter (e.g. ``'BTC'``).
        wallet: Optional wallet filter.
        start_date: Inclusive start date ``YYYY-MM-DD`` or ``None``.
        end_date: Inclusive end date ``YYYY-MM-DD`` or ``None``.
        persist: When ``True``, persist the health snapshot to the DB.
        thresholds: Custom health thresholds; defaults to
            :class:`.HealthThresholds` defaults.

    Returns:
        :class:`IntegrityReport` containing all four snapshots.
    """
    recon_snap = ReconciliationEngine(backend).run(
        coin=coin, wallet=wallet, start_date=start_date, end_date=end_date
    )
    transfer_snap = TransferPairChecker(backend).run(
        coin=coin, wallet=wallet, start_date=start_date, end_date=end_date
    )
    basis_snap = BasisContinuityMonitor(backend).run(
        coin=coin, wallet=wallet, start_date=start_date, end_date=end_date
    )
    scorer = TreasuryHealthScorer(
        thresholds=thresholds,
        backend=backend if persist else None,
    )
    health_snap = scorer.score(recon_snap, transfer_snap, basis_snap)
    if persist:
        scorer.persist(health_snap)

    return IntegrityReport(
        health_snap=health_snap,
        recon_snap=recon_snap,
        transfer_snap=transfer_snap,
        basis_snap=basis_snap,
    )


# ---------------------------------------------------------------------------
# Terminal summary formatter
# ---------------------------------------------------------------------------


def format_summary(report: IntegrityReport, top_n: int = _TOP_ISSUES_LIMIT) -> str:
    """Return a concise multi-line terminal summary of the report.

    Args:
        report: :class:`IntegrityReport` to summarise.
        top_n: Maximum number of individual findings to display.

    Returns:
        Formatted string ready to print.
    """
    lines: list[str] = []
    h = report.health_snap
    r = h.result

    lines.append("Treasury Integrity Report")
    lines.append("=" * 41)
    lines.append(f"Run:    {h.timestamp}")
    lines.append(f"Score:  {r.overall_score:.1f}  [{r.tier.value.upper()}]")
    lines.append("")

    # Sub-scores
    lines.append("Sub-scores")
    lines.append("-" * 41)
    sub_map = {s.name: s for s in r.sub_scores}

    recon_sub = sub_map.get("reconciliation")
    if recon_sub:
        d = recon_sub.details
        lines.append(
            f"  Reconciliation     {recon_sub.value:6.1f}"
            f"  ({d['total_coins_checked']} coins, "
            f"{d['discrepancy_count']} discrepancies, "
            f"{d['negative_balance_count']} negative balances)"
        )

    xfer_sub = sub_map.get("transfer_integrity")
    if xfer_sub:
        d = xfer_sub.details
        lines.append(
            f"  Transfer Integrity {xfer_sub.value:6.1f}"
            f"  ({d['critical_findings']} critical, "
            f"{d['warning_findings']} warnings, "
            f"{d['fee_anomalies']} fee anomalies)"
        )

    basis_sub = sub_map.get("basis_continuity")
    if basis_sub:
        d = basis_sub.details
        lines.append(
            f"  Basis Continuity   {basis_sub.value:6.1f}"
            f"  ({d['missing_cost_count']} missing cost, "
            f"{d['ambiguous_source_count']} ambiguous, "
            f"{d['coverage_gap_count']} coverage gaps)"
        )

    lines.append("")

    # Top issues
    all_issues = _collect_issues(report)
    total = len(all_issues)
    shown = all_issues[:top_n]

    if shown:
        lines.append(f"Top Issues ({min(top_n, total)} of {total})")
        lines.append("-" * 41)
        for sev, cat, desc in shown:
            lines.append(f"  [{sev}] {cat}: {desc}")
        lines.append("")

    # Remediation counts
    br = report.basis_snap.result
    tr = report.transfer_snap.result
    lines.append("Remediation Summary")
    lines.append("-" * 41)
    lines.append(f"  Missing cost basis:   {br.missing_cost_count}")
    lines.append(f"  Ambiguous sources:    {br.ambiguous_source_count}")
    lines.append(f"  Coverage gaps:        {br.coverage_gap_count}")
    lines.append(f"  Unmatched sends:      {tr.unmatched_sends}")
    lines.append(f"  Unmatched receives:   {tr.unmatched_receives}")
    lines.append(f"  Amount mismatches:    {tr.amount_mismatches}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def export_json(report: IntegrityReport) -> str:
    """Serialize the full :class:`IntegrityReport` to a JSON string.

    The structure contains four top-level keys: ``health``,
    ``reconciliation``, ``transfer_integrity``, and ``basis_continuity``.

    Args:
        report: Report to serialize.

    Returns:
        Pretty-printed JSON string.
    """
    h = report.health_snap
    r = h.result
    rr = report.recon_snap.result
    tr = report.transfer_snap.result
    br = report.basis_snap.result

    doc: dict[str, Any] = {
        "run_id": h.run_id,
        "timestamp": h.timestamp,
        "health": {
            "overall_score": r.overall_score,
            "tier": r.tier.value,
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
        },
        "reconciliation": {
            "run_id": report.recon_snap.run_id,
            "is_clean": rr.is_clean,
            "total_coins_checked": rr.total_coins_checked,
            "total_wallets_checked": rr.total_wallets_checked,
            "reconciled_count": rr.reconciled_count,
            "discrepancy_count": rr.discrepancy_count,
            "negative_balance_count": rr.negative_balance_count,
            "coin_summaries": [
                {
                    "coin": s.coin,
                    "wallet_sum": s.wallet_sum,
                    "ledger_total": s.ledger_total,
                    "delta": s.delta,
                    "is_reconciled": s.is_reconciled,
                }
                for s in rr.coin_summaries
            ],
        },
        "transfer_integrity": {
            "run_id": report.transfer_snap.run_id,
            "is_clean": tr.is_clean,
            "total_transfers_checked": tr.total_transfers_checked,
            "matched_pairs": tr.matched_pairs,
            "unmatched_sends": tr.unmatched_sends,
            "unmatched_receives": tr.unmatched_receives,
            "amount_mismatches": tr.amount_mismatches,
            "fee_anomalies": tr.fee_anomalies,
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "severity": f.severity.value,
                    "category": f.category,
                    "description": f.description,
                    "coin": f.coin,
                    "send_wallet": f.send_wallet,
                    "receive_wallet": f.receive_wallet,
                    "send_amount": f.send_amount,
                    "receive_amount": f.receive_amount,
                    "fee_amount": f.fee_amount,
                }
                for f in tr.findings
            ],
        },
        "basis_continuity": {
            "run_id": report.basis_snap.run_id,
            "is_clean": br.is_clean,
            "total_coins_checked": br.total_coins_checked,
            "total_issues": br.total_issues,
            "missing_cost_count": br.missing_cost_count,
            "ambiguous_source_count": br.ambiguous_source_count,
            "coverage_gap_count": br.coverage_gap_count,
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "issue_type": i.issue_type.value,
                    "coin": i.coin,
                    "wallet": i.wallet,
                    "tx_id": i.tx_id,
                    "createddate": i.createddate,
                    "trans_type": i.trans_type,
                    "amount": i.amount,
                    "remediation_hint": i.remediation_hint,
                }
                for i in br.issues
            ],
        },
    }
    return json.dumps(doc, indent=2)


def export_csv(report: IntegrityReport) -> str:
    """Serialize all findings/issues to a flat CSV string.

    Columns: ``check``, ``severity``, ``category``, ``coin``, ``wallet``,
    ``tx_id``, ``amount``, ``description``.

    Args:
        report: Report to serialize.

    Returns:
        CSV text with header row.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["check", "severity", "category", "coin", "wallet", "tx_id", "amount", "description"]
    )

    # Transfer-pair findings
    tr = report.transfer_snap.result
    for f in tr.findings:
        writer.writerow(
            [
                "transfer_integrity",
                f.severity.value,
                f.category,
                f.coin,
                f.send_wallet or f.receive_wallet or "",
                f.send_tx_id or f.receive_tx_id or "",
                f.send_amount if f.send_amount is not None else f.receive_amount or "",
                f.description,
            ]
        )

    # Basis-continuity issues
    br = report.basis_snap.result
    for i in br.issues:
        writer.writerow(
            [
                "basis_continuity",
                "warning",
                i.issue_type.value,
                i.coin,
                i.wallet or "",
                i.tx_id or "",
                i.amount,
                i.remediation_hint,
            ]
        )

    # Reconciliation discrepancies
    rr = report.recon_snap.result
    for s in rr.coin_summaries:
        if not s.is_reconciled:
            writer.writerow(
                [
                    "reconciliation",
                    "critical",
                    "discrepancy",
                    s.coin,
                    "",
                    "",
                    abs(s.delta),
                    f"Coin {s.coin}: wallet_sum={s.wallet_sum:.8f} ledger_total={s.ledger_total:.8f} delta={s.delta:.8f}",
                ]
            )
    for b in rr.wallet_balances:
        if b.is_negative:
            writer.writerow(
                [
                    "reconciliation",
                    "warning",
                    "negative_balance",
                    b.coin,
                    b.wallet,
                    "",
                    abs(b.balance),
                    f"Negative balance for {b.coin} in {b.wallet}: {b.balance:.8f}",
                ]
            )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _validate_date(value: str) -> str:
    """Argparse type validator: accept only YYYY-MM-DD dates."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}' — expected format YYYY-MM-DD (e.g. 2024-01-01)"
        )
    return value


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bitcoin-integrity",
        description="Run treasury integrity checks and produce a report.",
    )
    parser.add_argument("--coin", default=None, help="Restrict to this coin")
    parser.add_argument("--wallet", default=None, help="Restrict to this wallet")
    parser.add_argument(
        "--start-date", dest="start_date", default=None, metavar="YYYY-MM-DD",
        type=_validate_date,
        help="Inclusive start date YYYY-MM-DD"
    )
    parser.add_argument(
        "--end-date", dest="end_date", default=None, metavar="YYYY-MM-DD",
        type=_validate_date,
        help="Inclusive end date YYYY-MM-DD"
    )
    parser.add_argument(
        "--format", dest="fmt", choices=["json", "csv"], default=None,
        help="Export format (json or csv)"
    )
    parser.add_argument(
        "--output", default=None, metavar="PATH",
        help="Write export to this file (default: stdout)"
    )
    parser.add_argument(
        "--persist", action="store_true",
        help="Persist the health snapshot to the database"
    )
    parser.add_argument(
        "--warning-min", dest="warning_min", type=float,
        default=None, metavar="FLOAT",
        help="Minimum score for HEALTHY tier (default: 80.0)"
    )
    parser.add_argument(
        "--critical-min", dest="critical_min", type=float,
        default=None, metavar="FLOAT",
        help="Minimum score for WARNING tier (default: 60.0)"
    )
    return parser.parse_args(argv)


def _open_backend() -> DatabaseBackend:
    """Open a database backend honouring the DB_BACKEND environment variable.

    Delegates to ``db.get_backend()`` which reads ``DB_BACKEND`` (defaulting
    to ``'sqlite'``) and loads ``.env`` via python-dotenv, so PostgreSQL
    credentials are picked up automatically when configured.

    Uses an absolute import (``db.*``) so this function works both when
    ``bitcoin-integrity`` runs as an installed entrypoint (where
    ``integrity`` is a top-level package and ``..db`` would be an invalid
    relative path) and in editable-install development environments.
    """
    from db import get_backend

    return get_backend()


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for the treasury integrity report."""
    args = _parse_args(argv)

    thresholds: HealthThresholds | None = None
    if args.warning_min is not None or args.critical_min is not None:
        thresholds = HealthThresholds(
            warning_min=args.warning_min if args.warning_min is not None else 80.0,
            critical_min=args.critical_min if args.critical_min is not None else 60.0,
        )

    backend = _open_backend()
    try:
        report = run_integrity_check(
            backend=backend,
            coin=args.coin,
            wallet=args.wallet,
            start_date=args.start_date,
            end_date=args.end_date,
            persist=args.persist,
            thresholds=thresholds,
        )
    finally:
        backend.close()

    # Always print terminal summary
    print(format_summary(report))

    # Optional file export
    if args.fmt is not None:
        content = export_json(report) if args.fmt == "json" else export_csv(report)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"\nExported {args.fmt.upper()} report to: {args.output}")
        else:
            print(content)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_issues(
    report: IntegrityReport,
) -> list[tuple[str, str, str]]:
    """Return (severity_label, category, description) tuples for all findings.

    CRITICAL findings are listed first, then WARNING interleaved across all
    three checks (transfer, basis, reconciliation) so that each category with
    issues gets proportional representation in the top-N display, then INFO.
    """
    tr = report.transfer_snap.result
    br = report.basis_snap.result
    rr = report.recon_snap.result

    critical: list[tuple[str, str, str]] = []
    xfer_warn: list[tuple[str, str, str]] = []
    basis_warn: list[tuple[str, str, str]] = []
    info: list[tuple[str, str, str]] = []

    for f in tr.findings:
        entry = (f.severity.value.upper(), f.category, f.description)
        if f.severity == Severity.CRITICAL:
            critical.append(entry)
        elif f.severity == Severity.WARNING:
            xfer_warn.append(entry)
        else:
            info.append(entry)

    for i in br.issues:
        # Use a concise per-transaction description rather than the full hint
        # so the top-issues list is readable at a glance.
        if i.createddate and i.trans_type:
            desc = (
                f"{i.trans_type} {i.amount:.8f} {i.coin}"
                f" at {i.wallet or 'unknown'} on {i.createddate}"
            )
        else:
            desc = i.remediation_hint
        basis_warn.append(("WARNING", i.issue_type.value, desc))

    for s in rr.coin_summaries:
        if not s.is_reconciled:
            critical.append((
                "CRITICAL",
                "discrepancy",
                f"Coin {s.coin}: wallet_sum={s.wallet_sum:.8f} "
                f"ledger_total={s.ledger_total:.8f} delta={s.delta:.8f}",
            ))

    # Interleave transfer and basis warnings so both categories appear when
    # one dominates by count (e.g. 193 basis vs 7 transfer).
    interleaved: list[tuple[str, str, str]] = []
    for pair in zip(xfer_warn, basis_warn):
        interleaved.extend(pair)
    # Append the longer tail
    longer = xfer_warn if len(xfer_warn) > len(basis_warn) else basis_warn
    interleaved.extend(longer[len(min(xfer_warn, basis_warn, key=len)):])

    return critical + interleaved + info

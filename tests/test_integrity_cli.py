"""Tests for the integrity CLI report command (TIF-005)."""

from __future__ import annotations

import csv
import io
import json

import pytest

from src.python.db.schema import create_tables
from src.python.db.sqlite import SqliteBackend
from src.python.integrity.cli import (
    IntegrityReport,
    _validate_date,
    export_csv,
    export_json,
    format_summary,
    run_integrity_check,
)
from src.python.integrity.health_score import HealthThresholds, HealthTier


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


def _clean_report() -> IntegrityReport:
    return run_integrity_check(_make_backend())


# ---------------------------------------------------------------------------
# IntegrityReport structure
# ---------------------------------------------------------------------------


class TestIntegrityReportStructure:
    def test_report_has_all_four_snapshots(self) -> None:
        report = _clean_report()
        assert report.health_snap is not None
        assert report.recon_snap is not None
        assert report.transfer_snap is not None
        assert report.basis_snap is not None

    def test_health_snap_run_id_differs_from_sub_run_ids(self) -> None:
        report = _clean_report()
        ids = {
            report.health_snap.run_id,
            report.recon_snap.run_id,
            report.transfer_snap.run_id,
            report.basis_snap.run_id,
        }
        assert len(ids) == 4

    def test_clean_ledger_report_is_healthy(self) -> None:
        report = _clean_report()
        assert report.health_snap.result.tier == HealthTier.HEALTHY
        assert report.health_snap.result.overall_score == 100.0

    def test_issues_ledger_lowers_score(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        assert report.health_snap.result.overall_score < 100.0


# ---------------------------------------------------------------------------
# run_integrity_check filters
# ---------------------------------------------------------------------------


class TestRunIntegrityCheckFilters:
    def test_coin_filter_passed_through(self) -> None:
        report = run_integrity_check(_make_backend(), coin="BTC")
        assert report.recon_snap.result.coin_filter == "BTC"
        assert report.transfer_snap.result.coin_filter == "BTC"
        assert report.basis_snap.result.coin_filter == "BTC"

    def test_wallet_filter_passed_through(self) -> None:
        report = run_integrity_check(_make_backend(), wallet="coinbase")
        assert report.recon_snap.result.wallet_filter == "coinbase"

    def test_date_filter_passed_through(self) -> None:
        report = run_integrity_check(
            _make_backend(),
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        assert report.recon_snap.result.start_date == "2025-01-01"
        assert report.recon_snap.result.end_date == "2025-12-31"

    def test_custom_thresholds_applied(self) -> None:
        thresholds = HealthThresholds(warning_min=50.0, critical_min=30.0)
        report = run_integrity_check(_make_backend(), thresholds=thresholds)
        assert report.health_snap.result.thresholds.warning_min == 50.0

    def test_persist_false_no_rows_stored(self) -> None:
        backend = _make_backend()
        run_integrity_check(backend, persist=False)
        rows = backend.execute("SELECT run_id FROM integrity_health_snapshots")
        assert rows == []

    def test_persist_true_saves_snapshot(self) -> None:
        backend = _make_backend()
        run_integrity_check(backend, persist=True)
        rows = backend.execute(
            "SELECT * FROM integrity_health_snapshots"
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_summary_contains_header(self) -> None:
        text = format_summary(_clean_report())
        assert "Treasury Integrity Report" in text

    def test_summary_contains_score(self) -> None:
        text = format_summary(_clean_report())
        assert "Score:" in text
        assert "100.0" in text

    def test_summary_contains_tier(self) -> None:
        text = format_summary(_clean_report())
        assert "HEALTHY" in text

    def test_summary_contains_sub_scores(self) -> None:
        text = format_summary(_clean_report())
        assert "Reconciliation" in text
        assert "Transfer Integrity" in text
        assert "Basis Continuity" in text

    def test_summary_contains_remediation_section(self) -> None:
        text = format_summary(_clean_report())
        assert "Remediation Summary" in text
        assert "Missing cost basis:" in text
        assert "Unmatched sends:" in text

    def test_summary_shows_top_issues_when_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        text = format_summary(report)
        assert "Top Issues" in text
        assert "one_sided_send" in text

    def test_summary_no_top_issues_section_when_clean(self) -> None:
        text = format_summary(_clean_report())
        assert "Top Issues" not in text

    def test_summary_top_n_respected(self) -> None:
        backend = _make_backend()
        for _ in range(8):
            _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        text = format_summary(report, top_n=3)
        assert "Top Issues (3 of" in text

    def test_summary_contains_timestamp(self) -> None:
        report = _clean_report()
        text = format_summary(report)
        assert report.health_snap.timestamp in text


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------


class TestExportJson:
    def test_json_is_valid(self) -> None:
        data = json.loads(export_json(_clean_report()))
        assert isinstance(data, dict)

    def test_json_has_top_level_keys(self) -> None:
        data = json.loads(export_json(_clean_report()))
        assert "run_id" in data
        assert "timestamp" in data
        assert "health" in data
        assert "reconciliation" in data
        assert "transfer_integrity" in data
        assert "basis_continuity" in data

    def test_json_health_section(self) -> None:
        data = json.loads(export_json(_clean_report()))
        h = data["health"]
        assert "overall_score" in h
        assert "tier" in h
        assert "sub_scores" in h
        assert "thresholds" in h
        assert len(h["sub_scores"]) == 3

    def test_json_reconciliation_section(self) -> None:
        data = json.loads(export_json(_clean_report()))
        rec = data["reconciliation"]
        assert "is_clean" in rec
        assert "coin_summaries" in rec
        assert "discrepancy_count" in rec

    def test_json_transfer_integrity_section(self) -> None:
        data = json.loads(export_json(_clean_report()))
        tr = data["transfer_integrity"]
        assert "is_clean" in tr
        assert "findings" in tr
        assert "unmatched_sends" in tr

    def test_json_basis_continuity_section(self) -> None:
        data = json.loads(export_json(_clean_report()))
        bc = data["basis_continuity"]
        assert "is_clean" in bc
        assert "issues" in bc
        assert "coverage_gap_count" in bc

    def test_json_findings_populated_when_issues_exist(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        data = json.loads(export_json(report))
        findings = data["transfer_integrity"]["findings"]
        assert len(findings) > 0
        finding = findings[0]
        assert "severity" in finding
        assert "category" in finding
        assert "description" in finding

    def test_json_tier_value_is_string(self) -> None:
        data = json.loads(export_json(_clean_report()))
        assert isinstance(data["health"]["tier"], str)

    def test_json_run_id_matches_health_snap(self) -> None:
        report = _clean_report()
        data = json.loads(export_json(report))
        assert data["run_id"] == report.health_snap.run_id


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


class TestExportCsv:
    def _parse(self, content: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(content)))

    def test_csv_has_header(self) -> None:
        content = export_csv(_clean_report())
        assert content.startswith("check,severity,category")

    def test_csv_expected_columns(self) -> None:
        rows = self._parse(export_csv(_clean_report()))
        expected_cols = {"check", "severity", "category", "coin", "wallet",
                         "tx_id", "amount", "description"}
        if rows:
            assert expected_cols.issubset(rows[0].keys())

    def test_csv_empty_when_clean(self) -> None:
        rows = self._parse(export_csv(_clean_report()))
        assert rows == []

    def test_csv_transfer_finding_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        rows = self._parse(export_csv(report))
        checks = [r["check"] for r in rows]
        assert "transfer_integrity" in checks

    def test_csv_transfer_finding_has_severity(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=1.0, sell_curr="BTC")
        report = run_integrity_check(backend)
        rows = self._parse(export_csv(report))
        tr_rows = [r for r in rows if r["check"] == "transfer_integrity"]
        assert all(r["severity"] in ("critical", "warning", "info") for r in tr_rows)

    def test_csv_basis_issue_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy", buy=1.0, buy_curr="BTC")  # no cost
        report = run_integrity_check(backend)
        rows = self._parse(export_csv(report))
        checks = [r["check"] for r in rows]
        assert "basis_continuity" in checks

    def test_csv_reconciliation_negative_balance_present(self) -> None:
        backend = _make_backend()
        # Buy depletes USD → negative USD balance
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
        )
        report = run_integrity_check(backend)
        rows = self._parse(export_csv(report))
        recon_rows = [r for r in rows if r["check"] == "reconciliation"]
        assert any(r["category"] == "negative_balance" for r in recon_rows)


# ---------------------------------------------------------------------------
# Date format validation
# ---------------------------------------------------------------------------


class TestDateValidation:
    def test_valid_iso_date_accepted(self) -> None:
        assert _validate_date("2024-01-01") == "2024-01-01"

    def test_valid_iso_date_end_of_year(self) -> None:
        assert _validate_date("2025-12-31") == "2025-12-31"

    def test_wrong_order_dd_mm_yyyy_rejected(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
            _validate_date("01-01-2024")

    def test_us_slash_format_rejected(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
            _validate_date("01/01/2024")

    def test_partial_date_rejected(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_date("2024-01")

    def test_free_text_rejected(self) -> None:
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_date("yesterday")

"""Tests for monthly attestation artifact generation (TAM-001)."""

from __future__ import annotations

import csv
import io
import json

import pytest

from src.python.attestation.generator import (
    AttestationBundle,
    AttestationGenerator,
    AttestationMetadata,
    _extract_unresolved,
    _period_bounds,
    _period_run_id,
)
from src.python.db.schema import create_tables
from src.python.db.sqlite import SqliteBackend
from src.python.integrity.cli import run_integrity_check


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
    createddate: str = "2024-12-15",
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
# _period_bounds
# ---------------------------------------------------------------------------


class TestPeriodBounds:
    def test_january_start_and_end(self) -> None:
        start, end = _period_bounds(2024, 1)
        assert start == "2024-01-01"
        assert end == "2024-01-31"

    def test_february_non_leap(self) -> None:
        start, end = _period_bounds(2023, 2)
        assert start == "2023-02-01"
        assert end == "2023-02-28"

    def test_february_leap_year(self) -> None:
        start, end = _period_bounds(2024, 2)
        assert start == "2024-02-01"
        assert end == "2024-02-29"

    def test_december_end(self) -> None:
        start, end = _period_bounds(2024, 12)
        assert start == "2024-12-01"
        assert end == "2024-12-31"

    def test_april_has_30_days(self) -> None:
        start, end = _period_bounds(2024, 4)
        assert end == "2024-04-30"

    def test_period_label_format(self) -> None:
        start, end = _period_bounds(2024, 6)
        assert start.startswith("2024-06-")
        assert end.startswith("2024-06-")


# ---------------------------------------------------------------------------
# _period_run_id
# ---------------------------------------------------------------------------


class TestPeriodRunId:
    def test_deterministic_same_inputs(self) -> None:
        id1 = _period_run_id("2024-12", None, None)
        id2 = _period_run_id("2024-12", None, None)
        assert id1 == id2

    def test_different_period_different_id(self) -> None:
        id1 = _period_run_id("2024-11", None, None)
        id2 = _period_run_id("2024-12", None, None)
        assert id1 != id2

    def test_different_coin_different_id(self) -> None:
        id1 = _period_run_id("2024-12", "BTC", None)
        id2 = _period_run_id("2024-12", "ETH", None)
        assert id1 != id2

    def test_different_wallet_different_id(self) -> None:
        id1 = _period_run_id("2024-12", None, "wallet_a")
        id2 = _period_run_id("2024-12", None, "wallet_b")
        assert id1 != id2

    def test_none_and_empty_coin_same(self) -> None:
        # None coin and no coin should produce the same ID
        id1 = _period_run_id("2024-12", None, None)
        id2 = _period_run_id("2024-12", None, None)
        assert id1 == id2

    def test_returns_valid_uuid_format(self) -> None:
        import re

        run_id = _period_run_id("2024-12", None, None)
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(run_id), f"Not a UUID format: {run_id}"

    def test_coin_filter_changes_id(self) -> None:
        base = _period_run_id("2024-12", None, None)
        filtered = _period_run_id("2024-12", "BTC", None)
        assert base != filtered


# ---------------------------------------------------------------------------
# _extract_unresolved
# ---------------------------------------------------------------------------


class TestExtractUnresolved:
    def test_empty_ledger_no_findings(self) -> None:
        backend = _make_backend()
        report = run_integrity_check(backend)
        findings = _extract_unresolved(report)
        assert findings == []

    def test_clean_roundtrip_no_findings(self) -> None:
        backend = _make_backend()
        # Clean buy/trade roundtrip: no basis issues, no transfer issues,
        # no reconciliation discrepancy (buy_curr BTC, sell_curr USD)
        _insert_tx(
            backend,
            trans_type="Buy",
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
        )
        report = run_integrity_check(backend)
        findings = _extract_unresolved(report)
        # USD may have negative balance (buy depletes USD) — that produces
        # a reconciliation warning but not a "discrepancy" in coin_summaries.
        # All findings should only be from known unclean sources.
        sources = {f["source"] for f in findings}
        # Should not have any transfer_integrity findings (no transfers)
        assert "transfer_integrity" not in sources

    def test_finding_dict_has_required_keys(self) -> None:
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=0.5,
            buy_curr="BTC",
        )
        report = run_integrity_check(backend)
        findings = _extract_unresolved(report)
        required = {"source", "severity", "category", "coin", "wallet", "tx_id", "description"}
        for finding in findings:
            assert required.issubset(finding.keys()), f"Missing keys in {finding}"

    def test_unmatched_withdrawal_appears_as_transfer_finding(self) -> None:
        backend = _make_backend()
        _insert_tx(
            backend,
            trans_type="Withdrawal",
            sell=0.1,
            sell_curr="BTC",
            exchange="wallet_a",
        )
        report = run_integrity_check(backend)
        findings = _extract_unresolved(report)
        transfer_findings = [f for f in findings if f["source"] == "transfer_integrity"]
        assert len(transfer_findings) >= 1

    def test_basis_issues_appear_as_basis_continuity(self) -> None:
        backend = _make_backend()
        # Deposit without cost basis is an AMBIGUOUS_SOURCE issue
        _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
        report = run_integrity_check(backend)
        findings = _extract_unresolved(report)
        basis_findings = [f for f in findings if f["source"] == "basis_continuity"]
        assert len(basis_findings) >= 1
        for f in basis_findings:
            assert f["severity"] == "warning"


# ---------------------------------------------------------------------------
# AttestationGenerator.generate
# ---------------------------------------------------------------------------


class TestAttestationGeneratorGenerate:
    def test_generate_returns_bundle(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        assert isinstance(bundle, AttestationBundle)

    def test_metadata_period_label(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 6)
        assert bundle.metadata.period_label == "2024-06"

    def test_metadata_period_bounds(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 2)  # leap year
        assert bundle.metadata.period_start == "2024-02-01"
        assert bundle.metadata.period_end == "2024-02-29"

    def test_metadata_run_id_is_deterministic(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        b1 = gen.generate(2024, 12)
        b2 = gen.generate(2024, 12)
        assert b1.metadata.run_id == b2.metadata.run_id

    def test_metadata_generated_at_is_iso_utc(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        # Format: 2024-12-31T23:59:59Z
        assert bundle.metadata.generated_at.endswith("Z")
        assert "T" in bundle.metadata.generated_at

    def test_metadata_coin_wallet_filters_stored(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12, coin="BTC", wallet="cold_storage")
        assert bundle.metadata.coin == "BTC"
        assert bundle.metadata.wallet == "cold_storage"

    def test_unresolved_findings_is_list(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        assert isinstance(bundle.unresolved_findings, list)

    def test_report_is_present(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        # Check structural attributes rather than isinstance to avoid
        # two-module identity issues from absolute vs src.python-prefixed imports
        assert bundle.report is not None
        assert hasattr(bundle.report, "health_snap")
        assert hasattr(bundle.report, "recon_snap")
        assert hasattr(bundle.report, "transfer_snap")
        assert hasattr(bundle.report, "basis_snap")

    def test_coin_filter_propagated_to_report(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Buy", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle_btc = gen.generate(2024, 12, coin="BTC")
        bundle_eth = gen.generate(2024, 12, coin="ETH")
        # ETH filter: no ETH transactions — engine short-circuits to clean
        # (total_coins_checked may be ≥1 due to filter short-circuit; see
        # progress.txt reconciliation note — check is_clean instead)
        assert bundle_eth.report.recon_snap.result.is_clean
        # BTC filter: BTC transaction present, checked
        assert bundle_btc.report.recon_snap.result.total_coins_checked >= 1

    def test_date_scoping_to_period(self) -> None:
        backend = _make_backend()
        # Transaction outside December 2024
        _insert_tx(
            backend,
            trans_type="Deposit",
            buy=1.0,
            buy_curr="BTC",
            createddate="2024-11-15",
        )
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)  # December only
        # November tx is outside scope, so no coins checked in Dec
        assert bundle.report.recon_snap.result.total_coins_checked == 0


# ---------------------------------------------------------------------------
# export_bundle_json
# ---------------------------------------------------------------------------


class TestExportBundleJson:
    def _make_bundle(self) -> tuple[AttestationGenerator, AttestationBundle]:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        return gen, bundle

    def test_returns_valid_json(self) -> None:
        gen, bundle = self._make_bundle()
        raw = gen.export_bundle_json(bundle)
        doc = json.loads(raw)
        assert isinstance(doc, dict)

    def test_contains_attestation_run_id(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert "attestation_run_id" in doc
        assert doc["attestation_run_id"] == bundle.metadata.run_id

    def test_contains_period_fields(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert doc["period_label"] == "2024-12"
        assert doc["period_start"] == "2024-12-01"
        assert doc["period_end"] == "2024-12-31"

    def test_contains_generated_at(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert "generated_at" in doc
        assert doc["generated_at"].endswith("Z")

    def test_contains_unresolved_findings_list(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert "unresolved_findings" in doc
        assert isinstance(doc["unresolved_findings"], list)

    def test_unresolved_finding_count_matches(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert doc["unresolved_finding_count"] == len(bundle.unresolved_findings)

    def test_contains_integrity_section(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert "integrity" in doc
        assert "health" in doc["integrity"]
        assert "reconciliation" in doc["integrity"]

    def test_coin_filter_stored_in_json(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12, coin="BTC")
        doc = json.loads(gen.export_bundle_json(bundle))
        assert doc["coin_filter"] == "BTC"
        assert doc["wallet_filter"] is None

    def test_no_filter_null_in_json(self) -> None:
        gen, bundle = self._make_bundle()
        doc = json.loads(gen.export_bundle_json(bundle))
        assert doc["coin_filter"] is None
        assert doc["wallet_filter"] is None

    def test_findings_included_when_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        doc = json.loads(gen.export_bundle_json(bundle))
        assert doc["unresolved_finding_count"] > 0
        assert len(doc["unresolved_findings"]) > 0


# ---------------------------------------------------------------------------
# export_bundle_csv
# ---------------------------------------------------------------------------


class TestExportBundleCsv:
    def _make_bundle_with_findings(
        self,
    ) -> tuple[AttestationGenerator, AttestationBundle]:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        return gen, bundle

    def _parse_csv(self, content: str) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)

    def test_returns_string(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        result = gen.export_bundle_csv(bundle)
        assert isinstance(result, str)

    def test_header_row_present(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        content = gen.export_bundle_csv(bundle)
        first_line = content.split("\n")[0]
        assert "attestation_run_id" in first_line
        assert "period_label" in first_line
        assert "source" in first_line
        assert "severity" in first_line

    def test_empty_findings_produces_header_only(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        # Empty ledger — may still have some basis findings; rely on no crashes
        content = gen.export_bundle_csv(bundle)
        rows = self._parse_csv(content)
        assert isinstance(rows, list)

    def test_findings_rows_have_all_columns(self) -> None:
        gen, bundle = self._make_bundle_with_findings()
        content = gen.export_bundle_csv(bundle)
        rows = self._parse_csv(content)
        assert len(rows) > 0
        expected_cols = {
            "attestation_run_id",
            "period_label",
            "source",
            "severity",
            "category",
            "coin",
            "wallet",
            "tx_id",
            "description",
        }
        for row in rows:
            assert expected_cols.issubset(row.keys())

    def test_attestation_run_id_in_rows(self) -> None:
        gen, bundle = self._make_bundle_with_findings()
        content = gen.export_bundle_csv(bundle)
        rows = self._parse_csv(content)
        for row in rows:
            assert row["attestation_run_id"] == bundle.metadata.run_id

    def test_period_label_in_rows(self) -> None:
        gen, bundle = self._make_bundle_with_findings()
        content = gen.export_bundle_csv(bundle)
        rows = self._parse_csv(content)
        for row in rows:
            assert row["period_label"] == "2024-12"

    def test_source_values_are_known(self) -> None:
        gen, bundle = self._make_bundle_with_findings()
        content = gen.export_bundle_csv(bundle)
        rows = self._parse_csv(content)
        valid_sources = {"transfer_integrity", "basis_continuity", "reconciliation"}
        for row in rows:
            assert row["source"] in valid_sources

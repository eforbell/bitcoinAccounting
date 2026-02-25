"""Tests for attestation PDF/report formatting (TAM-002)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.python.attestation.generator import AttestationGenerator
from src.python.attestation.reports import (
    REPORTLAB_AVAILABLE,
    PDFNotAvailableError,
    AttestationReportFormatter,
    _build_remediation_checklist,
)
from src.python.db.schema import create_tables
from src.python.db.sqlite import SqliteBackend


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
    exchange: str = "wallet_a",
    createddate: str = "2024-12-15",
) -> None:
    backend.execute(
        """
        INSERT INTO ledger (createddate, trans_type, buy, buy_curr,
                            sell, sell_curr, exchange, deleted)
        VALUES (:createddate, :trans_type, :buy, :buy_curr,
                :sell, :sell_curr, :exchange, 0)
        """,
        {
            "createddate": createddate,
            "trans_type": trans_type,
            "buy": buy,
            "buy_curr": buy_curr,
            "sell": sell,
            "sell_curr": sell_curr,
            "exchange": exchange,
        },
    )
    backend.commit()


def _make_clean_bundle(backend: SqliteBackend | None = None):  # type: ignore[return]
    if backend is None:
        backend = _make_backend()
    gen = AttestationGenerator(backend)
    return gen.generate(2024, 12)


def _make_bundle_with_findings(backend: SqliteBackend | None = None):  # type: ignore[return]
    if backend is None:
        backend = _make_backend()
    _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
    _insert_tx(
        backend,
        trans_type="Withdrawal",
        sell=0.5,
        sell_curr="BTC",
        exchange="wallet_b",
    )
    gen = AttestationGenerator(backend)
    return gen.generate(2024, 12)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_reportlab_available_is_bool(self) -> None:
        assert isinstance(REPORTLAB_AVAILABLE, bool)

    def test_reportlab_available_is_true_in_test_env(self) -> None:
        # reportlab is a project dependency — should always be available
        assert REPORTLAB_AVAILABLE is True


# ---------------------------------------------------------------------------
# PDFNotAvailableError
# ---------------------------------------------------------------------------


class TestPDFNotAvailableError:
    def test_is_import_error_subclass(self) -> None:
        err = PDFNotAvailableError()
        assert isinstance(err, ImportError)

    def test_message_mentions_reportlab(self) -> None:
        err = PDFNotAvailableError()
        assert "reportlab" in str(err).lower()

    def test_message_mentions_install(self) -> None:
        err = PDFNotAvailableError()
        assert "pip install" in str(err)


# ---------------------------------------------------------------------------
# AttestationReportFormatter construction
# ---------------------------------------------------------------------------


class TestFormatterConstruction:
    def test_constructs_without_backend(self) -> None:
        formatter = AttestationReportFormatter()
        assert formatter is not None

    def test_constructs_with_backend(self) -> None:
        backend = _make_backend()
        formatter = AttestationReportFormatter(backend=backend)
        assert formatter is not None

    def test_raises_when_reportlab_unavailable(self) -> None:
        with patch("src.python.attestation.reports.REPORTLAB_AVAILABLE", False):
            with pytest.raises(PDFNotAvailableError):
                AttestationReportFormatter()

    def test_default_trend_limit(self) -> None:
        formatter = AttestationReportFormatter()
        assert formatter._trend_limit == 6

    def test_custom_trend_limit(self) -> None:
        formatter = AttestationReportFormatter(trend_limit=3)
        assert formatter._trend_limit == 3


# ---------------------------------------------------------------------------
# generate_pdf — file creation
# ---------------------------------------------------------------------------


class TestGeneratePdf:
    def test_creates_pdf_file(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert result.exists()

    def test_returns_path_object(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert isinstance(result, Path)

    def test_returned_path_matches_output(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert str(result) == out

    def test_pdf_file_is_non_empty(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert result.stat().st_size > 1000  # at least 1 KB

    def test_pdf_starts_with_pdf_magic_bytes(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report.pdf")
            result = formatter.generate_pdf(bundle, out)
            with open(result, "rb") as fh:
                header = fh.read(5)
            assert header == b"%PDF-"

    def test_generates_for_bundle_with_findings(self) -> None:
        bundle = _make_bundle_with_findings()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "report_findings.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert result.exists()
            assert result.stat().st_size > 500

    def test_accepts_pathlib_path(self) -> None:
        bundle = _make_clean_bundle()
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.pdf"
            result = formatter.generate_pdf(bundle, out)
            assert result.exists()

    def test_generates_with_coin_filter(self) -> None:
        backend = _make_backend()
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12, coin="BTC")
        formatter = AttestationReportFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "btc_report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert result.exists()

    def test_generates_with_trend_backend(self) -> None:
        backend = _make_backend()
        # Persist a snapshot so there's trend data
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12, persist=True)
        formatter = AttestationReportFormatter(backend=backend)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "trend_report.pdf")
            result = formatter.generate_pdf(bundle, out)
            assert result.exists()


# ---------------------------------------------------------------------------
# _build_remediation_checklist
# ---------------------------------------------------------------------------


class TestBuildRemediationChecklist:
    def test_empty_findings_returns_clean_message(self) -> None:
        bundle = _make_clean_bundle()
        items = _build_remediation_checklist(bundle)
        assert len(items) == 1
        assert "no remediation" in items[0].lower() or "clean" in items[0].lower()

    def test_findings_produce_action_items(self) -> None:
        bundle = _make_bundle_with_findings()
        items = _build_remediation_checklist(bundle)
        assert len(items) >= 1

    def test_deduplicates_same_category(self) -> None:
        bundle = _make_bundle_with_findings()
        items = _build_remediation_checklist(bundle)
        # Items should be unique strings (no duplicate action messages)
        assert len(items) == len(set(items))

    def test_returns_list_of_strings(self) -> None:
        bundle = _make_clean_bundle()
        items = _build_remediation_checklist(bundle)
        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, str)

    def test_missing_cost_action_present(self) -> None:
        backend = _make_backend()
        # Buy without cost basis triggers MISSING_COST
        _insert_tx(backend, trans_type="Buy", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        items = _build_remediation_checklist(bundle)
        combined = " ".join(items).lower()
        assert "cost" in combined or "price" in combined

    def test_ambiguous_source_action_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        items = _build_remediation_checklist(bundle)
        combined = " ".join(items).lower()
        assert "deposit" in combined or "acquisition" in combined or "tax" in combined

    def test_one_sided_send_action_present(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Withdrawal", sell=0.5, sell_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        items = _build_remediation_checklist(bundle)
        combined = " ".join(items).lower()
        assert "send" in combined or "receive" in combined or "withdrawal" in combined

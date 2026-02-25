"""Tests for rule-based alerts and finding lifecycle tracking (TAM-004)."""

from __future__ import annotations

import pytest

from src.python.attestation.alerts import (
    AlertEngine,
    AlertFired,
    AlertRule,
    FindingRecord,
    FindingState,
    FindingTracker,
    _stable_finding_id,
)
from src.python.attestation.generator import AttestationGenerator
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


def _make_clean_bundle():  # type: ignore[return]
    backend = _make_backend()
    gen = AttestationGenerator(backend)
    return gen.generate(2024, 12)


def _make_bundle_with_findings():  # type: ignore[return]
    backend = _make_backend()
    _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
    _insert_tx(backend, trans_type="Withdrawal", sell=0.5, sell_curr="BTC")
    gen = AttestationGenerator(backend)
    return gen.generate(2024, 12)


def _sample_finding(
    source: str = "transfer_integrity",
    severity: str = "critical",
    category: str = "one_sided_send",
    coin: str = "BTC",
    wallet: str = "wallet_a",
) -> dict:  # type: ignore[type-arg]
    return {
        "source": source,
        "severity": severity,
        "category": category,
        "coin": coin,
        "wallet": wallet,
        "description": f"Test finding {source}/{category}",
    }


# ---------------------------------------------------------------------------
# AlertRule — construction
# ---------------------------------------------------------------------------


class TestAlertRule:
    def test_name_only(self) -> None:
        rule = AlertRule("my-rule")
        assert rule.name == "my-rule"
        assert rule.score_below is None
        assert rule.severity is None
        assert rule.category is None
        assert rule.source is None

    def test_score_below(self) -> None:
        rule = AlertRule("low-score", score_below=70.0)
        assert rule.score_below == 70.0

    def test_severity_filter(self) -> None:
        rule = AlertRule("crit", severity="critical")
        assert rule.severity == "critical"

    def test_category_filter(self) -> None:
        rule = AlertRule("missing", category="missing_cost")
        assert rule.category == "missing_cost"

    def test_source_filter(self) -> None:
        rule = AlertRule("xfer", source="transfer_integrity")
        assert rule.source == "transfer_integrity"


# ---------------------------------------------------------------------------
# AlertFired — formatting
# ---------------------------------------------------------------------------


class TestAlertFired:
    def test_str_contains_rule_name(self) -> None:
        a = AlertFired("my-rule", "Score too low")
        assert "my-rule" in str(a)

    def test_str_contains_reason(self) -> None:
        a = AlertFired("my-rule", "Score too low")
        assert "Score too low" in str(a)

    def test_default_matching_findings_empty(self) -> None:
        a = AlertFired("my-rule", "Score too low")
        assert a.matching_findings == []


# ---------------------------------------------------------------------------
# AlertEngine.evaluate — score threshold
# ---------------------------------------------------------------------------


class TestAlertEngineScoreThreshold:
    def test_score_below_fires_when_below(self) -> None:
        bundle = _make_clean_bundle()
        # Override the score to something low for testing
        bundle.report.health_snap.result.overall_score = 50.0
        rules = [AlertRule("low-score", score_below=60.0)]
        engine = AlertEngine(rules)
        alerts = engine.evaluate(bundle)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "low-score"

    def test_score_below_does_not_fire_when_above(self) -> None:
        bundle = _make_clean_bundle()
        bundle.report.health_snap.result.overall_score = 90.0
        rules = [AlertRule("low-score", score_below=60.0)]
        engine = AlertEngine(rules)
        alerts = engine.evaluate(bundle)
        assert alerts == []

    def test_score_equal_to_threshold_does_not_fire(self) -> None:
        bundle = _make_clean_bundle()
        bundle.report.health_snap.result.overall_score = 60.0
        rules = [AlertRule("low-score", score_below=60.0)]
        engine = AlertEngine(rules)
        # score < threshold, not <=; 60.0 is not < 60.0
        assert engine.evaluate(bundle) == []

    def test_reason_mentions_score_and_threshold(self) -> None:
        bundle = _make_clean_bundle()
        bundle.report.health_snap.result.overall_score = 45.0
        rules = [AlertRule("low", score_below=60.0)]
        engine = AlertEngine(rules)
        alerts = engine.evaluate(bundle)
        assert "45.0" in alerts[0].reason
        assert "60.0" in alerts[0].reason


# ---------------------------------------------------------------------------
# AlertEngine.evaluate — finding-level rules
# ---------------------------------------------------------------------------


class TestAlertEngineFindingRules:
    def _engine_with(self, **kwargs: str) -> AlertEngine:  # type: ignore[type-arg]
        return AlertEngine([AlertRule("rule", **kwargs)])

    def _bundle_with_finding(self, **kwargs: str) -> object:  # type: ignore[return]
        bundle = _make_clean_bundle()
        bundle.unresolved_findings.append(_sample_finding(**kwargs))  # type: ignore[attr-defined]
        return bundle

    def test_severity_match_fires(self) -> None:
        bundle = self._bundle_with_finding(severity="critical")
        alerts = self._engine_with(severity="critical").evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts) == 1

    def test_severity_no_match_no_fire(self) -> None:
        bundle = self._bundle_with_finding(severity="warning")
        alerts = self._engine_with(severity="critical").evaluate(bundle)  # type: ignore[arg-type]
        assert alerts == []

    def test_category_match_fires(self) -> None:
        bundle = self._bundle_with_finding(category="missing_cost")
        alerts = self._engine_with(category="missing_cost").evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts) == 1

    def test_source_match_fires(self) -> None:
        bundle = self._bundle_with_finding(source="basis_continuity")
        alerts = self._engine_with(source="basis_continuity").evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts) == 1

    def test_no_match_no_fire(self) -> None:
        bundle = self._bundle_with_finding(severity="info")
        alerts = self._engine_with(severity="critical").evaluate(bundle)  # type: ignore[arg-type]
        assert alerts == []

    def test_matching_findings_populated(self) -> None:
        bundle = self._bundle_with_finding(severity="critical")
        alerts = self._engine_with(severity="critical").evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts[0].matching_findings) == 1

    def test_multiple_matching_findings(self) -> None:
        bundle = _make_clean_bundle()
        bundle.unresolved_findings.extend([  # type: ignore[attr-defined]
            _sample_finding(severity="critical"),
            _sample_finding(severity="critical", category="discrepancy"),
        ])
        engine = AlertEngine([AlertRule("crit", severity="critical")])
        alerts = engine.evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts[0].matching_findings) == 2

    def test_multiple_rules_independent(self) -> None:
        bundle = _make_clean_bundle()
        bundle.unresolved_findings.append(_sample_finding(severity="critical"))  # type: ignore[attr-defined]
        rules = [
            AlertRule("crit", severity="critical"),
            AlertRule("warn", severity="warning"),
        ]
        engine = AlertEngine(rules)
        alerts = engine.evaluate(bundle)  # type: ignore[arg-type]
        assert len(alerts) == 1  # only critical rule fires
        assert alerts[0].rule_name == "crit"

    def test_empty_findings_no_fire(self) -> None:
        bundle = _make_clean_bundle()
        assert bundle.unresolved_findings == []  # type: ignore[attr-defined]
        engine = AlertEngine([AlertRule("crit", severity="critical")])
        assert engine.evaluate(bundle) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AlertEngine.format_summary
# ---------------------------------------------------------------------------


class TestAlertEngineFormatSummary:
    def test_no_alerts_returns_no_alerts_message(self) -> None:
        engine = AlertEngine([])
        result = engine.format_summary([])
        assert "no alerts" in result.lower()

    def test_summary_contains_rule_name(self) -> None:
        engine = AlertEngine([])
        alerts = [AlertFired("my-rule", "Score too low")]
        result = engine.format_summary(alerts)
        assert "my-rule" in result

    def test_summary_contains_count(self) -> None:
        engine = AlertEngine([])
        alerts = [
            AlertFired("rule1", "reason1"),
            AlertFired("rule2", "reason2"),
        ]
        result = engine.format_summary(alerts)
        assert "2" in result

    def test_summary_truncates_long_finding_lists(self) -> None:
        findings = [_sample_finding() for _ in range(5)]
        engine = AlertEngine([])
        alerts = [AlertFired("r", "reason", matching_findings=findings)]
        result = engine.format_summary(alerts)
        assert "more" in result.lower()


# ---------------------------------------------------------------------------
# _stable_finding_id
# ---------------------------------------------------------------------------


class TestStableFindingId:
    def test_deterministic_same_input(self) -> None:
        f = _sample_finding()
        assert _stable_finding_id(f) == _stable_finding_id(f)

    def test_different_category_different_id(self) -> None:
        f1 = _sample_finding(category="one_sided_send")
        f2 = _sample_finding(category="missing_cost")
        assert _stable_finding_id(f1) != _stable_finding_id(f2)

    def test_different_source_different_id(self) -> None:
        f1 = _sample_finding(source="transfer_integrity")
        f2 = _sample_finding(source="basis_continuity")
        assert _stable_finding_id(f1) != _stable_finding_id(f2)

    def test_returns_string(self) -> None:
        assert isinstance(_stable_finding_id(_sample_finding()), str)


# ---------------------------------------------------------------------------
# FindingTracker — basic CRUD
# ---------------------------------------------------------------------------


class TestFindingTrackerOpenOrRefresh:
    def test_new_finding_inserted(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding()
        record = tracker.open_or_refresh(finding)
        assert isinstance(record, FindingRecord)
        assert record.state == FindingState.NEW

    def test_new_finding_has_correct_source(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding(source="basis_continuity")
        record = tracker.open_or_refresh(finding)
        assert record.source == "basis_continuity"

    def test_re_observing_updates_last_seen(self) -> None:
        import time
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding()
        r1 = tracker.open_or_refresh(finding)
        time.sleep(0.01)
        r2 = tracker.open_or_refresh(finding)
        # last_seen should be updated (or at least equal)
        assert r2.last_seen >= r1.last_seen

    def test_re_observing_keeps_new_state(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding()
        tracker.open_or_refresh(finding)
        r2 = tracker.open_or_refresh(finding)
        assert r2.state == FindingState.NEW

    def test_resolved_finding_resets_to_new_on_reobservation(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding()
        r = tracker.open_or_refresh(finding)
        tracker.resolve(r.finding_id)
        r2 = tracker.open_or_refresh(finding)
        assert r2.state == FindingState.NEW


# ---------------------------------------------------------------------------
# FindingTracker — lifecycle transitions
# ---------------------------------------------------------------------------


class TestFindingTrackerLifecycle:
    def _make_new_record(self) -> tuple[FindingTracker, FindingRecord]:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        finding = _sample_finding()
        record = tracker.open_or_refresh(finding)
        return tracker, record

    def test_acknowledge_transitions_to_acknowledged(self) -> None:
        tracker, record = self._make_new_record()
        result = tracker.acknowledge(record.finding_id)
        assert result.state == FindingState.ACKNOWLEDGED

    def test_acknowledge_sets_acknowledged_at(self) -> None:
        tracker, record = self._make_new_record()
        result = tracker.acknowledge(record.finding_id)
        assert result.acknowledged_at is not None

    def test_resolve_from_new(self) -> None:
        tracker, record = self._make_new_record()
        result = tracker.resolve(record.finding_id)
        assert result.state == FindingState.RESOLVED

    def test_resolve_from_acknowledged(self) -> None:
        tracker, record = self._make_new_record()
        tracker.acknowledge(record.finding_id)
        result = tracker.resolve(record.finding_id)
        assert result.state == FindingState.RESOLVED

    def test_resolve_sets_resolved_at(self) -> None:
        tracker, record = self._make_new_record()
        result = tracker.resolve(record.finding_id)
        assert result.resolved_at is not None

    def test_double_resolve_raises(self) -> None:
        tracker, record = self._make_new_record()
        tracker.resolve(record.finding_id)
        with pytest.raises(ValueError, match="already resolved"):
            tracker.resolve(record.finding_id)

    def test_acknowledge_acknowledged_raises(self) -> None:
        tracker, record = self._make_new_record()
        tracker.acknowledge(record.finding_id)
        with pytest.raises(ValueError, match="acknowledged"):
            tracker.acknowledge(record.finding_id)

    def test_acknowledge_missing_finding_raises(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        with pytest.raises(KeyError):
            tracker.acknowledge("nonexistent-id")

    def test_resolve_missing_finding_raises(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        with pytest.raises(KeyError):
            tracker.resolve("nonexistent-id")


# ---------------------------------------------------------------------------
# FindingTracker — load_all
# ---------------------------------------------------------------------------


class TestFindingTrackerLoadAll:
    def test_load_all_returns_all_findings(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        tracker.open_or_refresh(_sample_finding(category="c1"))
        tracker.open_or_refresh(_sample_finding(category="c2"))
        records = tracker.load_all()
        assert len(records) == 2

    def test_load_all_filters_by_state(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        r1 = tracker.open_or_refresh(_sample_finding(category="c1"))
        r2 = tracker.open_or_refresh(_sample_finding(category="c2"))
        tracker.acknowledge(r1.finding_id)
        new_records = tracker.load_all(state=FindingState.NEW)
        ack_records = tracker.load_all(state=FindingState.ACKNOWLEDGED)
        assert len(new_records) == 1
        assert len(ack_records) == 1

    def test_load_all_empty_returns_empty_list(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        assert tracker.load_all() == []


# ---------------------------------------------------------------------------
# FindingTracker — sync_findings
# ---------------------------------------------------------------------------


class TestFindingTrackerSyncFindings:
    def test_sync_empty_list(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        records = tracker.sync_findings([])
        assert records == []

    def test_sync_inserts_new_findings(self) -> None:
        backend = _make_backend()
        tracker = FindingTracker(backend)
        findings = [_sample_finding(category=f"c{i}") for i in range(3)]
        records = tracker.sync_findings(findings)
        assert len(records) == 3

    def test_sync_with_real_bundle(self) -> None:
        backend = _make_backend()
        _insert_tx(backend, trans_type="Deposit", buy=1.0, buy_curr="BTC")
        gen = AttestationGenerator(backend)
        bundle = gen.generate(2024, 12)
        tracker = FindingTracker(backend)
        records = tracker.sync_findings(bundle.unresolved_findings)
        assert len(records) == len(bundle.unresolved_findings)
        for r in records:
            assert r.state == FindingState.NEW

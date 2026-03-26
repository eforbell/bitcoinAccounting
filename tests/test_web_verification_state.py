"""Tests for web wallet verification persistence and posture helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db import SqliteBackend
from web.services.wallet_verification import (
    build_portfolio_verification_posture,
    ensure_wallet_verification_tables,
    get_latest_wallet_verification,
    list_wallet_verification_runs,
    record_wallet_verification_run,
)


def test_record_wallet_verification_run_persists_latest_state() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    ensure_wallet_verification_tables(backend)

    resource = record_wallet_verification_run(
        backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
        ledger_balance=1.25,
        verified_balance=1.25,
        chain_height=942151,
        branch_count=2,
        descriptor_count=1,
        highest_scanned_index=42,
        highest_used_index=9,
        scan_ceiling=50,
        gap_limit=20,
    )

    latest = get_latest_wallet_verification(backend, "Coldcard")
    assert latest is not None
    assert latest.verification_id == resource.verification_id
    assert latest.status == "verified"
    assert latest.coverage == "full"
    assert latest.ledger_balance == 1.25
    assert latest.verified_balance == 1.25
    assert latest.highest_scanned_index == 42
    assert latest.scan_ceiling == 50


def test_list_wallet_verification_runs_orders_newest_first() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    older = datetime.now(timezone.utc) - timedelta(days=3)
    newer = older + timedelta(days=1)
    record_wallet_verification_run(
        backend,
        wallet_id="Vault",
        status="failed",
        coverage="partial",
        verified_at=older,
    )
    record_wallet_verification_run(
        backend,
        wallet_id="Vault",
        status="verified",
        coverage="full",
        verified_at=newer,
    )

    runs = list_wallet_verification_runs(backend, "Vault")
    assert len(runs) == 2
    assert runs[0].status == "verified"
    assert runs[1].status == "failed"


def test_portfolio_verification_posture_is_strict() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    record_wallet_verification_run(
        backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
    )
    record_wallet_verification_run(
        backend,
        wallet_id="Vault",
        status="verified",
        coverage="partial",
    )

    posture = build_portfolio_verification_posture(
        backend,
        eligible_wallet_ids=["Coldcard", "Vault"],
    )
    assert posture.status == "partial_coverage"
    assert posture.verified_wallet_count == 1
    assert posture.partial_wallet_count == 1


def test_portfolio_verification_posture_marks_missing_wallets_stale() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    record_wallet_verification_run(
        backend,
        wallet_id="Coldcard",
        status="verified",
        coverage="full",
    )

    posture = build_portfolio_verification_posture(
        backend,
        eligible_wallet_ids=["Coldcard", "NewWallet"],
    )
    assert posture.status == "stale"
    assert posture.stale_wallet_count == 1


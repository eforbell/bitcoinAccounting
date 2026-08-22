"""Tests for web wallet verification persistence and posture helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db import SqliteBackend
from db.queries.wallet import WalletQuery
from web.services.proof_of_spend import (
    get_latest_proof_of_spend,
    record_proof_of_spend_result,
)
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


def test_latest_proof_of_spend_keeps_history_but_returns_newest_result() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    older = datetime.now(timezone.utc) - timedelta(days=1)
    newer = older + timedelta(hours=2)
    record_proof_of_spend_result(
        backend,
        wallet_id="Coldcard",
        accepted=False,
        txid="a" * 64,
        reject_reason="missing-inputs",
        tested_at=older,
    )
    accepted = record_proof_of_spend_result(
        backend,
        wallet_id="Coldcard",
        accepted=True,
        txid="b" * 64,
        virtual_size=141,
        base_fee_btc=0.0000141,
        tested_at=newer,
    )

    latest = get_latest_proof_of_spend(backend, "Coldcard")
    count = backend.execute_scalar(
        "SELECT COUNT(*) FROM web_wallet_proof_of_spend_runs WHERE wallet_id = :wallet_id",
        {"wallet_id": "Coldcard"},
    )

    assert count == 2
    assert latest is not None
    assert latest.proof_id == accepted.proof_id
    assert latest.accepted is True
    assert latest.txid == "b" * 64
    assert latest.wallet_binding == "operator_attested"


def test_wallet_rename_moves_proof_and_verification_records() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    wallets = WalletQuery(backend)
    wallets.add_wallet("Old Vault", "hardware", "self-custodied")
    proof = record_proof_of_spend_result(
        backend,
        wallet_id="Old Vault",
        accepted=True,
        txid="c" * 64,
    )
    verification = record_wallet_verification_run(
        backend,
        wallet_id="Old Vault",
        status="verified",
        coverage="full",
    )

    wallets.rename_wallet("Old Vault", "Vault")

    renamed_proof = get_latest_proof_of_spend(backend, "Vault")
    renamed_verification = get_latest_wallet_verification(backend, "Vault")
    assert renamed_proof is not None
    assert renamed_proof.proof_id == proof.proof_id
    assert renamed_verification is not None
    assert renamed_verification.verification_id == verification.verification_id
    assert get_latest_proof_of_spend(backend, "Old Vault") is None
    assert get_latest_wallet_verification(backend, "Old Vault") is None

    wallets.add_wallet("Old Vault", "hardware", "self-custodied")
    assert get_latest_proof_of_spend(backend, "Old Vault") is None
    assert get_latest_wallet_verification(backend, "Old Vault") is None


def test_wallet_merge_retargets_history_and_keeps_newest_verification_state() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    wallets = WalletQuery(backend)
    wallets.add_wallet("Source", "hardware", "self-custodied")
    wallets.add_wallet("Target", "hardware", "self-custodied")
    older = datetime.now(timezone.utc) - timedelta(days=1)
    newer = older + timedelta(hours=2)

    record_proof_of_spend_result(
        backend,
        wallet_id="Target",
        accepted=False,
        txid="d" * 64,
        tested_at=older,
    )
    newest_proof = record_proof_of_spend_result(
        backend,
        wallet_id="Source",
        accepted=True,
        txid="e" * 64,
        tested_at=newer,
    )
    record_wallet_verification_run(
        backend,
        wallet_id="Target",
        status="stale",
        coverage="full",
        verified_at=older,
    )
    newest_verification = record_wallet_verification_run(
        backend,
        wallet_id="Source",
        status="verified",
        coverage="full",
        verified_at=newer,
    )

    wallets.merge_wallets("Source", "Target")

    merged_proof = get_latest_proof_of_spend(backend, "Target")
    merged_verification = get_latest_wallet_verification(backend, "Target")
    assert merged_proof is not None
    assert merged_proof.proof_id == newest_proof.proof_id
    assert merged_verification is not None
    assert merged_verification.verification_id == newest_verification.verification_id
    assert backend.execute_scalar(
        "SELECT COUNT(*) FROM web_wallet_proof_of_spend_runs WHERE wallet_id = :wallet_id",
        {"wallet_id": "Target"},
    ) == 2
    assert backend.execute_scalar(
        "SELECT COUNT(*) FROM web_wallet_verification_runs WHERE wallet_id = :wallet_id",
        {"wallet_id": "Target"},
    ) == 2
    assert get_latest_proof_of_spend(backend, "Source") is None
    assert get_latest_wallet_verification(backend, "Source") is None


def test_legacy_orphan_history_blocks_wallet_name_reuse() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    wallets = WalletQuery(backend)
    wallets.add_wallet("Current", "hardware", "self-custodied")
    current_state = record_wallet_verification_run(
        backend,
        wallet_id="Current",
        status="verified",
        coverage="full",
    )
    orphan_state = record_wallet_verification_run(
        backend,
        wallet_id="Legacy Name",
        status="stale",
        coverage="full",
    )
    record_proof_of_spend_result(
        backend,
        wallet_id="Legacy Name",
        accepted=True,
        txid="f" * 64,
    )

    with pytest.raises(ValueError, match="retained verification history"):
        wallets.rename_wallet("Current", "Legacy Name")
    with pytest.raises(ValueError, match="retained verification history"):
        wallets.add_wallet("Legacy Name", "hardware", "self-custodied")

    current = get_latest_wallet_verification(backend, "Current")
    orphan = get_latest_wallet_verification(backend, "Legacy Name")
    assert current is not None
    assert current.verification_id == current_state.verification_id
    assert orphan is not None
    assert orphan.verification_id == orphan_state.verification_id
    assert get_latest_proof_of_spend(backend, "Legacy Name") is not None

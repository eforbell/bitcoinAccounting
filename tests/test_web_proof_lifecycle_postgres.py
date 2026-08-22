"""PostgreSQL concurrency coverage for proof and wallet lifecycle writes."""

from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from db import PostgresBackend
from db.queries.wallet import WalletQuery
from db.schema import create_tables
from web.services.proof_of_spend import (
    ensure_proof_of_spend_table,
    get_latest_proof_of_spend,
    record_proof_of_spend_result,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("PGHOST"),
    reason="PostgreSQL not configured (PGHOST not set)",
)


def test_concurrent_proof_insert_is_retargeted_by_wallet_merge() -> None:
    """Merge locks source before history moves, then includes a waiting proof."""
    suffix = uuid4().hex
    source_id = f"proof-source-{suffix}"
    target_id = f"proof-target-{suffix}"
    setup_backend = PostgresBackend()
    proof_backend = PostgresBackend()
    merge_backend = PostgresBackend()
    locked = threading.Event()
    release_proof = threading.Event()
    merge_done = threading.Event()
    failures: list[BaseException] = []
    proof_thread: threading.Thread | None = None
    merge_thread: threading.Thread | None = None

    try:
        create_tables(setup_backend)
        ensure_proof_of_spend_table(setup_backend)
        setup_wallets = WalletQuery(setup_backend)
        setup_wallets.add_wallet(source_id, "hardware", "self-custodied")
        setup_wallets.add_wallet(target_id, "hardware", "self-custodied")

        original_execute_one = proof_backend.execute_one

        def pause_after_wallet_lock(
            query: str,
            params: dict[str, object] | None = None,
        ) -> dict[str, object] | None:
            row = original_execute_one(query, params)
            if "FROM wallets" in query and "FOR UPDATE" in query:
                locked.set()
                if not release_proof.wait(timeout=5):
                    raise TimeoutError("Timed out waiting to release proof insert")
            return row

        proof_backend.execute_one = pause_after_wallet_lock  # type: ignore[method-assign]

        def insert_proof() -> None:
            try:
                record_proof_of_spend_result(
                    proof_backend,
                    wallet_id=source_id,
                    accepted=True,
                    txid="a" * 64,
                    require_existing_wallet=True,
                )
            except BaseException as exc:  # pragma: no cover - thread handoff
                failures.append(exc)

        def merge_wallets() -> None:
            try:
                WalletQuery(merge_backend).merge_wallets(source_id, target_id)
            except BaseException as exc:  # pragma: no cover - thread handoff
                failures.append(exc)
            finally:
                merge_done.set()

        proof_thread = threading.Thread(target=insert_proof)
        merge_thread = threading.Thread(target=merge_wallets)
        proof_thread.start()
        assert locked.wait(timeout=5), "Proof insert did not acquire its wallet lock"
        merge_thread.start()
        assert not merge_done.wait(timeout=0.25), "Merge bypassed the proof wallet lock"

        release_proof.set()
        proof_thread.join(timeout=5)
        merge_thread.join(timeout=5)
        assert not proof_thread.is_alive()
        assert not merge_thread.is_alive()
        assert failures == []

        latest = get_latest_proof_of_spend(setup_backend, target_id)
        assert latest is not None
        assert latest.txid == "a" * 64
        assert get_latest_proof_of_spend(setup_backend, source_id) is None
        assert setup_backend.execute_scalar(
            "SELECT COUNT(*) FROM wallets WHERE wallet_id = :wallet_id",
            {"wallet_id": source_id},
        ) == 0
    finally:
        release_proof.set()
        if proof_thread is not None:
            proof_thread.join(timeout=5)
        if merge_thread is not None:
            merge_thread.join(timeout=5)
        for backend in (setup_backend, proof_backend, merge_backend):
            try:
                backend.rollback()
                backend.execute(
                    """
                    DELETE FROM web_wallet_proof_of_spend_runs
                    WHERE wallet_id IN (:source_id, :target_id)
                    """,
                    {"source_id": source_id, "target_id": target_id},
                )
                backend.execute(
                    "DELETE FROM wallets WHERE wallet_id IN (:source_id, :target_id)",
                    {"source_id": source_id, "target_id": target_id},
                )
                backend.commit()
            except Exception:
                backend.rollback()
            finally:
                backend.close()

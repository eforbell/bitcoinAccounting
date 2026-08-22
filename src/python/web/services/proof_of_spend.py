"""Non-broadcast proof-of-spend checks backed by Bitcoin Core."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from bitcoinAccounts import BitcoinAccounts
from db import DatabaseBackend
from web.config import WebConfig
from web.models_verification import (
    ProofOfSpendCreateRequest,
    ProofOfSpendLatestResponse,
    ProofOfSpendResource,
    ProofOfSpendRunResponse,
)
from web.services.wallet_verification import get_wallet_verification_eligibility

_PROOFS_TABLE = "web_wallet_proof_of_spend_runs"


class ProofOfSpendRPCError(RuntimeError):
    """Raised when Bitcoin Core cannot evaluate the finalized transaction."""


class ProofOfSpendRPCClient:
    """Small Bitcoin Core client limited to ``testmempoolaccept``."""

    def __init__(self, config: WebConfig) -> None:
        self._config = config

    def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, Any]:
        """Evaluate one finalized transaction without broadcasting it."""
        rpc_url = (self._config.bitcoin_rpc_url or "").strip()
        if not rpc_url:
            raise ProofOfSpendRPCError("Bitcoin RPC URL is not configured.")

        payload = {
            "jsonrpc": "1.0",
            "id": "proof-of-spend",
            "method": "testmempoolaccept",
            "params": [[raw_transaction_hex]],
        }
        try:
            response = requests.post(
                rpc_url,
                json=payload,
                auth=self._rpc_auth(),
                timeout=self._config.bitcoin_rpc_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (OSError, ValueError, requests.RequestException) as exc:
            raise ProofOfSpendRPCError(f"Bitcoin RPC unavailable: {exc}") from exc

        if not isinstance(body, dict):
            raise ProofOfSpendRPCError("Bitcoin Core returned an invalid JSON-RPC response.")
        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ProofOfSpendRPCError(f"Bitcoin RPC error: {message}")

        result = body.get("result")
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            raise ProofOfSpendRPCError("Bitcoin Core returned an invalid testmempoolaccept result.")
        return result[0]

    def _rpc_auth(self) -> tuple[str, str]:
        cookie_file = (self._config.bitcoin_rpc_cookie_file or "").strip()
        if cookie_file:
            return self._load_cookie_auth(cookie_file)
        return (
            (self._config.bitcoin_rpc_user or "").strip(),
            (self._config.bitcoin_rpc_password or "").strip(),
        )

    @staticmethod
    def _load_cookie_auth(cookie_file: str) -> tuple[str, str]:
        try:
            cookie_text = Path(cookie_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ProofOfSpendRPCError(f"Unable to read Bitcoin RPC cookie file: {exc}") from exc
        username, separator, password = cookie_text.partition(":")
        if not separator or not username or not password:
            raise ProofOfSpendRPCError("Bitcoin RPC cookie file is malformed.")
        return username, password


def ensure_proof_of_spend_table(backend: DatabaseBackend) -> None:
    """Create the append-only, web-owned proof record table if absent."""
    backend.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_PROOFS_TABLE} (
            proof_id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            status TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            txid TEXT NULL,
            wtxid TEXT NULL,
            virtual_size INTEGER NULL,
            base_fee_btc REAL NULL,
            reject_reason TEXT NULL,
            tested_at TEXT NOT NULL
        )
        """
    )
    backend.execute(
        f"""
        CREATE INDEX IF NOT EXISTS web_wallet_proof_of_spend_wallet_time
        ON {_PROOFS_TABLE} (wallet_id, tested_at)
        """
    )
    backend.commit()


def _row_to_resource(row: dict[str, object]) -> ProofOfSpendResource:
    return ProofOfSpendResource(
        proof_id=str(row["proof_id"]),
        wallet_id=str(row["wallet_id"]),
        status=str(row["status"]),
        accepted=bool(row["accepted"]),
        txid=str(row["txid"]) if row["txid"] is not None else None,
        wtxid=str(row["wtxid"]) if row["wtxid"] is not None else None,
        virtual_size=(
            int(str(row["virtual_size"])) if row["virtual_size"] is not None else None
        ),
        base_fee_btc=(
            float(str(row["base_fee_btc"])) if row["base_fee_btc"] is not None else None
        ),
        reject_reason=str(row["reject_reason"]) if row["reject_reason"] is not None else None,
        tested_at=datetime.fromisoformat(str(row["tested_at"])),
    )


def record_proof_of_spend_result(
    backend: DatabaseBackend,
    *,
    wallet_id: str,
    accepted: bool,
    txid: str | None = None,
    wtxid: str | None = None,
    virtual_size: int | None = None,
    base_fee_btc: float | None = None,
    reject_reason: str | None = None,
    tested_at: datetime | None = None,
) -> ProofOfSpendResource:
    """Persist one result without retaining the finalized transaction hex."""
    ensure_proof_of_spend_table(backend)
    params = {
        "proof_id": str(uuid4()),
        "wallet_id": wallet_id,
        "status": "accepted" if accepted else "rejected",
        "accepted": 1 if accepted else 0,
        "txid": txid,
        "wtxid": wtxid,
        "virtual_size": virtual_size,
        "base_fee_btc": base_fee_btc,
        "reject_reason": reject_reason,
        "tested_at": (tested_at or datetime.now(timezone.utc)).isoformat(),
    }
    backend.execute(
        f"""
        INSERT INTO {_PROOFS_TABLE} (
            proof_id, wallet_id, status, accepted, txid, wtxid,
            virtual_size, base_fee_btc, reject_reason, tested_at
        ) VALUES (
            :proof_id, :wallet_id, :status, :accepted, :txid, :wtxid,
            :virtual_size, :base_fee_btc, :reject_reason, :tested_at
        )
        """,
        params,
    )
    backend.commit()
    row = backend.execute_one(
        f"SELECT * FROM {_PROOFS_TABLE} WHERE proof_id = :proof_id",
        {"proof_id": params["proof_id"]},
    )
    if row is None:
        raise RuntimeError("Proof-of-spend result was persisted but could not be reloaded.")
    return _row_to_resource(row)


def get_latest_proof_of_spend(
    backend: DatabaseBackend,
    wallet_id: str,
) -> ProofOfSpendResource | None:
    """Return only the latest proof result; older records remain in the database."""
    ensure_proof_of_spend_table(backend)
    row = backend.execute_one(
        f"""
        SELECT *
        FROM {_PROOFS_TABLE}
        WHERE wallet_id = :wallet_id
        ORDER BY tested_at DESC
        LIMIT 1
        """,
        {"wallet_id": wallet_id},
    )
    return _row_to_resource(row) if row is not None else None


def get_latest_proof_of_spend_response(
    backend: DatabaseBackend,
    wallet_id: str,
) -> ProofOfSpendLatestResponse:
    return ProofOfSpendLatestResponse(
        wallet_id=wallet_id,
        latest=get_latest_proof_of_spend(backend, wallet_id),
    )


def run_proof_of_spend(
    accounts: BitcoinAccounts,
    config: WebConfig,
    payload: ProofOfSpendCreateRequest,
) -> ProofOfSpendRunResponse:
    """Ask Bitcoin Core to test a signed transaction and persist the verdict."""
    eligibility = get_wallet_verification_eligibility(accounts, payload.wallet_id)
    if not eligibility.eligible:
        raise ValueError(eligibility.reason or "Wallet is not eligible for proof of spend.")

    core_result = ProofOfSpendRPCClient(config).test_mempool_accept(
        payload.raw_transaction_hex
    )
    allowed = core_result.get("allowed")
    if not isinstance(allowed, bool):
        raise ProofOfSpendRPCError("Bitcoin Core omitted the mempool acceptance verdict.")

    fees = core_result.get("fees")
    base_fee = fees.get("base") if isinstance(fees, dict) else None
    try:
        virtual_size = (
            int(core_result["vsize"]) if core_result.get("vsize") is not None else None
        )
        base_fee_btc = float(base_fee) if base_fee is not None else None
    except (TypeError, ValueError) as exc:
        raise ProofOfSpendRPCError(
            "Bitcoin Core returned invalid proof-of-spend size or fee metadata."
        ) from exc

    reject_reason_value = core_result.get("reject-reason") or core_result.get(
        "package-error"
    )
    resource = record_proof_of_spend_result(
        accounts.backend,
        wallet_id=payload.wallet_id,
        accepted=allowed,
        txid=str(core_result["txid"]) if core_result.get("txid") is not None else None,
        wtxid=str(core_result["wtxid"]) if core_result.get("wtxid") is not None else None,
        virtual_size=virtual_size,
        base_fee_btc=base_fee_btc,
        reject_reason=str(reject_reason_value) if reject_reason_value is not None else None,
    )
    return ProofOfSpendRunResponse(result=resource, broadcast=False)

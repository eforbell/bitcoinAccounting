"""Tests for authenticated wallet verification API routes."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend
from web.services.descriptor_engine import DescriptorEngineError
from web.services.electrum_client import ElectrumClientError


class _FakeEngine:
    def inspect_descriptor(self, descriptor: str):  # type: ignore[no-untyped-def]
        from web.services.descriptor_engine import DescriptorBranch, DescriptorInspection

        return DescriptorInspection(
            normalized_descriptor=descriptor,
            checksum=None,
            is_range=True,
            branches=[DescriptorBranch(branch_name="primary", descriptor=descriptor)],
        )

    def derive_addresses(self, descriptor: str, *, start_index: int, end_index: int):  # type: ignore[no-untyped-def]
        from web.services.descriptor_engine import DerivedAddress

        return [
            DerivedAddress(
                branch_name="primary",
                index=idx,
                address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            )
            for idx in range(start_index, end_index + 1)
        ]


class _FakeElectrum:
    def get_scripthash_balance(self, scripthash: str) -> dict[str, int]:
        return {"confirmed": 25_000_000, "unconfirmed": 0}

    def get_scripthash_balances(self, scripthashes: list[str]) -> dict[str, dict[str, int]]:
        return {
            scripthash: self.get_scripthash_balance(scripthash)
            for scripthash in scripthashes
        }


@pytest.fixture
def seeded_accounts() -> BitcoinAccounts:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    accounts = BitcoinAccounts(backend=backend)

    accounts.wallet_query.add_wallet(
        wallet_id="Coldcard",
        wallet_type="hardware",
        custody="self-custodied",
        description="Primary vault",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="Empty",
        wallet_type="hardware",
        custody="self-custodied",
        description="Unused wallet",
    )
    accounts.wallet_query.add_wallet(
        wallet_id="River",
        wallet_type="exchange",
        custody="custodial",
        description="Broker account",
    )
    accounts.execute_trade(
        trade_date=datetime(2024, 1, 15),
        buy=0.5,
        buy_curr="BTC",
        sell=25000.0,
        sell_curr="USD",
        exchange="Coldcard",
    )

    yield accounts
    accounts.close()


@pytest.fixture
def client(seeded_accounts: BitcoinAccounts) -> TestClient:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_cookie_file="/tmp/fake.cookie",
            electrum_host="127.0.0.1",
            electrum_port=50001,
            verification_recency_days=30,
        )
    )
    app.dependency_overrides[get_request_accounts] = lambda: seeded_accounts
    app.dependency_overrides[get_request_backend] = lambda: seeded_accounts.backend

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"passphrase": "orange-hodl"})
    assert login.status_code == 200
    return client


def test_verification_routes_require_auth() -> None:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    client = TestClient(app)

    assert client.get("/api/verification/wallets/Coldcard").status_code == 401
    assert client.post("/api/verification/run", json={"wallet_id": "Coldcard"}).status_code == 401
    assert client.get("/api/verification/proof-of-spend/wallets/Coldcard").status_code == 401
    assert client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "00"},
    ).status_code == 401


def test_verification_history_empty(client: TestClient) -> None:
    response = client.get("/api/verification/wallets/Coldcard")

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_id"] == "Coldcard"
    assert body["latest"] is None
    assert body["runs"] == []


def test_verification_run_not_meaningful_for_empty_wallet(client: TestClient) -> None:
    response = client.post(
        "/api/verification/run",
        json={"wallet_id": "Empty"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meaningful_to_verify"] is False
    assert body["result"]["status"] == "not_meaningful"


def test_verification_run_rejects_custodial_wallet(client: TestClient) -> None:
    response = client.post(
        "/api/verification/run",
        json={
            "wallet_id": "River",
            "descriptor": "wpkh(xpub/<0;1>/*)",
            "first_scan_ceiling": 2,
        },
    )

    assert response.status_code == 400
    assert "self-custodied or multisig" in response.json()["detail"]


def test_verification_run_rejects_unknown_wallet(client: TestClient) -> None:
    response = client.post(
        "/api/verification/run",
        json={"wallet_id": "DoesNotExist", "descriptor": "wpkh(xpub/<0;1>/*)"},
    )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_verification_run_success_path_with_fakes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "web.services.wallet_verification.BitcoindDescriptorEngine",
        lambda config: _FakeEngine(),
    )
    monkeypatch.setattr(
        "web.services.wallet_verification._build_electrum_client",
        lambda config: _FakeElectrum(),
    )

    response = client.post(
        "/api/verification/run",
        json={
            "wallet_id": "Coldcard",
            "descriptor": "wpkh(xpub/<0;1>/*)",
            "first_scan_ceiling": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meaningful_to_verify"] is True
    assert body["result"]["status"] == "verified"
    assert body["result"]["coverage"] == "full"
    assert body["result"]["verified_balance"] == 0.5

    history = client.get("/api/verification/wallets/Coldcard")
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["latest"]["status"] == "verified"
    assert len(history_body["runs"]) == 1


def test_verification_run_returns_502_for_descriptor_backend_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenEngine:
        def inspect_descriptor(self, descriptor: str):  # type: ignore[no-untyped-def]
            raise DescriptorEngineError("http 404")

    monkeypatch.setattr(
        "web.services.wallet_verification.BitcoindDescriptorEngine",
        lambda config: _BrokenEngine(),
    )

    response = client.post(
        "/api/verification/run",
        json={"wallet_id": "Coldcard", "descriptor": "wpkh(xpub/<0;1>/*)"},
    )

    assert response.status_code == 502
    assert "Bitcoin Core descriptor RPC unavailable" in response.json()["detail"]


def test_verification_run_returns_502_for_electrum_backend_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenElectrum:
        def get_scripthash_balances(self, scripthashes: list[str]) -> dict[str, dict[str, int]]:
            raise ElectrumClientError("connection reset")

    monkeypatch.setattr(
        "web.services.wallet_verification.BitcoindDescriptorEngine",
        lambda config: _FakeEngine(),
    )
    monkeypatch.setattr(
        "web.services.wallet_verification._build_electrum_client",
        lambda config: _BrokenElectrum(),
    )

    response = client.post(
        "/api/verification/run",
        json={"wallet_id": "Coldcard", "descriptor": "wpkh(xpub/<0;1>/*)"},
    )

    assert response.status_code == 502
    assert "Electrum verification backend unavailable" in response.json()["detail"]


def test_verification_run_rejects_excessive_scan_ceiling(client: TestClient) -> None:
    response = client.post(
        "/api/verification/run",
        json={
            "wallet_id": "Coldcard",
            "descriptor": "wpkh(xpub/<0;1>/*)",
            "first_scan_ceiling": 1000001,
        },
    )

    assert response.status_code == 422


def test_proof_of_spend_acceptance_is_persisted_without_raw_transaction(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _AcceptingCore:
        def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, object]:
            assert raw_transaction_hex == "deadbeef"
            return {
                "txid": "a" * 64,
                "wtxid": "b" * 64,
                "allowed": True,
                "vsize": 141,
                "fees": {"base": 0.00001410},
            }

    monkeypatch.setattr(
        "web.services.proof_of_spend.ProofOfSpendRPCClient",
        lambda config: _AcceptingCore(),
    )

    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "DEADBEEF"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["broadcast"] is False
    assert body["result"]["accepted"] is True
    assert body["result"]["status"] == "accepted"
    assert body["result"]["wallet_binding"] == "operator_attested"
    assert body["result"]["txid"] == "a" * 64
    assert body["result"]["virtual_size"] == 141
    assert "raw_transaction_hex" not in body["result"]

    latest = client.get("/api/verification/proof-of-spend/wallets/Coldcard")
    assert latest.status_code == 200
    assert latest.json()["latest"]["proof_id"] == body["result"]["proof_id"]

    columns = seeded_accounts.backend.execute(
        "PRAGMA table_info(web_wallet_proof_of_spend_runs)"
    )
    assert "raw_transaction_hex" not in {row["name"] for row in columns}


def test_proof_of_spend_rejection_records_core_reason(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RejectingCore:
        def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, object]:
            return {
                "txid": "c" * 64,
                "wtxid": "d" * 64,
                "allowed": False,
                "reject-reason": "missing-inputs",
            }

    monkeypatch.setattr(
        "web.services.proof_of_spend.ProofOfSpendRPCClient",
        lambda config: _RejectingCore(),
    )

    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "00"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["accepted"] is False
    assert response.json()["result"]["status"] == "rejected"
    assert response.json()["result"]["reject_reason"] == "missing-inputs"


def test_proof_of_spend_rejects_invalid_hex(client: TestClient) -> None:
    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "not-hex"},
    )

    assert response.status_code == 422


def test_proof_of_spend_rejects_custodial_wallet(client: TestClient) -> None:
    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "River", "raw_transaction_hex": "00"},
    )

    assert response.status_code == 400
    assert "self-custodied or multisig" in response.json()["detail"]


def test_proof_of_spend_returns_502_when_core_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from web.services.proof_of_spend import ProofOfSpendRPCError

    class _UnavailableCore:
        def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, object]:
            raise ProofOfSpendRPCError("connection refused")

    monkeypatch.setattr(
        "web.services.proof_of_spend.ProofOfSpendRPCClient",
        lambda config: _UnavailableCore(),
    )

    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "00"},
    )

    assert response.status_code == 502
    assert "proof-of-spend check unavailable" in response.json()["detail"]


def test_proof_of_spend_does_not_orphan_result_when_wallet_changes_during_rpc(
    client: TestClient,
    seeded_accounts: BitcoinAccounts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RenamingCore:
        def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, object]:
            seeded_accounts.wallet_query.rename_wallet("Coldcard", "Renamed Coldcard")
            return {
                "txid": "f" * 64,
                "wtxid": "e" * 64,
                "allowed": True,
            }

    monkeypatch.setattr(
        "web.services.proof_of_spend.ProofOfSpendRPCClient",
        lambda config: _RenamingCore(),
    )

    response = client.post(
        "/api/verification/proof-of-spend/run",
        json={"wallet_id": "Coldcard", "raw_transaction_hex": "00"},
    )

    assert response.status_code == 400
    assert "Wallet changed" in response.json()["detail"]
    assert client.get(
        "/api/verification/proof-of-spend/wallets/Coldcard"
    ).json()["latest"] is None
    assert client.get(
        "/api/verification/proof-of-spend/wallets/Renamed%20Coldcard"
    ).json()["latest"] is None

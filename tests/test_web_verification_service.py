"""Tests for manual wallet verification orchestration."""

from __future__ import annotations

from datetime import datetime

import pytest

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.config import WebConfig
from web.models_verification import WalletVerificationCreateRequest
from web.services.wallet_verification import run_manual_wallet_verification


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
        return {"confirmed": 50_000_000, "unconfirmed": 0}

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


def test_run_manual_wallet_verification_marks_not_meaningful_for_empty_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    accounts = BitcoinAccounts(backend=backend)
    accounts.wallet_query.add_wallet(
        wallet_id="Empty",
        wallet_type="hardware",
        custody="self-custodied",
    )
    config = WebConfig(verification_recency_days=30)

    response = run_manual_wallet_verification(
        accounts,
        config,
        WalletVerificationCreateRequest(wallet_id="Empty", descriptor="wpkh(xpub/0/*)"),
    )
    assert response.meaningful_to_verify is False
    assert response.result.status == "not_meaningful"
    accounts.close()


def test_run_manual_wallet_verification_records_verified_run(
    seeded_accounts: BitcoinAccounts,
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
    config = WebConfig(
        verification_recency_days=30,
        electrum_host="127.0.0.1",
        electrum_port=50001,
    )

    response = run_manual_wallet_verification(
        seeded_accounts,
        config,
        WalletVerificationCreateRequest(
            wallet_id="Coldcard",
            descriptor="wpkh(xpub/<0;1>/*)",
            first_scan_ceiling=3,
        ),
    )
    assert response.meaningful_to_verify is True
    assert response.result.status == "drift_detected"
    assert response.result.ledger_balance == 0.5
    assert response.result.verified_balance == 1.5
    assert response.result.scan_ceiling == 3

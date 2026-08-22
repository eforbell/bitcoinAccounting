"""Verification-specific web API models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from web.model_base import APIModel


class WalletVerificationResource(APIModel):
    """One persisted wallet verification result."""

    verification_id: str
    wallet_id: str
    status: str
    coverage: str
    descriptor_source_type: str
    recency_window_days: int
    is_recent: bool
    ledger_balance: float | None = None
    verified_balance: float | None = None
    drift_btc: float | None = None
    chain_height: int | None = None
    branch_count: int | None = None
    descriptor_count: int | None = None
    highest_scanned_index: int | None = None
    highest_used_index: int | None = None
    scan_ceiling: int | None = None
    gap_limit: int | None = None
    warning_text: str | None = None
    error_text: str | None = None
    verified_at: datetime
    stale_after: datetime


class WalletVerificationListResponse(APIModel):
    """Wallet verification history payload."""

    wallet_id: str
    latest: WalletVerificationResource | None = None
    runs: list[WalletVerificationResource]


class WalletVerificationEligibilityResource(APIModel):
    """Operator-facing verification eligibility and guidance for one wallet."""

    eligible: bool
    reason: str | None = None
    recommended_first_scan_ceiling: int = 50
    supports_combined_descriptor: bool = True
    supports_branch_descriptors: bool = True


class PortfolioVerificationPostureResource(APIModel):
    """Aggregate verification posture for dashboard surfaces."""

    status: str
    recency_window_days: int
    eligible_wallet_count: int
    verified_wallet_count: int
    partial_wallet_count: int
    stale_wallet_count: int
    failed_wallet_count: int
    drift_wallet_count: int
    refreshed_at: datetime


class WalletVerificationCreateRequest(APIModel):
    """Manual verification session request."""

    wallet_id: str = Field(min_length=1)
    descriptor: str | None = None
    external_descriptor: str | None = None
    change_descriptor: str | None = None
    first_scan_ceiling: int | None = Field(default=None, ge=1, le=10_000)
    gap_limit: int | None = Field(default=None, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_descriptor_inputs(self) -> "WalletVerificationCreateRequest":
        if not self.wallet_id.strip():
            raise ValueError("wallet_id must not be blank.")
        return self


class WalletVerificationRunResponse(APIModel):
    """Response payload for one manual verification run."""

    result: WalletVerificationResource
    ledger_transaction_count: int
    meaningful_to_verify: bool


class ProofOfSpendCreateRequest(APIModel):
    """A finalized transaction to evaluate without broadcasting it."""

    wallet_id: str = Field(min_length=1, max_length=255)
    raw_transaction_hex: str = Field(min_length=2, max_length=2_000_000)

    @field_validator("wallet_id")
    @classmethod
    def validate_wallet_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("wallet_id must not be blank.")
        return normalized

    @field_validator("raw_transaction_hex")
    @classmethod
    def validate_raw_transaction_hex(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) % 2:
            raise ValueError("raw_transaction_hex must contain an even number of characters.")
        try:
            bytes.fromhex(normalized)
        except ValueError as exc:
            raise ValueError("raw_transaction_hex must be hexadecimal.") from exc
        if any(character.isspace() for character in normalized):
            raise ValueError("raw_transaction_hex must not contain whitespace.")
        return normalized.lower()


class ProofOfSpendResource(APIModel):
    """Persisted result from Bitcoin Core's non-broadcast mempool evaluation."""

    proof_id: str
    wallet_id: str
    status: str
    accepted: bool
    txid: str | None = None
    wtxid: str | None = None
    virtual_size: int | None = None
    base_fee_btc: float | None = None
    reject_reason: str | None = None
    tested_at: datetime


class ProofOfSpendLatestResponse(APIModel):
    """Latest proof-of-spend result for one wallet."""

    wallet_id: str
    latest: ProofOfSpendResource | None = None


class ProofOfSpendRunResponse(APIModel):
    """Response from a non-broadcast proof-of-spend test."""

    result: ProofOfSpendResource
    broadcast: bool = False

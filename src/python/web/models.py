"""Canonical JSON models for the web API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base model with strict-ish API defaults."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class HealthResponse(APIModel):
    """Health endpoint response payload."""

    status: str
    service: str
    environment: str
    timestamp: datetime


class ReadinessResponse(APIModel):
    """Readiness endpoint response payload."""

    status: str
    service: str
    environment: str
    database_backend: str
    database_reachable: bool
    production_policy: str
    timestamp: datetime


class WalletResource(APIModel):
    """Canonical wallet resource for web clients."""

    wallet_id: str
    wallet_type: str
    custody: str
    description: str | None = None
    active: bool


class TransactionResource(APIModel):
    """Canonical ledger transaction resource for web clients."""

    transaction_id: int
    created_at: str
    transaction_type: str | None = None
    buy_amount: float | None = None
    buy_currency: str | None = None
    sell_amount: float | None = None
    sell_currency: str | None = None
    fee_amount: float | None = None
    fee_currency: str | None = None
    wallet_id: str | None = None
    group: str | None = None
    comment: str | None = None
    deleted: bool = False


class PortfolioSummaryResource(APIModel):
    """Top-level portfolio summary for dashboard consumers."""

    coin: str
    total_balance: float
    average_cost_basis_usd: float | None = None
    wallet_count: int
    active_wallet_count: int


class GainsSummaryResource(APIModel):
    """Summary of realized gains for a tax period."""

    tax_year: int
    coin: str
    wallet_id: str | None = None
    lot_count: int
    proceeds_usd: float
    cost_basis_usd: float
    gain_loss_usd: float
    short_term_lot_count: int
    long_term_lot_count: int


class TaxPolicyWarningResource(APIModel):
    """Operator-facing tax policy warning or guidance."""

    code: str
    severity: str
    message: str
    reference_doc: str | None = None


class TaxPolicyResource(APIModel):
    """Static tax policy metadata for web clients."""

    wallet_separation_required_from_tax_year: int
    strict_wallet_enforcement_for_exports: bool
    reference_doc: str
    summary: str


class GainsLotResource(APIModel):
    """A single 8949/1099-B lot entry."""

    description: str
    date_acquired: str
    date_sold: str
    proceeds_usd: float
    cost_basis_usd: float
    term: str


class GainsWorksheetEntryResource(APIModel):
    """Detailed worksheet row explaining one matched lot."""

    sale_date: str
    sale_quantity: float
    proceeds_usd: float
    acquire_date: str
    lot_quantity: float
    unit_cost_basis_usd: float
    total_cost_basis_usd: float
    holding_days: int | None = None
    term: str
    gain_loss_usd: float
    missing_basis: bool = False


class GainsReportResponse(APIModel):
    """Tax gains report payload for web clients."""

    summary: GainsSummaryResource
    lots: list[GainsLotResource]
    worksheet: list[GainsWorksheetEntryResource]
    warnings: list[TaxPolicyWarningResource]


class ForecastSummaryResource(APIModel):
    """Summary of a hypothetical sale forecast."""

    coin: str
    wallet_id: str | None = None
    quantity: float
    sale_price_usd: float | None = None
    total_cost_basis_usd: float
    total_proceeds_usd: float
    short_term_quantity: float
    long_term_quantity: float
    missing_basis_quantity: float


class ForecastLotResource(APIModel):
    """A FIFO lot consumed by a hypothetical sale."""

    acquire_date: str | None = None
    quantity: float
    unit_cost_usd: float
    cost_basis_usd: float
    holding_days: int
    term: str
    missing_basis: bool = False


class ForecastResponse(APIModel):
    """Forecast payload for hypothetical tax planning."""

    summary: ForecastSummaryResource
    current_balance: float
    lots: list[ForecastLotResource]
    warnings: list[TaxPolicyWarningResource]


class TaxPresetResource(APIModel):
    """Saved tax filter preset for the private operator."""

    preset_id: str
    name: str
    preset_type: str
    coin: str
    tax_year: int | None = None
    wallet_id: str | None = None
    quantity: float | None = None
    sale_price_usd: float | None = None
    created_at: datetime
    updated_at: datetime


class TaxPresetCreateRequest(APIModel):
    """Create a saved tax preset."""

    name: str
    preset_type: str
    coin: str = "BTC"
    tax_year: int | None = None
    wallet_id: str | None = None
    quantity: float | None = None
    sale_price_usd: float | None = None


class TaxHistoryEntryResource(APIModel):
    """Recent tax workflow run for quick recall."""

    history_id: str
    action: str
    coin: str
    tax_year: int | None = None
    wallet_id: str | None = None
    quantity: float | None = None
    sale_price_usd: float | None = None
    artifact_type: str | None = None
    status: str
    created_at: datetime


class LoginRequest(APIModel):
    """Login request payload."""

    passphrase: str


class SessionResponse(APIModel):
    """Auth/session response payload."""

    authenticated: bool
    username: str

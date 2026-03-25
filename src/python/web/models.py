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


class ChainStatusResponse(APIModel):
    """Chain status payload for optional Bitcoin node presence."""

    enabled: bool = False
    available: bool = False
    source: str = "bitcoind"
    network: str | None = None
    block_height: int | None = None
    header_height: int | None = None
    verification_progress: float | None = None
    is_synced: bool | None = None
    last_block_at: datetime | None = None
    seconds_since_last_block: int | None = None
    peer_count: int | None = None
    mempool_tx_count: int | None = None
    mempool_usage_bytes: int | None = None
    pruned: bool | None = None
    warnings: list[str]
    refreshed_at: datetime


class WalletResource(APIModel):
    """Canonical wallet resource for web clients."""

    wallet_id: str
    wallet_type: str
    custody: str
    description: str | None = None
    notes: str | None = None
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


class CustodyBreakdownResource(APIModel):
    """Custody bucket totals and percentages for dashboard consumers."""

    custody: str
    balance: float
    percentage: float


class WalletBalanceResource(APIModel):
    """Wallet balance card row for the portfolio dashboard."""

    wallet_id: str
    wallet_type: str
    custody: str
    description: str | None = None
    active: bool
    balance: float
    percentage: float


class PortfolioDashboardResponse(APIModel):
    """Dashboard payload combining top-level portfolio reads."""

    summary: PortfolioSummaryResource
    custody_breakdown: list[CustodyBreakdownResource]
    wallets: list[WalletBalanceResource]
    recent_transactions: list[TransactionResource]
    using_inferred_custody: bool = False


class WalletDetailResponse(APIModel):
    """Single wallet detail payload with balance and recent activity."""

    wallet: WalletBalanceResource
    recent_transactions: list[TransactionResource]


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


class LedgerSummaryResource(APIModel):
    """Aggregate stats for a filtered ledger view."""

    coin: str = "BTC"
    credits: float
    debits: float
    fees: float
    balance: float
    count: int


class LedgerResponse(APIModel):
    """Paginated ledger response with summary stats."""

    transactions: list[TransactionResource]
    summary: LedgerSummaryResource
    page: int
    per_page: int
    total: int


class BuyRequest(APIModel):
    """Record a BTC purchase."""

    trade_date: str
    buy: float
    buy_curr: str = "BTC"
    sell: float
    sell_curr: str = "USD"
    fee: float = 0.0
    fee_curr: str = "USD"
    exchange: str
    comment: str = ""


class SellRequest(APIModel):
    """Record a BTC sale."""

    trade_date: str
    buy: float
    buy_curr: str = "USD"
    sell: float
    sell_curr: str = "BTC"
    fee: float = 0.0
    fee_curr: str = "USD"
    exchange: str
    comment: str = ""


class TransferRequest(APIModel):
    """Record a wallet-to-wallet transfer."""

    transfer_date: str
    amount: float
    coin: str = "BTC"
    from_wallet: str
    to_wallet: str
    fee: float = 0.0
    fee_coin: str = "BTC"
    comment: str = ""


class InterestRequest(APIModel):
    """Record earned interest/rewards."""

    interest_date: str
    amount: float
    currency: str = "BTC"
    exchange: str
    comment: str = ""


class TransactionUpdateRequest(APIModel):
    """Partial update for a ledger transaction."""

    created_at: str | None = None
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


class WalletListResource(APIModel):
    """Wallet with transaction count for list views."""

    wallet_id: str
    wallet_type: str
    custody: str
    description: str | None = None
    notes: str | None = None
    active: bool
    transaction_count: int


class WalletListResponse(APIModel):
    """Paginated wallet list."""

    wallets: list[WalletListResource]


class WalletCreateRequest(APIModel):
    """Create a new wallet."""

    wallet_id: str
    wallet_type: str
    custody: str
    description: str | None = None
    notes: str | None = None


class WalletUpdateRequest(APIModel):
    """Partial update for wallet metadata."""

    wallet_type: str | None = None
    custody: str | None = None
    description: str | None = None
    notes: str | None = None
    active: bool | None = None


class WalletRenameRequest(APIModel):
    """Rename a wallet."""

    wallet_id: str
    new_wallet_id: str


class WalletMergeRequest(APIModel):
    """Merge source wallet into target."""

    source_wallet_id: str
    target_wallet_id: str


class TradeResource(APIModel):
    """Single trade with cost basis for the trades view."""

    date: str
    trade_type: str
    quantity: float
    trade_currency: str
    unit_cost_usd: float | None = None
    total_cost_usd: float | None = None
    exchange: str | None = None


class TradesResponse(APIModel):
    """Paginated trade history response."""

    trades: list[TradeResource]
    page: int
    per_page: int
    total: int


class ExchangeLiquidityResource(APIModel):
    """Per-exchange liquidity summary row."""

    exchange: str
    total_purchased: float
    current_balance: float
    avg_cost_usd: float | None = None


class CostBasisSummaryResource(APIModel):
    """Overall cost basis and holdings summary."""

    total_purchased: float
    total_usd_spent: float
    avg_cost_basis_usd: float | None = None
    still_at_exchanges: float
    in_cold_storage: float
    total_holdings: float


class LiquidityResponse(APIModel):
    """Exchange liquidity with cost basis summary."""

    exchanges: list[ExchangeLiquidityResource]
    summary: CostBasisSummaryResource


class LoginRequest(APIModel):
    """Login request payload."""

    passphrase: str


class SessionResponse(APIModel):
    """Auth/session response payload."""

    authenticated: bool
    username: str

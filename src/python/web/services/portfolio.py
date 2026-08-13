"""Portfolio/dashboard read models for the web UI."""

from __future__ import annotations

from typing import Any

from bitcoinAccounts import BitcoinAccounts
from web.models import (
    CustodyBreakdownResource,
    PortfolioDashboardResponse,
    PortfolioSummaryResource,
    TransactionResource,
    WalletBalanceResource,
    WalletDetailResponse,
)
from web.services.wallet_verification import (
    build_portfolio_verification_posture,
    get_latest_wallet_verification,
    get_wallet_verification_eligibility,
)

_CUSTODY_PRIORITY = {
    "self-custodied": 0,
    "multisig": 1,
    "custodial": 2,
    "unknown": 3,
}


def _normalize_custody(custody: str | None) -> str:
    value = (custody or "unknown").strip().lower()
    if value in {"self-custodied", "self", "cold", "hardware", "hot"}:
        return "self-custodied"
    if value in {"custodial", "exchange", "third-party"}:
        return "custodial"
    if value in {"multisig", "multi-sig", "collaborative"}:
        return "multisig"
    return "unknown"


def _build_transaction_resource(row: dict[str, Any]) -> TransactionResource:
    return TransactionResource(
        transaction_id=int(row["ID"]),
        created_at=str(row["Date"]),
        transaction_type=row.get("Type"),
        buy_amount=float(row["Buy"]) if row.get("Buy") is not None else None,
        buy_currency=row.get("Buy Cur."),
        sell_amount=float(row["Sell"]) if row.get("Sell") is not None else None,
        sell_currency=row.get("Sell Cur."),
        fee_amount=float(row["Fee"]) if row.get("Fee") is not None else None,
        fee_currency=row.get("Fee Cur."),
        wallet_id=row.get("Exchange"),
        group=row.get("Group"),
        comment=row.get("Comment"),
        deleted=bool(row.get("Deleted") or False),
    )


def build_portfolio_dashboard(
    accounts: BitcoinAccounts,
    coin: str = "BTC",
    recent_limit: int = 5,
) -> PortfolioDashboardResponse:
    """Build the mobile-first portfolio dashboard payload.

    Wallet balance cards intentionally include only active wallets with nonzero
    balances; inactive dust wallets remain available through wallet management.
    """
    balance = float(accounts.get_balance(coin))
    basis = accounts.get_basis(coin)

    all_wallets = accounts.get_wallets(active_only=False)
    active_wallets = accounts.get_wallets(active_only=True)
    wallet_balances = accounts.get_wallet_balance(coin, None)
    total_balance = sum(float(value) for value in wallet_balances.values())

    using_inferred_custody = False
    custody_totals: dict[str, float] = {
        "self-custodied": 0.0,
        "multisig": 0.0,
        "custodial": 0.0,
        "unknown": 0.0,
    }
    wallet_rows: list[WalletBalanceResource] = []
    eligible_wallet_ids: list[str] = []

    for wallet in all_wallets:
        wallet_id = str(wallet.get("wallet_id", ""))
        wallet_balance = float(wallet_balances.get(wallet_id, 0.0))
        active = bool(wallet.get("active", True))
        if not active or wallet_balance == 0:
            continue

        custody = _normalize_custody(wallet.get("custody"))
        percentage = (wallet_balance / total_balance * 100) if total_balance > 0 else 0.0
        eligibility = get_wallet_verification_eligibility(accounts, wallet_id)
        latest_verification = get_latest_wallet_verification(accounts.backend, wallet_id)

        if wallet.get("type") == "unknown":
            using_inferred_custody = True

        wallet_rows.append(
            WalletBalanceResource(
                wallet_id=wallet_id,
                wallet_type=str(wallet.get("type", "unknown")),
                custody=custody,
                description=wallet.get("description"),
                active=active,
                balance=wallet_balance,
                percentage=percentage,
                verification_eligible=eligibility.eligible,
                verification_status=latest_verification.status if latest_verification is not None else None,
                verification_coverage=latest_verification.coverage if latest_verification is not None else None,
                verification_is_recent=latest_verification.is_recent if latest_verification is not None else None,
            )
        )

        if active and wallet_balance > 0 and eligibility.eligible:
            eligible_wallet_ids.append(wallet_id)

        if wallet_balance > 0:
            custody_totals[custody] = custody_totals.get(custody, 0.0) + wallet_balance

    custody_rows = [
        CustodyBreakdownResource(
            custody=custody,
            balance=balance_value,
            percentage=(balance_value / total_balance * 100) if total_balance > 0 else 0.0,
        )
        for custody, balance_value in sorted(
            custody_totals.items(),
            key=lambda item: (_CUSTODY_PRIORITY.get(item[0], 99), -item[1]),
        )
        if balance_value > 0 or custody == "unknown"
    ]

    _headers, transactions = accounts.get_transactions(coin=coin)
    recent_transactions = [
        _build_transaction_resource(row)
        for row in list(reversed(transactions))[:recent_limit]
    ]

    wallet_rows.sort(key=lambda row: (-row.balance, row.wallet_id.lower()))
    portfolio_verification = build_portfolio_verification_posture(
        accounts.backend,
        eligible_wallet_ids=eligible_wallet_ids,
    )

    return PortfolioDashboardResponse(
        summary=PortfolioSummaryResource(
            coin=coin,
            total_balance=balance,
            average_cost_basis_usd=float(basis) if basis is not None else None,
            wallet_count=len(all_wallets),
            active_wallet_count=len(active_wallets),
        ),
        custody_breakdown=custody_rows,
        wallets=wallet_rows,
        portfolio_verification=portfolio_verification,
        recent_transactions=recent_transactions,
        using_inferred_custody=using_inferred_custody,
    )


def build_wallet_detail(
    accounts: BitcoinAccounts,
    wallet_id: str,
    coin: str = "BTC",
    recent_limit: int = 20,
) -> WalletDetailResponse | None:
    """Build a single-wallet detail payload with recent activity."""
    all_wallets = accounts.get_wallets(active_only=False)
    wallet_meta = next(
        (w for w in all_wallets if w.get("wallet_id") == wallet_id), None
    )
    if wallet_meta is None:
        return None

    wallet_balances = accounts.get_wallet_balance(coin, None)
    total_balance = sum(float(v) for v in wallet_balances.values())
    wallet_balance = float(wallet_balances.get(wallet_id, 0.0))
    percentage = (wallet_balance / total_balance * 100) if total_balance > 0 else 0.0

    wallet_resource = WalletBalanceResource(
        wallet_id=wallet_id,
        wallet_type=str(wallet_meta.get("type", "unknown")),
        custody=_normalize_custody(wallet_meta.get("custody")),
        description=wallet_meta.get("description"),
        active=bool(wallet_meta.get("active", True)),
        balance=wallet_balance,
        percentage=percentage,
    )

    _headers, transactions = accounts.get_transactions(coin=coin, wallet=wallet_id)
    recent_transactions = [
        _build_transaction_resource(row)
        for row in list(reversed(transactions))[:recent_limit]
    ]

    return WalletDetailResponse(
        wallet=wallet_resource,
        verification_eligibility=get_wallet_verification_eligibility(accounts, wallet_id),
        latest_verification=get_latest_wallet_verification(accounts.backend, wallet_id),
        recent_transactions=recent_transactions,
    )

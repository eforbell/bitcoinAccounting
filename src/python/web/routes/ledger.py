"""Authenticated ledger explorer routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from bitcoinAccounts import BitcoinAccounts
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts
from web.models import (
    BuyRequest,
    InterestRequest,
    LedgerResponse,
    SellRequest,
    TransactionResource,
    TransactionUpdateRequest,
    TransferRequest,
)
from web.services.ledger import (
    build_ledger_response,
    delete_transaction,
    get_transaction_detail,
    restore_transaction,
    update_transaction,
)

router = APIRouter(
    prefix="/api/ledger",
    tags=["ledger"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("", response_model=LedgerResponse)
def ledger(
    coin: str = Query("BTC", min_length=1),
    wallet: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> LedgerResponse:
    """Return paginated ledger transactions with summary stats."""
    return build_ledger_response(
        accounts,
        coin=coin,
        wallet=wallet,
        start_date=start_date,
        end_date=end_date,
        include_deleted=include_deleted,
        page=page,
        per_page=per_page,
    )


def _parse_date(value: str) -> "datetime":
    """Parse an ISO date string, raising HTTPException on failure."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"Invalid date format: {value!r}")


@router.post("/buy", response_model=dict)
def record_buy(
    body: BuyRequest,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Record a BTC purchase."""
    accounts.execute_trade(
        trade_date=_parse_date(body.trade_date),
        buy=body.buy,
        buy_curr=body.buy_curr,
        sell=body.sell,
        sell_curr=body.sell_curr,
        fee=body.fee,
        fee_curr=body.fee_curr,
        exchange=body.exchange,
        comment=body.comment,
    )
    return {"status": "ok", "action": "buy"}


@router.post("/sell", response_model=dict)
def record_sell(
    body: SellRequest,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Record a BTC sale."""
    accounts.execute_trade(
        trade_date=_parse_date(body.trade_date),
        buy=body.buy,
        buy_curr=body.buy_curr,
        sell=body.sell,
        sell_curr=body.sell_curr,
        fee=body.fee,
        fee_curr=body.fee_curr,
        exchange=body.exchange,
        comment=body.comment,
    )
    return {"status": "ok", "action": "sell"}


@router.post("/transfer", response_model=dict)
def record_transfer(
    body: TransferRequest,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Record a wallet-to-wallet transfer."""
    dt = _parse_date(body.transfer_date)
    accounts.transfer_funds(
        withdraw_date=dt,
        deposit_date=dt,
        tx_amount=body.amount,
        tx_coin=body.coin,
        from_account=body.from_wallet,
        to_account=body.to_wallet,
        fee_amount=body.fee,
        fee_coin=body.fee_coin,
        comment=body.comment,
    )
    return {"status": "ok", "action": "transfer"}


@router.post("/interest", response_model=dict)
def record_interest(
    body: InterestRequest,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Record earned interest or rewards."""
    accounts.interest(
        interest_date=_parse_date(body.interest_date),
        buy=body.amount,
        buy_curr=body.currency,
        exchange=body.exchange,
        comment=body.comment,
    )
    return {"status": "ok", "action": "interest"}


@router.get("/{tx_id}", response_model=TransactionResource)
def transaction_detail(
    tx_id: int,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TransactionResource:
    """Return a single transaction by ID."""
    result = get_transaction_detail(accounts, tx_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result


@router.patch("/{tx_id}", response_model=TransactionResource)
def transaction_update(
    tx_id: int,
    body: TransactionUpdateRequest,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TransactionResource:
    """Edit fields on a transaction."""
    result = update_transaction(accounts, tx_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result


@router.delete("/{tx_id}", response_model=TransactionResource)
def transaction_delete(
    tx_id: int,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TransactionResource:
    """Soft-delete a transaction."""
    result = delete_transaction(accounts, tx_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result


@router.post("/{tx_id}/restore", response_model=TransactionResource)
def transaction_restore(
    tx_id: int,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> TransactionResource:
    """Restore a soft-deleted transaction."""
    result = restore_transaction(accounts, tx_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result

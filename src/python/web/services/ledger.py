"""Ledger explorer read/write models for the web UI."""

from __future__ import annotations

from typing import Any

from bitcoinAccounts import BitcoinAccounts
from web.models import (
    LedgerResponse,
    LedgerSummaryResource,
    TransactionResource,
    TransactionUpdateRequest,
)


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


def _compute_summary(rows: list[dict[str, Any]], coin: str = "BTC") -> LedgerSummaryResource:
    """Compute credits/debits/fees/balance/count over the full (unpaginated) result set."""
    credits = 0.0
    debits = 0.0
    fees = 0.0

    for row in rows:
        buy = float(row["Buy"]) if row.get("Buy") is not None else 0.0
        sell = float(row["Sell"]) if row.get("Sell") is not None else 0.0
        fee = float(row["Fee"]) if row.get("Fee") is not None else 0.0
        buy_curr = row.get("Buy Cur.") or ""
        sell_curr = row.get("Sell Cur.") or ""

        if buy_curr == coin:
            credits += buy
        if sell_curr == coin:
            debits += sell
        if (row.get("Fee Cur.") or "") == coin:
            fees += fee

    return LedgerSummaryResource(
        coin=coin,
        credits=credits,
        debits=debits,
        fees=fees,
        balance=credits - debits - fees,
        count=len(rows),
    )


def build_ledger_response(
    accounts: BitcoinAccounts,
    coin: str = "BTC",
    wallet: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    include_deleted: bool = False,
    page: int = 1,
    per_page: int = 50,
) -> LedgerResponse:
    """Build a paginated ledger response with summary stats."""
    _headers, rows = accounts.get_transactions(
        coin=coin,
        wallet=wallet,
        start_date=start_date,
        end_date=end_date,
        include_deleted=include_deleted,
    )

    summary = _compute_summary(rows, coin=coin)

    # Reverse to newest-first, then paginate
    rows_desc = list(reversed(rows))
    total = len(rows_desc)
    start = (page - 1) * per_page
    page_rows = rows_desc[start : start + per_page]

    transactions = [_build_transaction_resource(row) for row in page_rows]

    return LedgerResponse(
        transactions=transactions,
        summary=summary,
        page=page,
        per_page=per_page,
        total=total,
    )


def _raw_row_to_resource(row: dict[str, Any]) -> TransactionResource:
    """Convert a raw DB row (SELECT *) to a TransactionResource."""
    return TransactionResource(
        transaction_id=int(row["id"]),
        created_at=str(row["createddate"]),
        transaction_type=row.get("trans_type"),
        buy_amount=float(row["buy"]) if row.get("buy") is not None else None,
        buy_currency=row.get("buy_curr"),
        sell_amount=float(row["sell"]) if row.get("sell") is not None else None,
        sell_currency=row.get("sell_curr"),
        fee_amount=float(row["fee"]) if row.get("fee") is not None else None,
        fee_currency=row.get("fee_curr"),
        wallet_id=row.get("exchange"),
        group=row.get("group"),
        comment=row.get("comment"),
        deleted=bool(row.get("deleted") or False),
    )


def get_transaction_detail(
    accounts: BitcoinAccounts, tx_id: int
) -> TransactionResource | None:
    """Fetch a single transaction by ID, or None if not found."""
    try:
        row = accounts.ledger_writer._get_transaction(tx_id)
    except ValueError:
        return None
    return _raw_row_to_resource(row)


def update_transaction(
    accounts: BitcoinAccounts, tx_id: int, updates: TransactionUpdateRequest
) -> TransactionResource | None:
    """Apply partial update to a transaction. Returns updated resource or None."""
    field_map = {
        "created_at": "createddate",
        "transaction_type": "trans_type",
        "buy_amount": "buy",
        "buy_currency": "buy_curr",
        "sell_amount": "sell",
        "sell_currency": "sell_curr",
        "fee_amount": "fee",
        "fee_currency": "fee_curr",
        "wallet_id": "exchange",
        "group": "group",
        "comment": "comment",
    }
    kwargs: dict[str, Any] = {}
    for api_field, db_field in field_map.items():
        value = getattr(updates, api_field)
        if value is not None:
            kwargs[db_field] = value

    if not kwargs:
        return get_transaction_detail(accounts, tx_id)

    try:
        row = accounts.ledger_writer.update_transaction(tx_id, **kwargs)
    except ValueError:
        return None
    return _raw_row_to_resource(row)


def delete_transaction(
    accounts: BitcoinAccounts, tx_id: int
) -> TransactionResource | None:
    """Soft-delete a transaction. Returns updated resource or None."""
    try:
        row = accounts.ledger_writer.soft_delete_transaction(tx_id)
    except ValueError:
        return None
    return _raw_row_to_resource(row)


def restore_transaction(
    accounts: BitcoinAccounts, tx_id: int
) -> TransactionResource | None:
    """Restore a soft-deleted transaction. Returns updated resource or None."""
    try:
        row = accounts.ledger_writer.restore_transaction(tx_id)
    except ValueError:
        return None
    return _raw_row_to_resource(row)

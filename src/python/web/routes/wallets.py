"""Authenticated wallet management routes.

Wallet IDs may contain slashes (e.g. "BNB/RUNE LP"), so GET and PATCH use
{wallet_id:path}.  Rename and merge are collection-level POSTs with the
wallet ID in the request body to avoid path-greedy ambiguity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from bitcoinAccounts import BitcoinAccounts
from web.auth import SessionPrincipal, require_authenticated_principal
from web.dependencies import get_request_accounts
from web.models import (
    WalletCreateRequest,
    WalletListResource,
    WalletListResponse,
    WalletMergeRequest,
    WalletRenameRequest,
    WalletResource,
    WalletUpdateRequest,
)
from web.services.audit import log_write_action
from web.services.wallet import (
    create_wallet,
    get_wallet,
    list_wallets,
    merge_wallets,
    rename_wallet,
    sync_wallets,
    update_wallet,
)

router = APIRouter(
    prefix="/api/wallets",
    tags=["wallets"],
    dependencies=[Depends(require_authenticated_principal)],
)


# --- Collection-level endpoints (no path params) ---

@router.get("", response_model=WalletListResponse)
def wallets_list(
    active_only: bool = Query(False),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletListResponse:
    """List all wallets with transaction counts."""
    return WalletListResponse(wallets=list_wallets(accounts, active_only=active_only))


@router.post("", response_model=WalletResource, status_code=201)
def wallets_create(
    body: WalletCreateRequest,
    principal: SessionPrincipal = Depends(require_authenticated_principal),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletResource:
    """Create a new wallet."""
    try:
        result = create_wallet(
            accounts,
            wallet_id=body.wallet_id,
            wallet_type=body.wallet_type,
            custody=body.custody,
            description=body.description,
            notes=body.notes,
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"Wallet '{body.wallet_id}' already exists")
        raise HTTPException(status_code=422, detail=str(exc))
    log_write_action(
        accounts.backend,
        action="wallet.create",
        entity_type="wallet",
        entity_id=body.wallet_id,
        operator=principal.username,
        detail=body.model_dump(),
    )
    return result


@router.post("/sync", response_model=dict)
def wallets_sync(
    principal: SessionPrincipal = Depends(require_authenticated_principal),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Sync wallets from ledger, creating missing wallet records."""
    result = sync_wallets(accounts)
    log_write_action(
        accounts.backend,
        action="wallet.sync",
        entity_type="wallet",
        operator=principal.username,
        detail={"created": result["created"]},
    )
    return result


@router.post("/rename", response_model=WalletResource)
def wallets_rename(
    body: WalletRenameRequest,
    principal: SessionPrincipal = Depends(require_authenticated_principal),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletResource:
    """Rename a wallet and update all ledger references."""
    try:
        result = rename_wallet(accounts, body.wallet_id, body.new_wallet_id)
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    if result is None:
        raise HTTPException(status_code=404, detail="Wallet not found after rename")
    log_write_action(
        accounts.backend,
        action="wallet.rename",
        entity_type="wallet",
        entity_id=body.new_wallet_id,
        operator=principal.username,
        detail={"old_wallet_id": body.wallet_id, "new_wallet_id": body.new_wallet_id},
    )
    return result


@router.post("/merge", response_model=dict)
def wallets_merge(
    body: WalletMergeRequest,
    principal: SessionPrincipal = Depends(require_authenticated_principal),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> dict:
    """Merge source wallet into target wallet."""
    if body.source_wallet_id == body.target_wallet_id:
        raise HTTPException(status_code=422, detail="Source and target wallets must be different")
    try:
        result = merge_wallets(accounts, body.source_wallet_id, body.target_wallet_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    log_write_action(
        accounts.backend,
        action="wallet.merge",
        entity_type="wallet",
        entity_id=body.target_wallet_id,
        operator=principal.username,
        detail={"source_wallet_id": body.source_wallet_id, "target_wallet_id": body.target_wallet_id},
    )
    return result


# --- Resource-level endpoints ({wallet_id:path} for slash-containing IDs) ---

@router.get("/{wallet_id:path}", response_model=WalletListResource)
def wallets_detail(
    wallet_id: str,
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletListResource:
    """Get a single wallet with transaction count."""
    result = get_wallet(accounts, wallet_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return result


@router.patch("/{wallet_id:path}", response_model=WalletResource)
def wallets_update(
    wallet_id: str,
    body: WalletUpdateRequest,
    principal: SessionPrincipal = Depends(require_authenticated_principal),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletResource:
    """Update wallet metadata."""
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = update_wallet(accounts, wallet_id, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    log_write_action(
        accounts.backend,
        action="wallet.update",
        entity_type="wallet",
        entity_id=wallet_id,
        operator=principal.username,
        detail=kwargs,
    )
    return result

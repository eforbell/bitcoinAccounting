"""Authenticated wallet verification routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from bitcoinAccounts import BitcoinAccounts
from web.auth import require_authenticated_principal
from web.config import WebConfig
from web.dependencies import get_request_accounts
from web.models_verification import (
    WalletVerificationCreateRequest,
    WalletVerificationListResponse,
    WalletVerificationRunResponse,
)
from web.services.descriptor_engine import DescriptorEngineError
from web.services.electrum_client import ElectrumClientError
from web.services.wallet_verification import (
    get_wallet_verification_list,
    run_manual_wallet_verification,
)

router = APIRouter(
    prefix="/api/verification",
    tags=["verification"],
    dependencies=[Depends(require_authenticated_principal)],
)


def get_web_config(request: Request) -> WebConfig:
    """Return the request-scoped web config."""
    return request.app.state.web_config


@router.get("/wallets/{wallet_id:path}", response_model=WalletVerificationListResponse)
def wallet_verification_history(
    wallet_id: str,
    limit: int = Query(20, ge=1, le=100),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletVerificationListResponse:
    """Return verification history for one wallet."""
    return get_wallet_verification_list(accounts.backend, wallet_id, limit=limit)


@router.post("/run", response_model=WalletVerificationRunResponse)
def run_verification(
    body: WalletVerificationCreateRequest,
    config: WebConfig = Depends(get_web_config),
    accounts: BitcoinAccounts = Depends(get_request_accounts),
) -> WalletVerificationRunResponse:
    """Run a manual balance-only verification session."""
    try:
        return run_manual_wallet_verification(accounts, config, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DescriptorEngineError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Bitcoin Core descriptor RPC unavailable: {exc}",
        ) from exc
    except ElectrumClientError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Electrum verification backend unavailable: {exc}",
        ) from exc

"""Authenticated Bitcoin chain-status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from web.auth import require_authenticated_principal
from web.models import ChainStatusResponse
from web.services.chain_status import ChainStatusService

router = APIRouter(
    prefix="/api/chain",
    tags=["chain"],
    dependencies=[Depends(require_authenticated_principal)],
)


def get_chain_status_service(request: Request) -> ChainStatusService:
    """Build the request-scoped chain status service."""
    return ChainStatusService(request.app.state.web_config)


@router.get("/status", response_model=ChainStatusResponse)
def chain_status(
    service: ChainStatusService = Depends(get_chain_status_service),
) -> ChainStatusResponse:
    """Return optional Bitcoin chain status for dashboard presence."""
    return service.get_status()

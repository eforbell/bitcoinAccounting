"""Health and readiness routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, status

from db import DatabaseBackend
from web.dependencies import get_request_backend
from web.models import HealthResponse, ReadinessResponse
from web.startup import probe_database

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    """Return liveness information without touching external dependencies."""
    config = request.app.state.web_config
    return HealthResponse(
        status="ok",
        service="bitcoin-accounting-api",
        environment=config.app_env,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/api/ready", response_model=ReadinessResponse)
def get_ready(
    response: Response,
    request: Request,
    backend: DatabaseBackend = Depends(get_request_backend),
) -> ReadinessResponse:
    """Return readiness information including a database probe."""
    config = request.app.state.web_config
    database_reachable = True
    readiness_status = "ready"
    try:
        probe_database(backend)
    except Exception:
        database_reachable = False
        readiness_status = "not_ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status=readiness_status,
        service="bitcoin-accounting-api",
        environment=config.app_env,
        database_backend=config.db_backend,
        database_reachable=database_reachable,
        production_policy="postgres-primary",
        timestamp=datetime.now(timezone.utc),
    )

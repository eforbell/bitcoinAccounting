"""Reports/visualization routes.

Serves the chart data as JSON for the charts the browser draws, and the
combined portfolio PDF (drawn by the ``viz`` matplotlib charts), both built on
demand from the request-scoped database backend.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from db import DatabaseBackend
from web.auth import require_authenticated_principal
from web.dependencies import get_request_backend
from web.models import ReportSeriesResponse
from web.services.reports import (
    VALID_RANGES,
    ReportError,
    build_report_series,
    render_report_pdf,
)

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(require_authenticated_principal)],
)

# Short private cache header so a browser reuses the PDF bytes briefly without
# pinning stale data across sessions.
_CACHE_CONTROL = "private, max-age=120"


@router.get("/series", response_model=ReportSeriesResponse)
def report_series(
    range: str = Query("all"),
    refresh: bool = Query(False),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> ReportSeriesResponse:
    """Return holdings, trades, cost basis and BTC-USD prices for the charts.

    ``refresh`` bypasses the cached price history.
    """
    if range not in VALID_RANGES:
        raise HTTPException(status_code=400, detail=f"Unknown range '{range}'")
    return build_report_series(backend, date_range=range, refresh=refresh)


@router.get("/report.pdf")
def report_pdf(
    range: str = Query("all"),
    refresh: bool = Query(False),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> Response:
    """Return the combined multi-page portfolio PDF as a download."""
    if range not in VALID_RANGES:
        raise HTTPException(status_code=400, detail=f"Unknown range '{range}'")

    try:
        pdf = render_report_pdf(backend, date_range=range, refresh=refresh)
    except ReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = f"btc_report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": _CACHE_CONTROL,
        },
    )

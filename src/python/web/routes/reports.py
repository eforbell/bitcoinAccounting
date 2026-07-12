"""Reports/visualization routes.

Serves the resurrected ``viz`` charts (orange plot, balance, custody) as PNGs
and the combined portfolio PDF, generated on demand from the request-scoped
database backend.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from db import DatabaseBackend
from web.auth import require_authenticated_principal
from web.dependencies import get_request_backend
from web.services.reports import (
    VALID_CHARTS,
    VALID_RANGES,
    ReportError,
    render_chart_png,
    render_report_pdf,
)

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(require_authenticated_principal)],
)

# Short private cache header so a browser reuses report bytes within a page
# load without pinning stale data across sessions. Applied to both the PNG and
# PDF responses for consistent caching semantics.
_CACHE_CONTROL = "private, max-age=120"


@router.get("/chart/{chart_type}.png")
def chart_png(
    chart_type: str,
    range: str = Query("all"),
    refresh: bool = Query(False),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> Response:
    """Return a single chart as a PNG image."""
    if chart_type not in VALID_CHARTS:
        raise HTTPException(status_code=404, detail=f"Unknown chart '{chart_type}'")
    if range not in VALID_RANGES:
        raise HTTPException(status_code=400, detail=f"Unknown range '{range}'")

    try:
        png = render_chart_png(backend, chart_type, date_range=range, refresh=refresh)
    except ReportError as exc:
        # No data yet (e.g. empty ledger) — surface as 404 so the UI can show
        # an empty state rather than a broken image.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": _CACHE_CONTROL},
    )


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

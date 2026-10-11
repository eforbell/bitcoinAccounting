"""Report/visualization service for the web app.

Serves the ``viz.series`` data as JSON for the charts the browser draws, and
wraps ``viz.PDFReport`` so the combined PDF can be generated on demand and
streamed as bytes from a FastAPI route. Both read the same series, so the
browser charts and the PDF agree.

Design notes:
- Forces the non-interactive ``Agg`` matplotlib backend *before* the viz
  modules (which import ``matplotlib.pyplot`` at import time) are imported.
  Without this a headless server can hang or crash trying to open a GUI
  backend.
- matplotlib's pyplot state machine is not thread-safe. Uvicorn runs sync
  route handlers in a threadpool, so all figure generation is serialized
  behind a module-level lock. This is fine for a single-operator app.
- Generated PDF bytes are cached in-process with a short TTL so repeat
  downloads don't redraw three matplotlib figures (plus a yfinance call).
  Pass ``refresh=True`` to bypass.
- The JSON series reads the ledger on every request (cheap) but caches the
  BTC-USD price history separately: ``PriceDataFetcher`` goes back to Yahoo
  whenever its disk cache does not reach "now", which is almost always.
  Prices do not depend on the ledger, so ledger writes do not clear it.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

# Force a headless backend before anything imports pyplot.
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib

matplotlib.use("Agg", force=True)

from viz import PDFReport, PriceDataFetcher, VizConfig
from viz.series import (
    BTC_EPSILON,
    DateWindow,
    HoldingsPoint,
    PricePoint,
    accumulation_series,
    holdings_series,
    nearest_price,
    price_series,
    resolve_window,
)
from web.models import (
    AccumulationSeriesResource,
    AccumulationSummaryResource,
    BasisPointResource,
    HoldingsPointResource,
    HoldingsSeriesResource,
    PricePointResource,
    PriceSeriesResource,
    ReportSeriesResponse,
    ReportTradeResource,
    ReportWarningResource,
    ReportWindowResource,
    ValuationResource,
)

if TYPE_CHECKING:
    from db import DatabaseBackend

VALID_RANGES = ("all", "5y", "1y", "ytd")

# Chart resolution inside the PDF. 150 DPI on a 10x6 figure -> ~1500x900,
# crisp when zoomed while keeping the file small.
_WEB_DPI = 150

# matplotlib pyplot is a global state machine; serialize all generation.
_render_lock = threading.Lock()

# Simple in-process byte cache: key -> (expires_at, content_bytes).
_CACHE_TTL_SECONDS = int(os.getenv("REPORTS_CACHE_TTL_SECONDS", "300"))
_cache: dict[str, tuple[float, bytes]] = {}
_cache_lock = threading.Lock()

# BTC-USD closes for the JSON series: key -> (expires_at, points). The lock is
# held across the fetch so concurrent requests share one Yahoo call.
_PRICE_CACHE_TTL_SECONDS = int(os.getenv("REPORTS_PRICE_CACHE_TTL_SECONDS", "900"))
_price_cache: dict[str, tuple[float, list[PricePoint]]] = {}
_price_lock = threading.Lock()

# A failed fetch is remembered briefly (key -> retry_after) so requests queued
# behind the lock during an outage fail fast instead of each waiting out
# another upstream timeout. ``refresh=True`` retries immediately.
_PRICE_FAILURE_BACKOFF_SECONDS = int(os.getenv("REPORTS_PRICE_FAILURE_BACKOFF_SECONDS", "60"))
_price_failures: dict[str, float] = {}

_PRICE_FEED_ERRORS = (ImportError, OSError, RuntimeError, ValueError)


class ReportError(RuntimeError):
    """Raised when the report cannot be generated (e.g. no data)."""


def _cache_get(key: str) -> bytes | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, content = entry
        if time.monotonic() >= expires_at:
            _cache.pop(key, None)
            return None
        return content


def _cache_put(key: str, content: bytes) -> None:
    if _CACHE_TTL_SECONDS <= 0:
        return
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, content)


def clear_cache() -> None:
    """Drop all cached report bytes (e.g. after a ledger mutation)."""
    with _cache_lock:
        _cache.clear()


def clear_price_cache() -> None:
    """Drop cached BTC-USD price history."""
    with _price_lock:
        _price_cache.clear()
        _price_failures.clear()


def _config(output_dir: Path, date_range: str) -> VizConfig:
    return VizConfig(
        date_range=date_range,
        output_dir=output_dir,
        include_cost_basis=True,
        log_scale=False,
        dpi=_WEB_DPI,
    )


def render_report_pdf(
    backend: DatabaseBackend,
    *,
    date_range: str = "all",
    refresh: bool = False,
) -> bytes:
    """Render the combined multi-page PDF report to bytes.

    Raises:
        ValueError: Invalid ``date_range``.
        ReportError: No transaction data / generation failed.
    """
    if date_range not in VALID_RANGES:
        raise ValueError(f"Unknown date range: {date_range!r}")

    cache_key = f"pdf:{date_range}"
    if not refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    with _render_lock:
        with tempfile.TemporaryDirectory(prefix="btc-report-") as tmp:
            config = _config(Path(tmp), date_range)
            try:
                output_path = PDFReport(backend, config).generate()
            except (ValueError, RuntimeError) as exc:
                raise ReportError(str(exc)) from exc
            content = Path(output_path).read_bytes()

    _cache_put(cache_key, content)
    return content


# ── JSON series for browser-drawn charts ──


def _price_fetcher() -> PriceDataFetcher:
    """Build the BTC-USD fetcher (patched in tests to stay offline)."""
    return PriceDataFetcher()


def _load_prices(date_range: str, window: DateWindow, refresh: bool) -> list[PricePoint]:
    # The window start moves with the ledger for "all", so it is part of the key.
    key = f"{date_range}:{window.start.date().isoformat()}"
    with _price_lock:
        entry = _price_cache.get(key)
        if entry is not None and not refresh and time.monotonic() < entry[0]:
            return entry[1]
        if not refresh and time.monotonic() < _price_failures.get(key, 0.0):
            raise RuntimeError("BTC-USD price feed failed recently; waiting before retrying")
        try:
            points = price_series(_price_fetcher(), window)
        except _PRICE_FEED_ERRORS:
            if _PRICE_FAILURE_BACKOFF_SECONDS > 0:
                _price_failures[key] = time.monotonic() + _PRICE_FAILURE_BACKOFF_SECONDS
            raise
        _price_failures.pop(key, None)
        if _PRICE_CACHE_TTL_SECONDS > 0:
            _price_cache[key] = (time.monotonic() + _PRICE_CACHE_TTL_SECONDS, points)
        return points


def _holdings_point(point: HoldingsPoint) -> HoldingsPointResource:
    return HoldingsPointResource(
        date=point.when,
        total_btc=point.total,
        self_custodied_btc=point.by_custody["self-custodied"],
        multisig_btc=point.by_custody["multisig"],
        custodial_btc=point.by_custody["custodial"],
        unknown_btc=point.by_custody["unknown"],
    )


def build_report_series(
    backend: DatabaseBackend,
    *,
    date_range: str = "all",
    refresh: bool = False,
) -> ReportSeriesResponse:
    """Build the reports page data for one date range preset.

    Ledger data always loads. When the price feed fails, ``price`` and
    ``valuation`` are null and a ``price_unavailable`` warning explains why.
    Warning text carries no amounts: it renders as plain text, outside the
    privacy mask and the sats/BTC toggle.

    Raises:
        ValueError: Invalid ``date_range``.
    """
    if date_range not in VALID_RANGES:
        raise ValueError(f"Unknown date range: {date_range!r}")

    window = resolve_window(backend, date_range)
    holdings = holdings_series(backend, window)
    accumulation = accumulation_series(backend, window)
    warnings: list[ReportWarningResource] = []

    prices: list[PricePoint] = []
    if holdings.has_transactions:
        try:
            prices = _load_prices(date_range, window, refresh)
        except _PRICE_FEED_ERRORS:
            warnings.append(ReportWarningResource(
                code="price_unavailable",
                severity="warning",
                message=(
                    "BTC-USD price history is unavailable right now, so the price "
                    "line and current value are hidden."
                ),
            ))

    summary = accumulation.summary
    if summary.purchases_missing_cost:
        warnings.append(ReportWarningResource(
            code="purchases_missing_cost",
            severity="info",
            message=(
                "Some purchases have no USD price in the ledger, so they are left "
                "out of the cost basis and total invested."
            ),
        ))
    if any(point.total < -BTC_EPSILON for point in holdings.points):
        warnings.append(ReportWarningResource(
            code="negative_balance",
            severity="warning",
            message=(
                "Holdings go negative in this range, which usually means a deposit "
                "or purchase is missing from the ledger."
            ),
        ))

    trades = sorted(
        accumulation.purchases + accumulation.sales,
        key=lambda t: (t.when, t.ledger_id or 0),
    )
    trade_resources = [
        ReportTradeResource(
            date=t.when,
            side=t.side,
            btc=t.btc,
            unit_price_usd=t.unit_price_usd,
            total_usd=t.total_usd,
            marker_price_usd=(
                t.unit_price_usd
                if t.unit_price_usd is not None
                else (nearest_price(prices, t.when) if prices else None)
            ),
            wallet_id=t.wallet,
            ledger_id=t.ledger_id,
        )
        for t in trades
    ]

    price_resource = None
    valuation_resource = None
    if prices:
        latest = prices[-1]
        price_resource = PriceSeriesResource(
            points=[PricePointResource(date=p.when, close_usd=p.close_usd) for p in prices],
            latest=PricePointResource(date=latest.when, close_usd=latest.close_usd),
        )
        if holdings.has_transactions:
            valuation = summary.valuation(latest.close_usd, holdings.latest.total)
            valuation_resource = ValuationResource(
                as_of=latest.when,
                price_usd=valuation.price_usd,
                current_value_usd=valuation.current_value_usd,
                position_cost_usd=valuation.position_cost_usd,
                unrealized_gain_usd=valuation.unrealized_gain_usd,
                unrealized_gain_pct=valuation.unrealized_gain_pct,
            )

    return ReportSeriesResponse(
        window=ReportWindowResource(range=date_range, start=window.start, end=window.end),
        has_transactions=holdings.has_transactions,
        holdings=HoldingsSeriesResource(
            points=[_holdings_point(p) for p in holdings.points],
            latest=_holdings_point(holdings.latest),
            self_custody_pct=holdings.self_custody_pct(),
        ),
        accumulation=AccumulationSeriesResource(
            trades=trade_resources,
            basis=[
                BasisPointResource(date=b.when, average_cost_usd=b.average_cost_usd)
                for b in accumulation.basis
            ],
            summary=AccumulationSummaryResource(
                purchase_count=summary.purchase_count,
                sale_count=summary.sale_count,
                btc_purchased=summary.btc_purchased,
                btc_sold=summary.btc_sold,
                net_btc=summary.net_btc,
                invested_usd=summary.invested_usd,
                invested_in_window_usd=summary.invested_in_window_usd,
                average_cost_usd=summary.average_cost_usd,
                purchases_missing_cost=summary.purchases_missing_cost,
            ),
        ),
        price=price_resource,
        valuation=valuation_resource,
        warnings=warnings,
    )

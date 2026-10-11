"""Tests for the Reports/visualization API routes and service.

Covers the JSON series behind the browser charts, the network-free PNG charts
(balance, custody), auth protection, error handling for an empty ledger, and
report-cache invalidation on ledger writes. The orange plot PNG and PDF are
intentionally not exercised here because they fetch BTC-USD prices over the
network; the JSON series stubs the price fetcher instead.
"""

from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig
from web.dependencies import get_request_accounts, get_request_backend
from web.services import reports as reports_service

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
def _isolate_cache() -> None:
    reports_service.clear_cache()
    reports_service.clear_price_cache()
    yield
    reports_service.clear_cache()
    reports_service.clear_price_cache()


class _StubFetcher:
    """Offline BTC-USD feed: one close per day, rising $10/day from $20,000."""

    calls = 0
    fail = False

    def fetch_btc_price_history(self, start: datetime, end: datetime) -> pd.DataFrame:
        _StubFetcher.calls += 1
        if _StubFetcher.fail:
            raise RuntimeError("Yahoo is down")
        days = pd.date_range("2022-01-01", "2027-01-01", freq="D")
        frame = pd.DataFrame({"close": [20000.0 + 10 * i for i in range(len(days))]}, index=days)
        return frame[(frame.index >= start) & (frame.index <= end)]


@pytest.fixture(autouse=True)
def stub_prices(monkeypatch: pytest.MonkeyPatch) -> type[_StubFetcher]:
    _StubFetcher.calls = 0
    _StubFetcher.fail = False
    monkeypatch.setattr(reports_service, "_price_fetcher", _StubFetcher)
    return _StubFetcher


@pytest.fixture
def seeded_accounts() -> BitcoinAccounts:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    acc = BitcoinAccounts(backend=backend)
    acc.wallet_query.add_wallet(
        wallet_id="Coldcard", wallet_type="hardware",
        custody="self-custodied", description="vault",
    )
    acc.execute_trade(trade_date=datetime(2023, 1, 10), buy=0.2,
                      sell=6000, exchange="Coldcard")
    acc.execute_trade(trade_date=datetime(2024, 3, 5), buy=0.1,
                      sell=6500, exchange="Coldcard")
    yield acc
    acc.close()


@pytest.fixture
def client(seeded_accounts: BitcoinAccounts) -> TestClient:
    app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
        )
    )
    app.dependency_overrides[get_request_accounts] = lambda: seeded_accounts
    app.dependency_overrides[get_request_backend] = lambda: seeded_accounts.backend
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"passphrase": "orange-hodl"}).status_code == 200
    return client


@pytest.mark.parametrize("chart", ["balance", "custody"])
def test_chart_png_renders(client: TestClient, chart: str) -> None:
    resp = client.get(f"/api/reports/chart/{chart}.png?range=all")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers.get("cache-control") == "private, max-age=120"
    assert resp.content[:8] == _PNG_MAGIC


def test_unknown_chart_is_404(client: TestClient) -> None:
    assert client.get("/api/reports/chart/bogus.png?range=all").status_code == 404


def test_bad_range_is_400(client: TestClient) -> None:
    assert client.get("/api/reports/chart/balance.png?range=decade").status_code == 400


def test_reports_require_authentication(seeded_accounts: BitcoinAccounts) -> None:
    app = create_app(
        WebConfig(auth_enabled=True, auth_passphrase="pw", session_secret="s")
    )
    app.dependency_overrides[get_request_backend] = lambda: seeded_accounts.backend
    anon = TestClient(app)
    assert anon.get("/api/reports/chart/balance.png?range=all").status_code in (401, 403)
    assert anon.get("/api/reports/series?range=all").status_code in (401, 403)


# ── JSON series ──


def _close_on(day: datetime) -> float:
    return 20000.0 + 10 * (day - datetime(2022, 1, 1)).days


def test_series_payload(client: TestClient) -> None:
    resp = client.get("/api/reports/series?range=all")
    assert resp.status_code == 200
    body = resp.json()

    assert body["window"]["range"] == "all"
    assert body["window"]["start"].startswith("2023-01-10")
    assert body["has_transactions"] is True
    assert body["warnings"] == []

    holdings = body["holdings"]
    assert holdings["points"][0]["total_btc"] == pytest.approx(0.0)
    assert holdings["latest"]["total_btc"] == pytest.approx(0.3)
    assert holdings["latest"]["self_custodied_btc"] == pytest.approx(0.3)
    assert holdings["self_custody_pct"] == pytest.approx(100.0)

    trades = body["accumulation"]["trades"]
    assert [t["side"] for t in trades] == ["buy", "buy"]
    assert trades[0]["unit_price_usd"] == pytest.approx(30000.0)
    assert trades[0]["marker_price_usd"] == pytest.approx(30000.0)
    assert trades[0]["wallet_id"] == "Coldcard"
    assert isinstance(trades[0]["ledger_id"], int)

    summary = body["accumulation"]["summary"]
    assert summary["invested_usd"] == pytest.approx(12500.0)
    assert summary["average_cost_usd"] == pytest.approx(12500.0 / 0.3)
    basis = [b["average_cost_usd"] for b in body["accumulation"]["basis"]]
    assert basis == pytest.approx([30000.0, 12500.0 / 0.3, 12500.0 / 0.3])

    price = body["price"]
    latest_day = datetime.fromisoformat(price["latest"]["date"])
    assert price["latest"]["close_usd"] == pytest.approx(_close_on(latest_day))
    assert price["points"][0]["date"] >= body["window"]["start"][:10]

    valuation = body["valuation"]
    assert valuation["current_value_usd"] == pytest.approx(0.3 * _close_on(latest_day))
    assert valuation["position_cost_usd"] == pytest.approx(12500.0)


def test_series_values_position_net_of_sales(
    client: TestClient, seeded_accounts: BitcoinAccounts
) -> None:
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 6, 1), buy=5000, buy_curr="USD",
        sell=0.1, sell_curr="BTC", exchange="Coldcard",
    )
    body = client.get("/api/reports/series?range=all").json()
    latest_close = body["price"]["latest"]["close_usd"]

    assert [t["side"] for t in body["accumulation"]["trades"]] == ["buy", "buy", "sell"]
    assert body["accumulation"]["summary"]["net_btc"] == pytest.approx(0.2)
    assert body["valuation"]["current_value_usd"] == pytest.approx(0.2 * latest_close)
    assert body["holdings"]["latest"]["total_btc"] == pytest.approx(0.2)


def test_series_bad_range_is_400(client: TestClient) -> None:
    assert client.get("/api/reports/series?range=decade").status_code == 400


def test_series_survives_price_feed_outage(client: TestClient, stub_prices) -> None:
    stub_prices.fail = True
    resp = client.get("/api/reports/series?range=all")
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] is None
    assert body["valuation"] is None
    assert [w["code"] for w in body["warnings"]] == ["price_unavailable"]
    assert body["holdings"]["latest"]["total_btc"] == pytest.approx(0.3)
    assert len(body["accumulation"]["trades"]) == 2


def test_series_caches_prices_until_refresh(client: TestClient, stub_prices) -> None:
    client.get("/api/reports/series?range=1y")
    client.get("/api/reports/series?range=1y")
    assert stub_prices.calls == 1
    client.get("/api/reports/series?range=1y&refresh=true")
    assert stub_prices.calls == 2


def test_series_trade_without_usd_price(
    client: TestClient, seeded_accounts: BitcoinAccounts
) -> None:
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 9, 2), buy=0.05, sell=2500,
        sell_curr="EUR", exchange="Coldcard",
    )
    body = client.get("/api/reports/series?range=all").json()
    eur_trade = body["accumulation"]["trades"][-1]
    assert eur_trade["unit_price_usd"] is None
    # Plotted on the market price line instead.
    assert eur_trade["marker_price_usd"] == pytest.approx(_close_on(datetime(2024, 9, 2)))
    assert [w["code"] for w in body["warnings"]] == ["purchases_missing_cost"]


def test_series_warning_text_has_no_amounts(
    client: TestClient, seeded_accounts: BitcoinAccounts, stub_prices
) -> None:
    # Warnings render as plain text, outside privacy mode and the denomination toggle.
    stub_prices.fail = True
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 9, 2), buy=0.05, sell=2500,
        sell_curr="EUR", exchange="Coldcard",
    )
    seeded_accounts.execute_trade(
        trade_date=datetime(2024, 10, 2), buy=50000, buy_curr="USD",
        sell=1.0, sell_curr="BTC", exchange="Coldcard",
    )
    warnings = client.get("/api/reports/series?range=all").json()["warnings"]
    assert {w["code"] for w in warnings} == {
        "price_unavailable", "purchases_missing_cost", "negative_balance",
    }
    assert not any(ch.isdigit() for w in warnings for ch in w["message"])


def test_series_empty_ledger_skips_price_feed(stub_prices) -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    try:
        series = reports_service.build_report_series(backend, date_range="all")
    finally:
        backend.close()
    assert series.has_transactions is False
    assert series.holdings.latest.total_btc == 0.0
    assert series.accumulation.trades == []
    assert series.price is None
    assert stub_prices.calls == 0


def test_service_renders_png_bytes(seeded_accounts: BitcoinAccounts) -> None:
    png = reports_service.render_chart_png(
        seeded_accounts.backend, "balance", date_range="all"
    )
    assert png[:8] == _PNG_MAGIC


def test_service_empty_ledger_raises_report_error() -> None:
    backend = SqliteBackend(":memory:", auto_create_tables=True)
    try:
        with pytest.raises(reports_service.ReportError):
            reports_service.render_chart_png(backend, "balance", date_range="all")
    finally:
        backend.close()


def test_ledger_write_invalidates_report_cache(client: TestClient) -> None:
    # Seed a fake cached entry, then confirm a successful write clears it.
    reports_service._cache["png:balance:all"] = (time.monotonic() + 999, b"stale")
    resp = client.post(
        "/api/ledger/buy",
        json={
            "trade_date": "2024-06-15T10:30:00",
            "buy": 0.05,
            "sell": 3000.0,
            "exchange": "Coldcard",
            "comment": "cache-bust",
        },
    )
    assert resp.status_code == 200
    assert "png:balance:all" not in reports_service._cache

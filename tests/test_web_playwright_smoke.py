"""Browser smoke test for the web tax dashboard."""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from bitcoinAccounts import BitcoinAccounts
from db import SqliteBackend
from web.app import create_app
from web.config import WebConfig


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _seed_smoke_database(db_path: str) -> None:
    backend = SqliteBackend(db_path, auto_create_tables=True)
    accounts = BitcoinAccounts(backend=backend)
    try:
        accounts.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=1.0,
            buy_curr="BTC",
            sell=50000.0,
            sell_curr="USD",
            exchange="Strike",
        )
        accounts.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr="USD",
            sell=1.0,
            sell_curr="BTC",
            exchange="Strike",
        )
        accounts.execute_trade(
            trade_date=datetime(2025, 12, 1),
            buy=0.25,
            buy_curr="BTC",
            sell=20000.0,
            sell_curr="USD",
            exchange="Vault",
        )
    finally:
        accounts.close()


@contextlib.contextmanager
def _run_smoke_server(db_path: str) -> Iterator[str]:
    previous_db_backend = os.environ.get("DB_BACKEND")
    previous_sqlite_path = os.environ.get("SQLITE_DB_PATH")
    os.environ["DB_BACKEND"] = "sqlite"
    os.environ["SQLITE_DB_PATH"] = db_path

    port = _find_free_port()
    root_app = FastAPI()
    root_app.mount(
        "/bitcoin-accounting",
        create_app(
            WebConfig(
                auth_enabled=True,
                auth_passphrase="orange-hodl",
                session_secret="test-secret",
                db_backend="sqlite",
                web_base_path="/bitcoin-accounting",
            )
        ),
    )

    config = uvicorn.Config(root_app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Timed out waiting for uvicorn smoke server to start.")

    try:
        yield f"http://127.0.0.1:{port}/bitcoin-accounting/"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if previous_db_backend is None:
            os.environ.pop("DB_BACKEND", None)
        else:
            os.environ["DB_BACKEND"] = previous_db_backend
        if previous_sqlite_path is None:
            os.environ.pop("SQLITE_DB_PATH", None)
        else:
            os.environ["SQLITE_DB_PATH"] = previous_sqlite_path


def test_tax_dashboard_smoke_flow(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    db_path = str(tmp_path / "smoke.sqlite3")
    _seed_smoke_database(db_path)

    with _run_smoke_server(db_path) as base_url:
        manager = None
        browser = None
        try:
            manager = playwright.sync_playwright().start()
            browser = manager.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            if manager is not None:
                manager.stop()
            pytest.skip(f"Playwright Chromium unavailable: {exc}")

        try:
            page = browser.new_page()
            page.goto(base_url, wait_until="networkidle")

            playwright.expect(page.locator(".nav-logo")).to_contain_text("Bitcoin Accounting")
            page.get_by_label("Passphrase").fill("orange-hodl")
            page.get_by_role("button", name="Sign In").click()

            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
            playwright.expect(page.locator("#dashboard-balance")).to_contain_text("BTC")
            page.locator('.app-sidebar [data-route="tax"]').click()
            playwright.expect(page.locator('#tax-view h1')).to_have_text("Tax")
            playwright.expect(page.locator("#policy-summary")).to_contain_text("Wallet-separated FIFO")

            page.get_by_role("button", name="Load Gains").click()
            playwright.expect(page.locator("#gains-lots")).to_have_text("1")
            playwright.expect(page.locator("#gains-table")).to_contain_text("12/01/2024")

            page.get_by_label("Wallet").nth(1).fill("Vault")
            page.get_by_label("Quantity").fill("0.2")
            page.get_by_role("button", name="Forecast Sale").click()
            playwright.expect(page.locator("#forecast-balance")).to_have_text("0.25000000 BTC")
            playwright.expect(page.locator("#forecast-table")).to_contain_text("2025-12-01")

            page.get_by_label("Name").fill("Vault Forecast")
            page.get_by_label("Type").select_option("forecast")
            page.get_by_role("button", name="Save Current Filters").click()
            playwright.expect(page.locator("#presets-list")).to_contain_text("Vault Forecast")
            playwright.expect(page.locator("#history-list")).to_contain_text("forecast")

            # Navigate back to dashboard and click into wallet detail
            page.locator('.app-sidebar .nav-item[data-route="dashboard"]').click()
            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

            page.locator('[data-wallet-id="Strike"]').click()
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Strike")
            playwright.expect(page.locator("#wallet-view-balance")).to_contain_text("BTC")
            playwright.expect(page.locator("#wallet-tx-list")).not_to_contain_text("Not Found")
            assert "/wallet/Strike" in page.url

            # Verify direct-load of wallet URL works (API resolves from subpath)
            page.goto(base_url + "wallet/Vault", wait_until="networkidle")
            if page.locator("#login-panel").is_visible():
                page.get_by_label("Passphrase").fill("orange-hodl")
                page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            playwright.expect(page.locator("#wallet-view-balance")).to_contain_text("BTC")
            playwright.expect(page.locator("#wallet-tx-list")).not_to_contain_text("Not Found")
        finally:
            if browser is not None:
                browser.close()
            if manager is not None:
                manager.stop()

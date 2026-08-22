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
from web.routes.chain import get_chain_status_service


MOBILE_IMPORT_CSV = (
    "trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date\n"
    "Trade,0.5,BTC,25000,USD,10,USD,Strike,,Mobile preview,2024-06-15 10:30:00\n"
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _seed_smoke_database(db_path: str) -> None:
    backend = SqliteBackend(db_path, auto_create_tables=True)
    accounts = BitcoinAccounts(backend=backend)
    try:
        accounts.wallet_query.add_wallet(
            wallet_id="Strike",
            wallet_type="exchange",
            custody="custodial",
            description="DCA exchange",
        )
        accounts.wallet_query.add_wallet(
            wallet_id="Vault",
            wallet_type="hardware",
            custody="self-custodied",
            description="Cold storage",
        )
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


class _StaticChainService:
    """Minimal fake chain-status service for Playwright smoke tests."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def get_status(self) -> dict[str, object]:
        return self._payload


@contextlib.contextmanager
def _run_smoke_server(
    db_path: str,
    *,
    chain_status_payload: dict[str, object] | None = None,
) -> Iterator[str]:
    previous_db_backend = os.environ.get("DB_BACKEND")
    previous_sqlite_path = os.environ.get("SQLITE_DB_PATH")
    os.environ["DB_BACKEND"] = "sqlite"
    os.environ["SQLITE_DB_PATH"] = db_path

    port = _find_free_port()
    root_app = FastAPI()
    web_app = create_app(
        WebConfig(
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
            db_backend="sqlite",
            web_base_path="/bitcoin-accounting",
        )
    )
    if chain_status_payload is not None:
        web_app.dependency_overrides[get_chain_status_service] = (
            lambda: _StaticChainService(chain_status_payload)
        )

    root_app.mount(
        "/bitcoin-accounting",
        web_app,
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

    with _run_smoke_server(
        db_path,
        chain_status_payload={
            "enabled": True,
            "available": True,
            "source": "bitcoind",
            "network": "main",
            "block_height": 942151,
            "header_height": 942151,
            "verification_progress": 1.0,
            "is_synced": True,
            "last_block_at": datetime(2026, 3, 25, 12, 0, 0),
            "seconds_since_last_block": 302,
            "peer_count": 11,
            "mempool_tx_count": 10815,
            "mempool_usage_bytes": 64487424,
            "pruned": False,
            "warnings": [],
            "refreshed_at": datetime(2026, 3, 25, 12, 5, 0),
        },
    ) as base_url:
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
            playwright.expect(page.locator("#dashboard-verification")).to_contain_text("🔰")
            playwright.expect(page.locator("#wallet-list")).to_contain_text("🔰")
            page.locator('.app-sidebar [data-route="tax"]').click()
            playwright.expect(page.locator('#tax-view h1')).to_have_text("Tax")
            playwright.expect(page.locator("#policy-summary")).to_contain_text("Wallet-separated FIFO")

            page.get_by_role("button", name="Load Gains").click()
            playwright.expect(page.locator("#gains-lots")).to_have_text("1")
            playwright.expect(page.locator("#gains-table")).to_contain_text("12/01/2024")

            page.locator("#forecast-wallet").fill("Vault")
            page.locator("#forecast-quantity").fill("0.2")
            page.get_by_role("button", name="Forecast Sale").click()
            playwright.expect(page.locator("#forecast-balance")).to_have_text("0.25000000 BTC")
            playwright.expect(page.locator("#forecast-table")).to_contain_text("2025-12-01")

            page.locator("#preset-name").fill("Vault Forecast")
            page.locator("#preset-type").select_option("forecast")
            page.get_by_role("button", name="Save Current Filters").click()
            playwright.expect(page.locator("#presets-list")).to_contain_text("Vault Forecast")
            playwright.expect(page.locator("#history-list")).to_contain_text("forecast")

            # Navigate back to dashboard and click into wallet detail
            page.locator('.app-sidebar .nav-item[data-route="dashboard"]').click()
            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

            page.locator('[data-wallet-id="Vault"]').click()
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            playwright.expect(page.locator("#wallet-view-balance")).to_contain_text("BTC")
            playwright.expect(page.locator("#wallet-tx-list")).not_to_contain_text("Not Found")
            assert "/wallet/Vault" in page.url

            # Verify direct-load of wallet URL works (API resolves from subpath)
            page.goto(base_url + "wallet/Strike", wait_until="networkidle")
            if page.locator("#login-panel").is_visible():
                page.get_by_label("Passphrase").fill("orange-hodl")
                page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Strike")
            playwright.expect(page.locator("#wallet-view-balance")).to_contain_text("BTC")
            playwright.expect(page.locator("#wallet-tx-list")).not_to_contain_text("Not Found")

            # Navigate to ledger via sidebar
            page.locator('.app-sidebar .nav-item[data-route="ledger"]').click()
            playwright.expect(page.get_by_role("heading", name="Ledger")).to_be_visible()
            playwright.expect(page.locator("#ledger-balance")).to_contain_text("BTC")
            playwright.expect(page.locator("#ledger-table")).not_to_contain_text("No transactions loaded yet.")
            assert "/ledger" in page.url

            # Verify direct-load of ledger URL works
            page.goto(base_url + "ledger", wait_until="networkidle")
            if page.locator("#login-panel").is_visible():
                page.get_by_label("Passphrase").fill("orange-hodl")
                page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.get_by_role("heading", name="Ledger")).to_be_visible()
            playwright.expect(page.locator("#ledger-balance")).to_contain_text("BTC")

            # Navigate to wallets via sidebar
            page.locator('.app-sidebar .nav-item[data-route="wallets"]').click()
            playwright.expect(page.get_by_role("heading", name="Wallets")).to_be_visible()
            playwright.expect(page.locator("#wallets-table")).to_contain_text("Strike")
            playwright.expect(page.locator("#wallets-table")).to_contain_text("Vault")
            assert "/wallets" in page.url

            # Record flows only allow existing active wallets; no free-text
            # wallet input may create an accidental ledger category.
            page.locator('.app-sidebar .nav-item[data-route="record"]').click()
            playwright.expect(page.get_by_role("heading", name="Record Transaction")).to_be_visible()
            for select_id in (
                "buy-wallet",
                "sell-wallet",
                "transfer-from",
                "transfer-to",
                "interest-wallet",
            ):
                wallet_select = page.locator(f"#{select_id}")
                playwright.expect(wallet_select).to_be_attached()
                playwright.expect(wallet_select.locator('option[value="Strike"]')).to_be_attached()
                playwright.expect(wallet_select.locator('option[value="Vault"]')).to_be_attached()
            page.get_by_role("button", name="Transfer").click()
            page.locator("#transfer-from").select_option("Strike")
            page.locator("#transfer-to").select_option("Vault")

            # Reloading the direct route must restore the constrained options.
            page.goto(base_url + "record", wait_until="networkidle")
            playwright.expect(page.get_by_role("heading", name="Record Transaction")).to_be_visible()
            playwright.expect(page.locator('#buy-wallet option[value="Strike"]')).to_be_attached()
            playwright.expect(page.locator('#buy-wallet option[value="Vault"]')).to_be_attached()

            # Verify the disclosed ledger filter exposes wallet options.
            page.locator('.app-sidebar .nav-item[data-route="ledger"]').click()
            page.locator("#ledger-filter-toggle").click()
            playwright.expect(page.locator("#ledger-filter-toggle")).to_have_attribute("aria-expanded", "true")
            playwright.expect(page.locator("#ledger-wallet")).to_be_visible()
            playwright.expect(page.locator('#ledger-wallet option[value="Strike"]')).to_be_attached()
            playwright.expect(page.locator('#ledger-wallet option[value="Vault"]')).to_be_attached()

            # Verify direct-load of wallets URL works
            page.goto(base_url + "wallets", wait_until="networkidle")
            if page.locator("#login-panel").is_visible():
                page.get_by_label("Passphrase").fill("orange-hodl")
                page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.get_by_role("heading", name="Wallets")).to_be_visible()
            playwright.expect(page.locator("#wallets-table")).to_contain_text("Strike")

            # Enter wallet detail directly from wallets and confirm verification panel renders
            page.locator("#wallets-table tr", has_text="Vault").get_by_role("button", name="Open").click()
            playwright.expect(page.locator("#wallet-view-title")).to_be_visible()
            playwright.expect(page.locator("#wallet-verification-status")).to_have_text("Unverified")
            playwright.expect(page.locator("#wallet-verification-chip")).to_have_text("unverified")
            playwright.expect(page.locator("#wallet-verification-submit")).to_be_enabled()
            playwright.expect(page.locator("#wallet-proof-chip")).to_have_text("untested")
            playwright.expect(page.locator("#wallet-proof-submit")).to_be_enabled()
            playwright.expect(page.locator("#wallet-proof-latest")).to_contain_text("No proof of spend recorded")
            assert page.locator("#wallet-verification-history").count() == 0

            # Navigate to trades via sidebar
            page.locator('.app-sidebar .nav-item[data-route="trades"]').click()
            playwright.expect(page.get_by_role("heading", name="Trades")).to_be_visible()
            playwright.expect(page.locator("#trades-table")).not_to_contain_text("No trades loaded yet.")
            assert "/trades" in page.url

            # Toggle to liquidity view
            page.locator("#trades-tab-liquidity").click()
            playwright.expect(page.locator("#liquidity-table")).not_to_contain_text("No liquidity data loaded yet.")
            playwright.expect(page.locator("#liq-total-holdings")).to_contain_text("BTC")

            # Toggle back to trade history
            page.locator("#trades-tab-history").click()
            playwright.expect(page.locator("#trades-table")).to_be_visible()

            # Verify direct-load of trades URL works
            page.goto(base_url + "trades", wait_until="networkidle")
            if page.locator("#login-panel").is_visible():
                page.get_by_label("Passphrase").fill("orange-hodl")
                page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.get_by_role("heading", name="Trades")).to_be_visible()
            playwright.expect(page.locator("#trades-table")).not_to_contain_text("No trades loaded yet.")
        finally:
            if browser is not None:
                browser.close()
            if manager is not None:
                manager.stop()


def test_proof_of_spend_state_is_wallet_scoped_and_privacy_aware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    db_path = str(tmp_path / "proof-smoke.sqlite3")
    _seed_smoke_database(db_path)

    class _DelayedAcceptingCore:
        def test_mempool_accept(self, raw_transaction_hex: str) -> dict[str, object]:
            time.sleep(0.4)
            return {
                "txid": "a" * 64,
                "wtxid": "b" * 64,
                "allowed": True,
                "vsize": 141,
                "fees": {"base": 0.0000141},
            }

    monkeypatch.setattr(
        "web.services.proof_of_spend.ProofOfSpendRPCClient",
        lambda config: _DelayedAcceptingCore(),
    )

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
            page.get_by_label("Passphrase").fill("orange-hodl")
            page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

            page.evaluate("navigateToWallet('Vault')")
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            playwright.expect(page.locator("#wallet-proof-submit")).to_be_enabled()
            page.locator("#wallet-proof-transaction").fill("deadbeef")

            page.evaluate("navigateTo('dashboard')")
            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")
            page.evaluate("navigateToWallet('Vault')")
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            page.locator("#wallet-proof-transaction").fill("cafebabe")

            page.evaluate("navigateToWallet('Strike')")
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Strike")
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")

            page.evaluate("navigateToWallet('Vault')")
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            page.locator("#wallet-proof-transaction").fill("00")
            page.locator("#wallet-proof-submit").click()
            page.evaluate("navigateToWallet('Strike')")
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Strike")
            page.wait_for_timeout(800)
            playwright.expect(page.locator("#wallet-proof-chip")).to_have_text("untested")
            playwright.expect(page.locator("#wallet-proof-latest")).to_contain_text(
                "No proof of spend recorded"
            )
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")

            page.evaluate("navigateToWallet('Vault')")
            playwright.expect(page.locator("#wallet-proof-chip")).to_have_text("accepted")
            playwright.expect(page.locator("#wallet-proof-latest")).to_contain_text(
                "Wallet association: operator-attested."
            )
            page.locator("#wallet-proof-transaction").fill("deadbeef")
            page.evaluate("BtcPrivacy.setPreference('on')")
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")
            playwright.expect(page.locator("#wallet-proof-transaction")).to_be_disabled()
            playwright.expect(page.locator("#wallet-proof-latest")).to_contain_text(
                "Transaction •••••"
            )
            playwright.expect(page.locator("#wallet-proof-latest")).not_to_contain_text(
                "aaaaaaaaaaaa"
            )
            playwright.expect(page.locator("#wallet-proof-latest")).to_contain_text(
                "••••• fee"
            )

            # A same-wallet status refresh must not supersede an active proof
            # submission or re-enable its controls before the POST completes.
            page.evaluate("BtcPrivacy.setPreference('off')")
            playwright.expect(page.locator("#wallet-proof-submit")).to_be_enabled()
            page.locator("#wallet-proof-transaction").fill("00")
            page.locator("#wallet-proof-submit").click()
            page.evaluate("window.dispatchEvent(new CustomEvent('btc:denom-change'))")
            page.wait_for_timeout(100)
            playwright.expect(page.locator("#wallet-proof-submit")).to_have_text("Testing...")
            playwright.expect(page.locator("#wallet-proof-submit")).to_be_disabled()
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("00")
            playwright.expect(page.locator("#wallet-proof-message")).to_contain_text(
                "Proof accepted"
            )
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")
            playwright.expect(page.locator("#wallet-proof-submit")).to_be_enabled()

            # Explicit logout and a later authentication failure both dispose
            # of pasted bearer data before another operator can sign in.
            page.locator("#wallet-proof-transaction").fill("deadbeef")
            page.locator("#session-action").click()
            playwright.expect(page.locator("#login-panel")).to_be_visible()
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")
            page.get_by_label("Passphrase").fill("orange-hodl")
            page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.locator("#wallet-view-title")).to_have_text("Vault")
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")

            page.locator("#wallet-proof-transaction").fill("cafebabe")
            page.context.clear_cookies()
            page.evaluate("refreshSession()")
            playwright.expect(page.locator("#login-panel")).to_be_visible()
            playwright.expect(page.locator("#wallet-proof-transaction")).to_have_value("")
        finally:
            if browser is not None:
                browser.close()
            if manager is not None:
                manager.stop()


def test_mobile_data_views_stay_within_the_viewport(tmp_path: Path) -> None:
    """Dense mobile views use cards (or contained table scrolling), never page overflow."""
    playwright = pytest.importorskip("playwright.sync_api")
    db_path = str(tmp_path / "mobile-smoke.sqlite3")
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
            page = browser.new_page(viewport={"width": 375, "height": 812})

            def assert_viewport_contained() -> None:
                dimensions = page.evaluate(
                    "({ viewport: window.innerWidth, document: document.documentElement.scrollWidth })"
                )
                assert dimensions["document"] <= dimensions["viewport"], dimensions

            page.goto(base_url, wait_until="networkidle")
            page.get_by_label("Passphrase").fill("orange-hodl")
            page.get_by_role("button", name="Sign In").click()
            playwright.expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "wallet/Vault", wait_until="networkidle")
            playwright.expect(page.locator("#wallet-view")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "record", wait_until="networkidle")
            playwright.expect(page.locator("#record-view")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "reports", wait_until="networkidle")
            playwright.expect(page.locator("#reports-view")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "settings", wait_until="networkidle")
            playwright.expect(page.locator("#settings-view")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "ledger", wait_until="networkidle")
            playwright.expect(page.locator("#ledger-cards")).to_be_visible()
            assert_viewport_contained()

            page.goto(base_url + "trades", wait_until="networkidle")
            playwright.expect(page.locator("#trades-cards")).to_be_visible()
            assert_viewport_contained()
            page.locator("#trades-tab-liquidity").click()
            playwright.expect(page.locator("#liquidity-cards")).to_be_visible()
            playwright.expect(page.locator("#liquidity-cards")).to_contain_text("Strike")
            assert_viewport_contained()

            page.goto(base_url + "wallets", wait_until="networkidle")
            playwright.expect(page.locator("#wallets-cards")).to_be_visible()
            playwright.expect(page.locator("#wallets-cards")).to_contain_text("Strike")
            assert_viewport_contained()

            page.goto(base_url + "tax", wait_until="networkidle")
            playwright.expect(page.locator("#gains-cards")).to_be_visible()
            playwright.expect(page.locator("#forecast-cards")).to_be_visible()
            page.get_by_role("button", name="Load Gains").click()
            playwright.expect(page.locator("#gains-cards")).to_contain_text("12/01/2024")
            page.locator("#forecast-wallet").fill("Vault")
            page.locator("#forecast-quantity").fill("0.2")
            page.get_by_role("button", name="Forecast Sale").click()
            playwright.expect(page.locator("#forecast-cards")).to_contain_text("2025-12-01")
            assert_viewport_contained()

            page.goto(base_url + "import", wait_until="networkidle")
            page.locator("#import-file").set_input_files({
                "name": "mobile-preview.csv",
                "mimeType": "text/csv",
                "buffer": MOBILE_IMPORT_CSV.encode(),
            })
            page.get_by_role("button", name="Upload & Preview").click()
            playwright.expect(page.locator("#import-step-2")).to_be_visible()
            playwright.expect(page.locator("#import-preview-table")).to_contain_text("Mobile preview")
            assert_viewport_contained()
        finally:
            if browser is not None:
                browser.close()
            if manager is not None:
                manager.stop()

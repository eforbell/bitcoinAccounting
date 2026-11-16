"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.config import WebConfig, load_web_config, normalized_base_path
from web.routes import auth_router, chain_router, health_router, imports_router, ledger_router, portfolio_router, reports_router, tax_router, trades_router, ui_router, verification_router, wallets_router
from web.startup import validate_startup_config
from web.suite_identity import SuiteIdentity, SuiteIdentityMiddleware, create_suite_identity
from pathlib import Path


def create_app(config: WebConfig | None = None, *, suite: SuiteIdentity | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = load_web_config()
    validate_startup_config(config)
    base_path = normalized_base_path(config.web_base_path)
    # Who is asking (web/suite_identity.py): checked once here, so a bad tailnet configuration stops startup.
    suite = suite or create_suite_identity(os.environ)
    if suite.tailnet and suite.base_path != f"{base_path}/":
        raise ValueError(
            f"APP_PUBLIC_URL's path '{suite.base_path}' must be the app's mount, '{base_path}/' "
            "(BITCOIN_ACCOUNTING_WEB_BASE_PATH)"
        )
    docs_url = "/docs" if config.docs_enabled else None
    redoc_url = "/redoc" if config.docs_enabled else None
    openapi_url = "/openapi.json" if config.docs_enabled else None

    app = FastAPI(
        title=config.app_name,
        root_path=base_path,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.web_config = config
    app.state.web_base_path = base_path
    app.state.suite = suite
    static_dir = Path(__file__).resolve().parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(ui_router)
    app.include_router(auth_router)
    app.include_router(chain_router)
    app.include_router(health_router)
    app.include_router(ledger_router)
    app.include_router(portfolio_router)
    app.include_router(reports_router)
    app.include_router(tax_router)
    app.include_router(trades_router)
    app.include_router(verification_router)
    app.include_router(wallets_router)
    app.include_router(imports_router)

    # Drop cached report bytes after any successful write that can change the
    # charts (ledger transactions, imports, wallet custody). Substring matching
    # tolerates a mounted base_path prefix on the request path.
    _REPORT_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    _REPORT_MUTATION_PREFIXES = ("/api/ledger", "/api/import", "/api/wallets")

    @app.middleware("http")
    async def _invalidate_reports_cache(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.method in _REPORT_MUTATION_METHODS and response.status_code < 400:
            path = request.url.path
            if any(prefix in path for prefix in _REPORT_MUTATION_PREFIXES):
                from web.services.reports import clear_cache

                clear_cache()
        return response

    # Added last, so it runs first: in tailnet mode the request guard and the member gate see every request before
    # anything reads it. In local mode it passes everything through.
    app.add_middleware(SuiteIdentityMiddleware, suite=suite)

    return app

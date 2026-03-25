"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.config import WebConfig, load_web_config, normalized_base_path
from web.routes import auth_router, health_router, imports_router, ledger_router, portfolio_router, tax_router, ui_router, wallets_router
from web.startup import validate_startup_config
from pathlib import Path


def create_app(config: WebConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = load_web_config()
    validate_startup_config(config)
    base_path = normalized_base_path(config.web_base_path)
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
    static_dir = Path(__file__).resolve().parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(ui_router)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(ledger_router)
    app.include_router(portfolio_router)
    app.include_router(tax_router)
    app.include_router(wallets_router)
    app.include_router(imports_router)

    return app

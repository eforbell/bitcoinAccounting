"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from web.config import WebConfig, load_web_config
from web.routes import auth_router, health_router, tax_router
from web.startup import validate_startup_config


def create_app(config: WebConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = load_web_config()
    validate_startup_config(config)
    docs_url = "/docs" if config.docs_enabled else None
    redoc_url = "/redoc" if config.docs_enabled else None
    openapi_url = "/openapi.json" if config.docs_enabled else None

    app = FastAPI(
        title=config.app_name,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.web_config = config
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(tax_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "bitcoin-accounting-api",
            "status": "ok",
        }

    return app

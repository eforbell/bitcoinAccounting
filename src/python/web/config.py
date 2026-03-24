"""Web application configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


class WebConfigurationError(RuntimeError):
    """Raised when web configuration is internally inconsistent."""


@dataclass(frozen=True)
class WebConfig:
    """Runtime configuration for the web application."""

    app_name: str = "Bitcoin Accounting API"
    app_env: str = "development"
    web_base_path: str = ""
    docs_enabled: bool = True
    db_backend: str = "sqlite"
    allow_sqlite_in_production: bool = False
    auth_enabled: bool = False
    auth_passphrase: str | None = None
    session_secret: str | None = None
    session_cookie_name: str = "ba_session"
    session_cookie_secure: bool | None = None
    session_ttl_seconds: int = 60 * 60 * 24 * 7


def load_web_config() -> WebConfig:
    """Load web configuration from environment variables."""
    app_env = os.getenv("BITCOIN_ACCOUNTING_ENV", "development").strip() or "development"
    web_base_path = os.getenv("BITCOIN_ACCOUNTING_WEB_BASE_PATH", "").strip()
    docs_raw = os.getenv("BITCOIN_ACCOUNTING_WEB_DOCS", "1").strip().lower()
    docs_enabled = docs_raw not in {"0", "false", "off", "no"}
    db_backend = os.getenv("DB_BACKEND", "sqlite").strip().lower() or "sqlite"
    allow_sqlite_raw = os.getenv("BITCOIN_ACCOUNTING_WEB_ALLOW_SQLITE", "0").strip().lower()
    allow_sqlite_in_production = allow_sqlite_raw in {"1", "true", "on", "yes"}
    auth_raw = os.getenv("BITCOIN_ACCOUNTING_AUTH_ENABLED", "0").strip().lower()
    auth_enabled = auth_raw in {"1", "true", "on", "yes"}
    auth_passphrase = os.getenv("BITCOIN_ACCOUNTING_AUTH_PASSPHRASE")
    session_secret = os.getenv("BITCOIN_ACCOUNTING_SESSION_SECRET")
    cookie_name = os.getenv("BITCOIN_ACCOUNTING_SESSION_COOKIE", "ba_session").strip() or "ba_session"
    cookie_secure_raw = os.getenv("BITCOIN_ACCOUNTING_SESSION_COOKIE_SECURE")
    session_cookie_secure = None
    if cookie_secure_raw is not None:
        session_cookie_secure = cookie_secure_raw.strip().lower() in {"1", "true", "on", "yes"}
    ttl_raw = os.getenv("BITCOIN_ACCOUNTING_SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7)).strip()
    session_ttl_seconds = int(ttl_raw)
    return WebConfig(
        app_env=app_env,
        web_base_path=web_base_path,
        docs_enabled=docs_enabled,
        db_backend=db_backend,
        allow_sqlite_in_production=allow_sqlite_in_production,
        auth_enabled=auth_enabled,
        auth_passphrase=auth_passphrase,
        session_secret=session_secret,
        session_cookie_name=cookie_name,
        session_cookie_secure=session_cookie_secure,
        session_ttl_seconds=session_ttl_seconds,
    )


def normalized_base_path(raw_path: str) -> str:
    """Normalize configured web base path for subpath-mounted deployments."""
    value = raw_path.strip()
    if value in {"", "/"}:
        return ""
    if not value.startswith("/"):
        raise WebConfigurationError(
            "BITCOIN_ACCOUNTING_WEB_BASE_PATH must start with '/' when set."
        )
    normalized = value.rstrip("/")
    if not normalized:
        return ""
    return normalized


def validate_web_config(config: WebConfig) -> None:
    """Validate the effective web configuration.

    Production web mode is PostgreSQL-first by policy. SQLite remains supported
    for low-concurrency/dev scenarios, and can be allowed explicitly in
    production-like environments with `BITCOIN_ACCOUNTING_WEB_ALLOW_SQLITE=1`.
    """
    backend = config.db_backend.strip().lower()
    if backend not in {"sqlite", "postgres"}:
        raise WebConfigurationError(
            f"Unsupported DB_BACKEND '{config.db_backend}'. Expected 'sqlite' or 'postgres'."
        )

    if config.session_ttl_seconds <= 0:
        raise WebConfigurationError("Session TTL must be greater than zero.")

    normalized_base_path(config.web_base_path)

    if config.app_env.lower() in {"production", "prod"}:
        if backend != "postgres" and not config.allow_sqlite_in_production:
            raise WebConfigurationError(
                "Production web mode requires DB_BACKEND=postgres unless "
                "BITCOIN_ACCOUNTING_WEB_ALLOW_SQLITE=1 is set explicitly."
            )

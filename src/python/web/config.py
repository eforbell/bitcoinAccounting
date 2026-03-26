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
    chain_status_enabled: bool = False
    bitcoin_rpc_url: str | None = None
    bitcoin_rpc_cookie_file: str | None = None
    bitcoin_rpc_user: str | None = None
    bitcoin_rpc_password: str | None = None
    bitcoin_rpc_timeout_seconds: float = 3.0
    electrum_host: str | None = None
    electrum_port: int | None = None
    electrum_use_ssl: bool = False
    electrum_timeout_seconds: float = 5.0
    verification_recency_days: int = 30


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
    chain_status_raw = os.getenv("BITCOIN_CHAIN_STATUS_ENABLED", "0").strip().lower()
    chain_status_enabled = chain_status_raw in {"1", "true", "on", "yes"}
    bitcoin_rpc_url = os.getenv("BITCOIN_RPC_URL")
    bitcoin_rpc_cookie_file = os.getenv("BITCOIN_RPC_COOKIE_FILE")
    bitcoin_rpc_user = os.getenv("BITCOIN_RPC_USER")
    bitcoin_rpc_password = os.getenv("BITCOIN_RPC_PASSWORD")
    rpc_timeout_raw = os.getenv("BITCOIN_RPC_TIMEOUT_SECONDS", "3").strip()
    bitcoin_rpc_timeout_seconds = float(rpc_timeout_raw)
    electrum_host = os.getenv("BITCOIN_ELECTRUM_HOST")
    electrum_port_raw = os.getenv("BITCOIN_ELECTRUM_PORT")
    electrum_port = int(electrum_port_raw) if electrum_port_raw else None
    electrum_ssl_raw = os.getenv("BITCOIN_ELECTRUM_SSL", "0").strip().lower()
    electrum_use_ssl = electrum_ssl_raw in {"1", "true", "on", "yes"}
    electrum_timeout_raw = os.getenv("BITCOIN_ELECTRUM_TIMEOUT_SECONDS", "5").strip()
    electrum_timeout_seconds = float(electrum_timeout_raw)
    verification_recency_raw = os.getenv(
        "BITCOIN_ACCOUNTING_VERIFICATION_RECENCY_DAYS",
        "30",
    ).strip()
    verification_recency_days = int(verification_recency_raw)
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
        chain_status_enabled=chain_status_enabled,
        bitcoin_rpc_url=bitcoin_rpc_url,
        bitcoin_rpc_cookie_file=bitcoin_rpc_cookie_file,
        bitcoin_rpc_user=bitcoin_rpc_user,
        bitcoin_rpc_password=bitcoin_rpc_password,
        bitcoin_rpc_timeout_seconds=bitcoin_rpc_timeout_seconds,
        electrum_host=electrum_host,
        electrum_port=electrum_port,
        electrum_use_ssl=electrum_use_ssl,
        electrum_timeout_seconds=electrum_timeout_seconds,
        verification_recency_days=verification_recency_days,
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

    if config.bitcoin_rpc_timeout_seconds <= 0:
        raise WebConfigurationError("Bitcoin RPC timeout must be greater than zero.")

    if config.electrum_timeout_seconds <= 0:
        raise WebConfigurationError("Electrum timeout must be greater than zero.")

    if config.verification_recency_days <= 0:
        raise WebConfigurationError("Verification recency days must be greater than zero.")

    normalized_base_path(config.web_base_path)

    if config.chain_status_enabled:
        rpc_url = (config.bitcoin_rpc_url or "").strip()
        cookie_file = (config.bitcoin_rpc_cookie_file or "").strip()
        rpc_user = (config.bitcoin_rpc_user or "").strip()
        rpc_password = (config.bitcoin_rpc_password or "").strip()

        if not rpc_url:
            raise WebConfigurationError(
                "BITCOIN_RPC_URL must be set when BITCOIN_CHAIN_STATUS_ENABLED=1."
            )

        if not cookie_file and not (rpc_user and rpc_password):
            raise WebConfigurationError(
                "Configure BITCOIN_RPC_COOKIE_FILE or both BITCOIN_RPC_USER and "
                "BITCOIN_RPC_PASSWORD when BITCOIN_CHAIN_STATUS_ENABLED=1."
            )

    if config.app_env.lower() in {"production", "prod"}:
        if backend != "postgres" and not config.allow_sqlite_in_production:
            raise WebConfigurationError(
                "Production web mode requires DB_BACKEND=postgres unless "
                "BITCOIN_ACCOUNTING_WEB_ALLOW_SQLITE=1 is set explicitly."
            )

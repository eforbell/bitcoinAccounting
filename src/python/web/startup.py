"""Startup validation and readiness helpers for the web app."""

from __future__ import annotations

from pathlib import Path

from db import DatabaseBackend, create_tables, get_backend

from web.auth import AuthConfigurationError, require_auth_config
from web.config import WebConfig, WebConfigurationError, validate_web_config
from web.services.tax_state import ensure_tax_state_tables


def validate_startup_config(config: WebConfig) -> None:
    """Validate startup configuration for the web service."""
    validate_web_config(config)
    try:
        require_auth_config(config)
    except AuthConfigurationError as exc:
        raise WebConfigurationError(str(exc)) from exc


def probe_database(backend: DatabaseBackend) -> None:
    """Perform a minimal readiness check against the configured backend."""
    backend.execute_scalar("SELECT 1")


def _missing_postgres_tables(backend: DatabaseBackend) -> list[str]:
    required = {"coins", "ledger", "pair_price", "wallets"}
    rows = backend.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    )
    existing = {str(row["table_name"]) for row in rows}
    return sorted(required - existing)


def ensure_runtime_schema(config: WebConfig, backend: DatabaseBackend) -> None:
    """Ensure the runtime schema expected by the web app is available."""
    backend_type = config.db_backend.strip().lower()
    if backend_type == "sqlite":
        create_tables(backend)
    else:
        missing = _missing_postgres_tables(backend)
        if missing:
            tables_sql = Path(__file__).resolve().parents[2] / "sql" / "tables.sql"
            raise WebConfigurationError(
                "PostgreSQL core schema is missing required tables: "
                f"{', '.join(missing)}. Initialize PostgreSQL with "
                f"`psql -U <db-admin> -d <database> -f {tables_sql}` before deploying the web app."
            )
    ensure_tax_state_tables(backend)


def initialize_web_runtime(config: WebConfig | None = None) -> dict[str, object]:
    """Validate config, connect to the backend, and prepare runtime tables."""
    if config is None:
        from web.config import load_web_config

        config = load_web_config()

    validate_startup_config(config)
    backend = get_backend(config.db_backend)
    try:
        probe_database(backend)
        ensure_runtime_schema(config, backend)
        return {
            "status": "ok",
            "database_backend": config.db_backend,
            "base_path": config.web_base_path,
        }
    finally:
        backend.close()

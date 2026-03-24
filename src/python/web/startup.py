"""Startup validation and readiness helpers for the web app."""

from __future__ import annotations

from db import DatabaseBackend

from web.auth import AuthConfigurationError, require_auth_config
from web.config import WebConfig, WebConfigurationError, validate_web_config


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

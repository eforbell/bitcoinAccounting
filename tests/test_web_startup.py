"""Tests for startup validation and production DB policy."""

from __future__ import annotations

import importlib

import pytest

import web.app as web_app_module
from web.app import create_app
from web.config import WebConfig, WebConfigurationError


def test_production_web_mode_requires_postgres_by_default() -> None:
    with pytest.raises(WebConfigurationError) as excinfo:
        create_app(
            WebConfig(
                app_env="production",
                db_backend="sqlite",
            )
        )

    assert "requires DB_BACKEND=postgres" in str(excinfo.value)


def test_production_can_explicitly_allow_sqlite() -> None:
    app = create_app(
        WebConfig(
            app_env="production",
            db_backend="sqlite",
            allow_sqlite_in_production=True,
        )
    )

    assert app.state.web_config.allow_sqlite_in_production is True


def test_auth_enabled_requires_secret_and_passphrase() -> None:
    with pytest.raises(WebConfigurationError):
        create_app(
            WebConfig(
                auth_enabled=True,
                auth_passphrase=None,
                session_secret=None,
            )
        )


def test_importing_web_app_module_does_not_validate_env_at_import_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITCOIN_ACCOUNTING_ENV", "production")
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.delenv("BITCOIN_ACCOUNTING_WEB_ALLOW_SQLITE", raising=False)

    reloaded = importlib.reload(web_app_module)

    assert hasattr(reloaded, "create_app")

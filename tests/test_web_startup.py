"""Tests for startup validation and production DB policy."""

from __future__ import annotations

import importlib

import pytest

import web.app as web_app_module
import web.cli as web_cli_module
from web.app import create_app
from web.config import WebConfig, WebConfigurationError, normalized_base_path
from web.startup import ensure_runtime_schema, initialize_web_runtime


def test_production_web_mode_requires_postgres_by_default() -> None:
    with pytest.raises(WebConfigurationError) as excinfo:
        create_app(
            WebConfig(
                app_env="production",
                db_backend="sqlite",
                auth_enabled=True,
                auth_passphrase="orange-hodl",
                session_secret="test-secret",
            )
        )

    assert "requires DB_BACKEND=postgres" in str(excinfo.value)


def test_production_web_mode_requires_auth_enabled() -> None:
    with pytest.raises(WebConfigurationError) as excinfo:
        create_app(
            WebConfig(
                app_env="production",
                db_backend="postgres",
                auth_enabled=False,
            )
        )

    assert "requires BITCOIN_ACCOUNTING_AUTH_ENABLED=1" in str(excinfo.value)

def test_production_can_explicitly_allow_sqlite() -> None:
    app = create_app(
        WebConfig(
            app_env="production",
            db_backend="sqlite",
            allow_sqlite_in_production=True,
            auth_enabled=True,
            auth_passphrase="orange-hodl",
            session_secret="test-secret",
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


def test_base_path_is_normalized_for_subpath_mounts() -> None:
    assert normalized_base_path("") == ""
    assert normalized_base_path("/") == ""
    assert normalized_base_path("/bitcoin-accounting/") == "/bitcoin-accounting"


def test_invalid_base_path_is_rejected() -> None:
    with pytest.raises(WebConfigurationError):
        create_app(WebConfig(web_base_path="bitcoin-accounting"))


def test_create_app_sets_fastapi_root_path() -> None:
    app = create_app(WebConfig(web_base_path="/bitcoin-accounting"))

    assert app.root_path == "/bitcoin-accounting"


class FakePostgresBackend:
    def __init__(self, table_names: list[str]) -> None:
        self.table_names = table_names
        self.commits = 0

    def execute(self, query: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        if "information_schema.tables" in query:
            return [{"table_name": name} for name in self.table_names]
        if "CREATE TABLE IF NOT EXISTS web_tax_" in query:
            return []
        return []

    def execute_one(self, query: str, params: dict[str, object] | None = None) -> dict[str, object] | None:
        return None

    def execute_scalar(self, query: str, params: dict[str, object] | None = None) -> object:
        return 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_postgres_runtime_schema_requires_core_tables() -> None:
    backend = FakePostgresBackend(["ledger"])

    with pytest.raises(WebConfigurationError) as excinfo:
        ensure_runtime_schema(WebConfig(db_backend="postgres"), backend)

    message = str(excinfo.value)
    assert "missing required tables" in message
    assert "src/sql/tables.sql" in message


def test_initialize_web_runtime_returns_status_for_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    db_path = tmp_path / "web-runtime.db"
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    result = initialize_web_runtime(WebConfig(db_backend="sqlite", web_base_path="/bitcoin-accounting"))

    assert result == {
        "status": "ok",
        "database_backend": "sqlite",
        "base_path": "/bitcoin-accounting",
    }


def test_web_init_cli_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_cli_module,
        "initialize_web_runtime",
        lambda: {"status": "ok", "database_backend": "postgres", "base_path": "/bitcoin-accounting"},
    )

    assert web_cli_module.main(["--json"]) == 0


def test_web_init_cli_returns_json_for_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        web_cli_module,
        "initialize_web_runtime",
        lambda: (_ for _ in ()).throw(RuntimeError("database offline")),
    )

    exit_code = web_cli_module.main(["--json"])

    assert exit_code == 1
    assert '"status": "error"' in capsys.readouterr().out

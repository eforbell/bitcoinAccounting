"""Web-native tax state persistence for recent tax workflow history."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from db import DatabaseBackend
from web.models import TaxHistoryEntryResource

_HISTORY_TABLE = "web_tax_history"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.isoformat()


def ensure_tax_state_tables(backend: DatabaseBackend) -> None:
    """Create the web tax history table if it does not already exist."""
    backend.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_HISTORY_TABLE} (
            history_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            coin TEXT NOT NULL,
            tax_year INTEGER NULL,
            wallet_id TEXT NULL,
            quantity REAL NULL,
            sale_price_usd REAL NULL,
            artifact_type TEXT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    backend.commit()


def _row_to_history(row: dict[str, object]) -> TaxHistoryEntryResource:
    return TaxHistoryEntryResource(
        history_id=str(row["history_id"]),
        action=str(row["action"]),
        coin=str(row["coin"]),
        tax_year=int(row["tax_year"]) if row["tax_year"] is not None else None,
        wallet_id=str(row["wallet_id"]) if row["wallet_id"] is not None else None,
        quantity=float(row["quantity"]) if row["quantity"] is not None else None,
        sale_price_usd=(
            float(row["sale_price_usd"]) if row["sale_price_usd"] is not None else None
        ),
        artifact_type=str(row["artifact_type"]) if row["artifact_type"] is not None else None,
        status=str(row["status"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )


def record_tax_history(
    backend: DatabaseBackend,
    *,
    action: str,
    coin: str,
    tax_year: int | None = None,
    wallet_id: str | None = None,
    quantity: float | None = None,
    sale_price_usd: float | None = None,
    artifact_type: str | None = None,
    status: str = "success",
) -> TaxHistoryEntryResource:
    """Record a lightweight recent tax workflow event."""
    ensure_tax_state_tables(backend)
    now = _utcnow()
    history_id = str(uuid4())
    backend.execute(
        f"""
        INSERT INTO {_HISTORY_TABLE} (
            history_id, action, coin, tax_year, wallet_id, quantity,
            sale_price_usd, artifact_type, status, created_at
        ) VALUES (
            :history_id, :action, :coin, :tax_year, :wallet_id, :quantity,
            :sale_price_usd, :artifact_type, :status, :created_at
        )
        """,
        {
            "history_id": history_id,
            "action": action,
            "coin": coin,
            "tax_year": tax_year,
            "wallet_id": wallet_id,
            "quantity": quantity,
            "sale_price_usd": sale_price_usd,
            "artifact_type": artifact_type,
            "status": status,
            "created_at": _isoformat(now),
        },
    )
    backend.commit()
    row = backend.execute_one(
        f"SELECT * FROM {_HISTORY_TABLE} WHERE history_id = :history_id",
        {"history_id": history_id},
    )
    assert row is not None
    return _row_to_history(row)


def list_tax_history(
    backend: DatabaseBackend,
    *,
    limit: int = 20,
) -> list[TaxHistoryEntryResource]:
    """Return recent tax workflow history."""
    ensure_tax_state_tables(backend)
    rows = backend.execute(
        f"""
        SELECT history_id, action, coin, tax_year, wallet_id, quantity,
               sale_price_usd, artifact_type, status, created_at
        FROM {_HISTORY_TABLE}
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    return [_row_to_history(row) for row in rows]

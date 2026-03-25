"""Write audit log service for web operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from db import DatabaseBackend


AUDIT_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS write_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    operator TEXT NOT NULL DEFAULT 'operator',
    detail_json TEXT,
    outcome TEXT NOT NULL DEFAULT 'success'
)
"""

AUDIT_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS write_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    operator TEXT NOT NULL DEFAULT 'operator',
    detail_json TEXT,
    outcome TEXT NOT NULL DEFAULT 'success'
)
"""


def ensure_audit_table(backend: DatabaseBackend) -> None:
    """Create the audit table if it does not exist."""
    from db.sqlite import SqliteBackend

    ddl = AUDIT_TABLE_SQLITE if isinstance(backend, SqliteBackend) else AUDIT_TABLE_POSTGRES
    backend.execute(ddl)
    backend.commit()


def log_write_action(
    backend: DatabaseBackend,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    operator: str = "operator",
    detail: dict[str, Any] | None = None,
    outcome: str = "success",
) -> None:
    """Insert a row into the write audit log."""
    ensure_audit_table(backend)
    query = """
        INSERT INTO write_audit_log
            (timestamp, action, entity_type, entity_id, operator, detail_json, outcome)
        VALUES
            (:timestamp, :action, :entity_type, :entity_id, :operator, :detail_json, :outcome)
    """
    backend.execute(
        query,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operator": operator,
            "detail_json": json.dumps(detail) if detail else None,
            "outcome": outcome,
        },
    )
    backend.commit()


def get_audit_log(
    backend: DatabaseBackend,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Read recent audit log entries."""
    ensure_audit_table(backend)
    conditions = []
    params: dict[str, Any] = {"limit": limit}
    if entity_type:
        conditions.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if entity_id:
        conditions.append("entity_id = :entity_id")
        params["entity_id"] = entity_id
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT id, timestamp, action, entity_type, entity_id, operator, detail_json, outcome
        FROM write_audit_log
        {where}
        ORDER BY id DESC
        LIMIT :limit
    """
    rows = backend.execute(query, params)
    return [dict(row) for row in rows]

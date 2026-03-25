"""Import service layer for web routes."""

from __future__ import annotations

import json
from typing import Any

from imports.base import BaseImporter
from imports.registry import detect_parser, get_all_parsers, get_parser
from imports.validation import ValidationResult, detect_duplicates, validate_batch


def list_parsers() -> list[dict[str, Any]]:
    """Return metadata for all registered parsers."""
    return [
        {
            "name": p.name.lower(),
            "display_name": p.name,
            "source_type": p.source_type,
            "description": p.description,
            "expected_columns": p.expected_columns,
        }
        for p in get_all_parsers()
    ]


def _validation_to_dict(result: ValidationResult) -> dict[str, Any]:
    """Serialize a ValidationResult to a JSON-safe dict."""
    return {
        "valid_count": result.valid_count,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "errors": [[idx, msgs] for idx, msgs in result.errors],
        "warnings": [[idx, msgs] for idx, msgs in result.warnings],
    }


def _sanitize_tx(tx: dict[str, Any]) -> dict[str, Any]:
    """Ensure all values in a transaction dict are JSON-serializable."""
    clean: dict[str, Any] = {}
    for k, v in tx.items():
        if isinstance(v, float):
            clean[k] = v
        elif v is None:
            clean[k] = v
        else:
            clean[k] = str(v) if not isinstance(v, (int, bool, list, dict)) else v
    return clean


def parse_upload(
    file_path: str,
    parser_name: str | None = None,
    wallet_name: str | None = None,
    withdraw_to: str | None = None,
) -> dict[str, Any]:
    """Parse an uploaded CSV and return preview data.

    Returns a dict with parser info, transactions, preview rows, and validation.
    Raises ValueError on detection/parse failure.
    """
    parser: BaseImporter | None = None

    if parser_name:
        parser = get_parser(parser_name)
        if parser is None:
            raise ValueError(f"Unknown parser: {parser_name!r}")
    else:
        parser = detect_parser(file_path)
        if parser is None:
            raise ValueError(
                "Could not auto-detect CSV format. "
                "Please select a parser manually."
            )

    if parser.source_type == "wallet" and not wallet_name:
        raise ValueError(
            f"Parser '{parser.name}' is a wallet parser and requires a wallet_name. "
            "Please select or create a wallet before uploading."
        )

    column_names, transactions = parser.parse(
        file_path,
        wallet_name=wallet_name,
        withdraw_to=withdraw_to,
    )

    validation = validate_batch(transactions)

    sanitized = [_sanitize_tx(tx) for tx in transactions]
    preview_rows = sanitized[:10]

    return {
        "parser_used": parser.name.lower(),
        "display_name": parser.name,
        "source_type": parser.source_type,
        "filename": "",  # caller sets this
        "column_names": column_names,
        "row_count": len(transactions),
        "preview_rows": preview_rows,
        "transactions": sanitized,
        "validation": _validation_to_dict(validation),
    }


def check_duplicates_service(
    transactions: list[dict[str, Any]],
    backend: Any,
) -> dict[str, Any]:
    """Run duplicate detection and return indices."""
    dupes = detect_duplicates(transactions, backend)
    # Build set of duplicate indices by identity comparison
    dupe_set = set()
    for i, tx in enumerate(transactions):
        for d in dupes:
            if tx is d:
                dupe_set.add(i)
                break
    return {
        "total": len(transactions),
        "duplicate_count": len(dupe_set),
        "duplicate_indices": sorted(dupe_set),
    }


def execute_import(
    accounts: Any,
    transactions: list[dict[str, Any]],
    skip_indices: list[int] | None = None,
) -> dict[str, int]:
    """Execute the import, optionally skipping certain indices.

    Server-side validation is enforced: rows that fail validate_transaction()
    are rejected and counted as skipped, regardless of what the client sent.
    Operator-skipped rows (via skip_indices) are also counted in the total.
    """
    from imports.validation import validate_transaction

    skip_set = set(skip_indices) if skip_indices else set()
    operator_skipped = len(skip_set)

    # Filter out operator-skipped rows, then validate remaining
    valid = []
    invalid_count = 0
    for i, tx in enumerate(transactions):
        if i in skip_set:
            continue
        errors = validate_transaction(tx)
        if errors:
            invalid_count += 1
        else:
            valid.append(tx)

    result = accounts.import_transactions(valid)
    imported = result.get("imported", 0)
    core_skipped = result.get("skipped", 0)

    return {
        "imported": imported,
        "skipped": operator_skipped + invalid_count + core_skipped,
    }


def get_import_history(
    backend: Any,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve recent import runs from the audit log."""
    from web.services.audit import get_audit_log

    logs = get_audit_log(backend, entity_type="import", limit=limit)
    history = []
    for entry in logs:
        detail = {}
        if entry.get("detail_json"):
            try:
                detail = json.loads(entry["detail_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        history.append({
            "id": entry["id"],
            "timestamp": entry["timestamp"],
            "parser_name": detail.get("parser_name", ""),
            "filename": entry.get("entity_id", ""),
            "imported": detail.get("imported", 0),
            "skipped": detail.get("skipped", 0),
            "row_count": detail.get("row_count", 0),
            "operator": entry.get("operator", "operator"),
            "outcome": entry.get("outcome", "success"),
        })
    return history


def get_parser_help(parser_name: str) -> dict[str, Any] | None:
    """Return format help for a parser, or None if not found."""
    parser = get_parser(parser_name)
    if parser is None:
        return None
    return {
        "parser_name": parser.name.lower(),
        "display_name": parser.name,
        "source_type": parser.source_type,
        "help_text": parser.get_format_help(),
        "expected_columns": parser.expected_columns,
    }

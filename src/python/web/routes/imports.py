"""Authenticated import routes for CSV upload, preview, and commit."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from bitcoinAccounts import BitcoinAccounts
from db import DatabaseBackend
from web.auth import require_authenticated_principal
from web.dependencies import get_request_accounts, get_request_backend
from web.services.audit import log_write_action
from web.services.imports import (
    check_duplicates_service,
    execute_import,
    get_import_history,
    get_parser_help,
    list_parsers,
    parse_upload,
)

router = APIRouter(
    prefix="/api/import",
    tags=["import"],
    dependencies=[Depends(require_authenticated_principal)],
)


@router.get("/parsers")
def parsers_list() -> dict[str, Any]:
    """Return metadata for all available import parsers."""
    return {"parsers": list_parsers()}


@router.get("/parsers/{parser_name}/help")
def parser_help(parser_name: str) -> dict[str, Any]:
    """Return format help text for a specific parser."""
    result = get_parser_help(parser_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Parser not found: {parser_name!r}")
    return result


@router.post("/parse")
async def parse_file(
    file: UploadFile = File(...),
    parser: str = Form(""),
    wallet_name: str = Form(""),
    withdraw_to: str = Form(""),
) -> dict[str, Any]:
    """Upload a CSV, auto-detect or use explicit parser, return preview."""
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    try:
        contents = await file.read()
        if not contents.strip():
            raise HTTPException(status_code=422, detail="Uploaded file is empty")
        tmp.write(contents)
        tmp.flush()
        tmp.close()

        result = parse_upload(
            tmp.name,
            parser_name=parser or None,
            wallet_name=wallet_name or None,
            withdraw_to=withdraw_to or None,
        )
        result["filename"] = file.filename or "upload.csv"
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/check-duplicates")
def check_duplicates(
    body: dict[str, Any],
    backend: DatabaseBackend = Depends(get_request_backend),
) -> dict[str, Any]:
    """Check parsed transactions for potential duplicates in the database."""
    transactions = body.get("transactions", [])
    return check_duplicates_service(transactions, backend)


@router.post("/commit")
def commit_import(
    body: dict[str, Any],
    accounts: BitcoinAccounts = Depends(get_request_accounts),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> dict[str, Any]:
    """Commit parsed transactions to the ledger."""
    transactions = body.get("transactions", [])
    parser_name = body.get("parser_name", "")
    filename = body.get("filename", "")
    skip_indices = body.get("skip_indices", [])

    if not transactions:
        raise HTTPException(status_code=422, detail="No transactions to import")

    result = execute_import(accounts, transactions, skip_indices=skip_indices or None)

    log_write_action(
        backend,
        action="import.execute",
        entity_type="import",
        entity_id=filename,
        detail={
            "parser_name": parser_name,
            "filename": filename,
            "imported": result.get("imported", 0),
            "skipped": result.get("skipped", 0),
            "row_count": len(transactions),
        },
    )

    return {
        "status": "ok",
        "imported": result.get("imported", 0),
        "skipped": result.get("skipped", 0),
        "parser_name": parser_name,
        "filename": filename,
    }


@router.get("/history")
def import_history(
    limit: int = Query(20, ge=1, le=100),
    backend: DatabaseBackend = Depends(get_request_backend),
) -> dict[str, Any]:
    """Return recent import runs from the audit log."""
    return {"imports": get_import_history(backend, limit=limit)}

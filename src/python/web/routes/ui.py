"""Static web UI routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
_INDEX_FILE = _UI_DIR / "index.html"
_INDEX_HTML: str | None = None


def _get_index_html() -> str:
    global _INDEX_HTML
    if _INDEX_HTML is None:
        _INDEX_HTML = _INDEX_FILE.read_text()
    return _INDEX_HTML


def _shell_response(request: Request) -> HTMLResponse:
    """Return the SPA shell with a <base> tag so relative URLs resolve from the app root."""
    base_path = request.scope.get("root_path", "") or ""
    base_href = base_path.rstrip("/") + "/"
    html = _get_index_html().replace(
        '<meta charset="UTF-8">',
        f'<meta charset="UTF-8">\n  <base href="{base_href}">',
        1,
    )
    return HTMLResponse(html)


@router.get("/", include_in_schema=False)
def web_app_shell(request: Request) -> HTMLResponse:
    """Serve the main web UI shell."""
    return _shell_response(request)


@router.get("/tax", include_in_schema=False)
def web_tax_shell(request: Request) -> HTMLResponse:
    """Serve the tax page within the shared web shell."""
    return _shell_response(request)


@router.get("/record", include_in_schema=False)
def web_record_shell(request: Request) -> HTMLResponse:
    """Serve the transaction entry page within the shared web shell."""
    return _shell_response(request)


@router.get("/ledger", include_in_schema=False)
def web_ledger_shell(request: Request) -> HTMLResponse:
    """Serve the ledger explorer page within the shared web shell."""
    return _shell_response(request)


@router.get("/trades", include_in_schema=False)
def web_trades_shell(request: Request) -> HTMLResponse:
    """Serve the trades and liquidity page within the shared web shell."""
    return _shell_response(request)


@router.get("/import", include_in_schema=False)
def web_import_shell(request: Request) -> HTMLResponse:
    """Serve the import center page within the shared web shell."""
    return _shell_response(request)


@router.get("/wallets", include_in_schema=False)
def web_wallets_shell(request: Request) -> HTMLResponse:
    """Serve the wallet management page within the shared web shell."""
    return _shell_response(request)


@router.get("/wallet/{wallet_id:path}", include_in_schema=False)
def web_wallet_shell(request: Request, wallet_id: str) -> HTMLResponse:
    """Serve the wallet detail page within the shared web shell."""
    return _shell_response(request)

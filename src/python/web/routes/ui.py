"""Static web UI routes."""

from __future__ import annotations

from pathlib import Path
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

router = APIRouter(tags=["ui"])

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
_INDEX_FILE = _UI_DIR / "index.html"
_INDEX_HTML: str | None = None
_DEFAULT_SOVEREIGN_FONT_SANS_CSS_URL = "https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&display=swap"
_DEFAULT_SOVEREIGN_FONT_MONO_CSS_URL = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap"


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


def _sovereign_fonts_css() -> str:
    source = (os.getenv("SOVEREIGN_FONT_SOURCE", "google") or "google").strip().lower()
    if source == "off":
        return "/* Sovereign fonts disabled via SOVEREIGN_FONT_SOURCE=off */\n"

    is_local = source == "local"
    sans_url = (
        os.getenv("SOVEREIGN_FONT_SANS_CSS_URL_LOCAL")
        if is_local
        else os.getenv("SOVEREIGN_FONT_SANS_CSS_URL")
    ) or _DEFAULT_SOVEREIGN_FONT_SANS_CSS_URL
    mono_url = (
        os.getenv("SOVEREIGN_FONT_MONO_CSS_URL_LOCAL")
        if is_local
        else os.getenv("SOVEREIGN_FONT_MONO_CSS_URL")
    ) or _DEFAULT_SOVEREIGN_FONT_MONO_CSS_URL
    return "\n".join(
        [
            "/* Generated from environment: /sovereign-fonts.css */",
            f"@import url('{sans_url}');",
            f"@import url('{mono_url}');",
            "",
        ]
    )


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


@router.get("/sovereign-fonts.css", include_in_schema=False)
def sovereign_fonts_css() -> PlainTextResponse:
    """Serve env-configurable sovereign font CSS imports."""
    return PlainTextResponse(
        _sovereign_fonts_css(),
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=300"},
    )

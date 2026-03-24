"""Static web UI routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"])

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
_INDEX_FILE = _UI_DIR / "index.html"


@router.get("/", include_in_schema=False)
def web_app_shell() -> FileResponse:
    """Serve the main web UI shell."""
    return FileResponse(_INDEX_FILE)

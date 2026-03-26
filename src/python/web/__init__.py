"""Web application package for Bitcoin Accounting."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from web.config import WebConfig


def create_app(config: "WebConfig | None" = None) -> "FastAPI":
    """Lazy import wrapper so service tests do not require FastAPI at import time."""
    from .app import create_app as _create_app

    return _create_app(config)


__all__ = ["create_app"]

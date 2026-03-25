"""API route modules."""

from .auth import router as auth_router
from .health import router as health_router
from .ledger import router as ledger_router
from .portfolio import router as portfolio_router
from .tax import router as tax_router
from .ui import router as ui_router
from .wallets import router as wallets_router

__all__ = ["auth_router", "health_router", "ledger_router", "portfolio_router", "tax_router", "ui_router", "wallets_router"]

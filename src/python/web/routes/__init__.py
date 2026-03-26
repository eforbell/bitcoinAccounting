"""API route modules."""

from .auth import router as auth_router
from .chain import router as chain_router
from .health import router as health_router
from .imports import router as imports_router
from .ledger import router as ledger_router
from .portfolio import router as portfolio_router
from .tax import router as tax_router
from .trades import router as trades_router
from .ui import router as ui_router
from .verification import router as verification_router
from .wallets import router as wallets_router

__all__ = ["auth_router", "chain_router", "health_router", "imports_router", "ledger_router", "portfolio_router", "tax_router", "trades_router", "ui_router", "verification_router", "wallets_router"]

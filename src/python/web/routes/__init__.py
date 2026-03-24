"""API route modules."""

from .auth import router as auth_router
from .health import router as health_router
from .tax import router as tax_router

__all__ = ["auth_router", "health_router", "tax_router"]

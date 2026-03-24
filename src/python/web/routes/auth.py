"""Private auth/session routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from web.auth import (
    AuthConfigurationError,
    SessionPrincipal,
    clear_session_cookie,
    create_session_token,
    require_auth_config,
    require_authenticated_principal,
    set_session_cookie,
    verify_auth_passphrase,
)
from web.config import WebConfig
from web.models import LoginRequest, SessionResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _config(request: Request) -> WebConfig:
    return request.app.state.web_config


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
    """Authenticate the private operator and issue a signed session cookie."""
    config = _config(request)
    try:
        require_auth_config(config)
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not verify_auth_passphrase(payload.passphrase, config):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_session_token(config, username="operator")
    set_session_cookie(response, token, config)
    return SessionResponse(authenticated=True, username="operator")


@router.post("/logout", response_model=SessionResponse)
def logout(request: Request, response: Response) -> SessionResponse:
    """Clear the current session cookie."""
    config = _config(request)
    clear_session_cookie(response, config)
    return SessionResponse(authenticated=False, username="operator")


@router.get("/me", response_model=SessionResponse)
def me(principal: SessionPrincipal = Depends(require_authenticated_principal)) -> SessionResponse:
    """Return the current authenticated principal."""
    return SessionResponse(authenticated=True, username=principal.username)

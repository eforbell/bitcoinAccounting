"""Private single-operator auth helpers for the web app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status

from web.config import WebConfig


class AuthConfigurationError(RuntimeError):
    """Raised when auth is enabled but missing required config."""


@dataclass(frozen=True)
class SessionPrincipal:
    """Authenticated principal carried by signed cookie sessions."""

    username: str
    authenticated: bool = True


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return digest


def _require_auth_secret(config: WebConfig) -> str:
    if not config.session_secret:
        raise AuthConfigurationError(
            "BITCOIN_ACCOUNTING_SESSION_SECRET must be set when auth is enabled"
        )
    return config.session_secret


def verify_auth_passphrase(candidate: str, config: WebConfig) -> bool:
    """Compare auth passphrases using a timing-safe check."""
    if config.auth_passphrase is None:
        return False
    return hmac.compare_digest(candidate.encode(), config.auth_passphrase.encode())


def session_cookie_secure(config: WebConfig) -> bool:
    """Return whether the session cookie should be marked secure."""
    if config.session_cookie_secure is not None:
        return config.session_cookie_secure
    return config.app_env.lower() in {"production", "prod"}


def require_auth_config(config: WebConfig) -> None:
    """Validate auth configuration when auth is enabled."""
    if not config.auth_enabled:
        return
    if not config.auth_passphrase:
        raise AuthConfigurationError(
            "BITCOIN_ACCOUNTING_AUTH_PASSPHRASE must be set when auth is enabled"
        )
    _require_auth_secret(config)


def create_session_token(config: WebConfig, username: str = "operator") -> str:
    """Create a signed session token."""
    secret = _require_auth_secret(config)
    payload = {
        "sub": username,
        "iat": int(time.time()),
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(payload_b64, secret)
    return f"{payload_b64}.{signature}"


def verify_session_token(token: str, config: WebConfig) -> SessionPrincipal | None:
    """Verify a signed session token and return principal if valid."""
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None

    try:
        secret = _require_auth_secret(config)
    except AuthConfigurationError:
        return None

    expected = _sign(payload_b64, secret)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None

    issued_at = int(payload.get("iat", 0))
    if issued_at <= 0:
        return None
    if int(time.time()) - issued_at > config.session_ttl_seconds:
        return None

    subject = str(payload.get("sub", "")).strip()
    if not subject:
        return None
    return SessionPrincipal(username=subject)


def get_current_principal(request: Request) -> SessionPrincipal | None:
    """Read current principal from request cookie or dev-mode bypass."""
    config: WebConfig = request.app.state.web_config
    if not config.auth_enabled:
        return SessionPrincipal(username="operator")

    cookie = request.cookies.get(config.session_cookie_name)
    if not cookie:
        return None
    return verify_session_token(cookie, config)


def require_authenticated_principal(request: Request) -> SessionPrincipal:
    """Require an authenticated principal for protected endpoints."""
    principal = get_current_principal(request)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return principal


def set_session_cookie(response: Response, token: str, config: WebConfig) -> None:
    """Attach the session cookie to a response."""
    response.set_cookie(
        key=config.session_cookie_name,
        value=token,
        httponly=True,
        samesite="strict",
        secure=session_cookie_secure(config),
        max_age=config.session_ttl_seconds,
        path="/",
    )


def clear_session_cookie(response: Response, config: WebConfig) -> None:
    """Clear the session cookie from a response."""
    response.delete_cookie(config.session_cookie_name, path="/")

"""Suite identity (Home Base Feature-10): who is asking, in tailnet mode.

SOVEREIGN_AUTH_MODE picks how Bitcoin Accounting knows who is asking. 'local' is its own passphrase and session
cookie (web/auth.py). 'tailnet' is the household member nginx names in the identity headers, looked up in the
directory snapshot Home Base publishes. Home Base writes the mode when it switches the app over; an install from
before that has none, which means local.

Bitcoin Accounting has one operator and no table of people, so there is nothing to link: any parent Home Base has
given it to may use it, and kids never. The directory decides both, on every request.

In tailnet mode SuiteIdentityMiddleware runs before anything reads the request:
  1. the request guard (wire contract, section 4): resource isolation, because the app has its own hostname, and
     the write check (exact Origin; JSON, or a form upload on the import route that takes a file). It reads only
     the method and headers;
  2. the member gate: a parent with access to Bitcoin Accounting, or a page a person can act on.
Only Home Base's health and readiness probes pass without either, and the page assets without a member.
"""
from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sovereign_auth import (
    GuardMiddleware,
    Identity,
    auth_mode,
    create_identity,
    create_request_guard,
    create_snapshot_reader,
    headers_from_scope,
    normalize_origin,
)

APP_ID = "bitcoin-accounting"
NAME = "Bitcoin Accounting"
log = logging.getLogger("web.suite_identity")

# Home Base's liveness and readiness probes (catalog: livenessPath and readinessPath). They come over the socket
# through the executor, with no identity headers and no fetch metadata.
OPEN_PATHS = frozenset({"/api/health", "/api/ready"})
# The page's own files, never data: reads only, these types, in static/ or one of its two folders, and the font
# stylesheet the page links. A page with data in it is not an asset.
ASSET_PATH = re.compile(
    r"/static/(?:brand/|vendor/)?[\w.-]+\.(?:css|js|svg|ico|png|woff2?)|/sovereign-fonts\.css", re.ASCII
)
# The one route that takes a file: an exchange or wallet CSV, sent as a form upload. Every other write is JSON only,
# which keeps forms out. The upload still needs this hostname's exact Origin.
UPLOAD_PATH = "/api/import/parse"
UPLOAD_TYPES = ("application/json", "multipart/form-data")
_API_PATH = re.compile(r"/api(?:/|$)", re.IGNORECASE)
_UID = re.compile(r"[1-9][0-9]{0,9}", re.ASCII)
# Plain path segments only (and no dot segments), so a path built on it stays on this host and under the mount.
_PLAIN_PATH = re.compile(r"/(?:[A-Za-z0-9._~-]+/)*(?:[A-Za-z0-9._~-]+)?", re.ASCII)


def route_path(scope) -> str:
    """The path Starlette routes on: the request path less root_path (Home Base's /bitcoin-accounting mount),
    exactly as starlette._utils.get_route_path computes it. Every check here looks at the path the router will
    use."""
    path = scope.get("path") or "/"
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        if path == root:
            return "/"
        if path[len(root)] == "/":
            return path[len(root):]
    return path


def is_api_path(path: str) -> bool:
    """Any spelling of /api: a check that refuses has to see every one (Starlette routes are case-sensitive
    today, but a refusal shouldn't depend on that)."""
    return bool(_API_PATH.match(path))


def home_base_uid(value: Any) -> int:
    """SOVEREIGN_HOMEBASE_UID: the owner Home Base gives its directory snapshot. Never root."""
    text = str(value if value is not None else "").strip()
    uid = int(text) if _UID.fullmatch(text) else -1
    if not 0 < uid < 4294967295:
        raise ValueError(f"SOVEREIGN_HOMEBASE_UID must be the Home Base user's uid, not '{text}'")
    return uid


def public_address(value: Any) -> tuple[str, str]:
    """APP_PUBLIC_URL, the address Home Base publishes the app at: every write's Origin must be its origin, and the
    pages live under its path (/bitcoin-accounting/)."""
    text = str(value if value is not None else "")
    try:
        parts = urlsplit(text)
        origin = normalize_origin(f"https://{parts.netloc}") if parts.scheme.lower() == "https" else ""
    except ValueError:
        parts, origin = None, ""
    if not origin:
        raise ValueError(f"tailnet mode needs APP_PUBLIC_URL, {NAME}'s https address, not '{text}'")
    path = parts.path or "/"
    dot_segment = any(segment in (".", "..") for segment in path.split("/"))
    if "?" in text or "#" in text or dot_segment or not _PLAIN_PATH.fullmatch(path):
        raise ValueError(f"APP_PUBLIC_URL must have a plain path such as /bitcoin-accounting/, not '{path}'")
    return origin, path if path.endswith("/") else f"{path}/"


@dataclass(frozen=True)
class Refusal:
    status: int
    title: str
    text: str


REFUSALS = {
    "directory": Refusal(
        503,
        f"{NAME} can't check who you are right now",
        "It couldn't read the household directory from Home Base. Try again in a minute, and if this keeps "
        "happening, tell whoever runs Home Base.",
    ),
    "not_member": Refusal(
        403,
        f"{NAME} doesn't know you yet",
        f"Ask whoever runs Home Base to give you access to {NAME}.",
    ),
    "parents_only": Refusal(
        403,
        f"{NAME} is for parents",
        f"{NAME} keeps the household's bitcoin records and taxes, so only parents can open it.",
    ),
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bitcoin Accounting</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px; box-sizing: border-box;
    font: 16px/1.5 system-ui, -apple-system, sans-serif; background: #12100c; color: #f2ede4; }}
  main {{ max-width: 28rem; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .5rem; }}
  p {{ margin: 0; color: #a99f8f; }}
{style}</style>
</head>
<body>{body}</body>
</html>
"""


def refusal_page(refusal: Refusal, name: str | None = None) -> str:
    title = f"{refusal.title}, {name}" if name else refusal.title
    return _PAGE.format(style="", body=f"<main><h1>{html.escape(title)}</h1><p>{html.escape(refusal.text)}</p></main>")


async def _send(send, status: int, body: bytes, content_type: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", content_type.encode("latin-1")),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class SuiteIdentity:
    """create_suite_identity(env) checks the configuration once, at startup. An unknown mode, or tailnet mode off
    the app's socket, without Home Base's uid or without a plain https APP_PUBLIC_URL, refuses to start: an app
    that starts open on a typo is the worst outcome."""

    def __init__(self, env: Mapping[str, str], *, reader: Any = None):
        # Unset means local, for installs from before the switch existed. Anything but local or tailnet throws.
        mode = auth_mode(env.get("SOVEREIGN_AUTH_MODE", "local"))
        self.tailnet = mode == "tailnet"
        if self.tailnet and reader is None:
            reader = create_snapshot_reader(home_base_uid=home_base_uid(env.get("SOVEREIGN_HOMEBASE_UID")))
        self.reader = reader if self.tailnet else None
        self.identity: Identity = create_identity(
            app_id=APP_ID, mode=mode, listen=env.get("SOVEREIGN_LISTEN"), reader=self.reader
        )
        self.origin = self.base_path = self.hostname = None
        self.guard = self.upload_guard = None
        if self.tailnet:
            self.origin, self.base_path = public_address(env.get("APP_PUBLIC_URL"))
            self.hostname = urlsplit(self.origin).hostname
            # The passkey cookie names a hostname, not a port, and Home Base publishes on 443.
            if self.origin != f"https://{self.hostname}":
                raise ValueError(f"APP_PUBLIC_URL must be on the default https port, not '{self.origin}'")
            # Its own hostname: isolation and the write check.
            self.guard = create_request_guard(self.origin)
            self.upload_guard = create_request_guard(self.origin, content_types=UPLOAD_TYPES)


def create_suite_identity(env: Mapping[str, str], *, reader: Any = None) -> SuiteIdentity:
    return SuiteIdentity(env, reader=reader)


def suite_of(request) -> SuiteIdentity | None:
    """The app's SuiteIdentity (create_app keeps it on app.state)."""
    return getattr(request.app.state, "suite", None)


def in_tailnet_mode(request) -> bool:
    """Tailnet mode: Home Base's directory decides who may use the app, and the local passphrase sign-in is off.
    The passphrase and session secret stay configured, so returning to local mode needs nothing else."""
    suite = suite_of(request)
    return bool(suite and suite.tailnet)


def suite_member(request):
    """The member the gate admitted, in tailnet mode; None otherwise."""
    return request.scope.get("state", {}).get("suite_member")


class SuiteIdentityMiddleware:
    """The guard, then the member gate, in tailnet mode; nothing at all in local mode."""

    def __init__(self, app, *, suite: SuiteIdentity):
        self.app = app
        self.suite = suite
        if suite.tailnet:
            self._guarded = GuardMiddleware(self._gate, guard=suite.guard, mode="enforce", log=log.warning)
            self._upload = GuardMiddleware(self._gate, guard=suite.upload_guard, mode="enforce", log=log.warning)

    async def __call__(self, scope, receive, send):
        path = route_path(scope)
        if scope.get("type") != "http" or not self.suite.tailnet or path in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        guarded = self._upload if path == UPLOAD_PATH else self._guarded
        await guarded(scope, receive, send)

    async def _gate(self, scope, receive, send):
        path = route_path(scope)
        method = scope.get("method", "GET")
        if method in ("GET", "HEAD") and ASSET_PATH.fullmatch(path):
            await self.app(scope, receive, send)
            return
        headers = headers_from_scope(scope)
        api = is_api_path(path)
        # The JSON API is for the app's own pages. A sibling hostname can navigate here with the member's identity
        # (a link, <a target>), so no API route answers a navigation.
        if api and headers.get("sec-fetch-mode") == "navigate":
            body = {"detail": f"This address is only for {NAME}'s own pages.", "code": "not_a_page"}
            await _send(send, 403, json.dumps(body).encode("utf-8"), "application/json")
            return
        resolution = self.suite.identity.identify(headers)
        member = resolution.member
        if member is None:
            code = "directory" if resolution.reason == "no_snapshot" else "not_member"
            if code == "directory":
                log.warning("suite identity: no directory snapshot (%s)", resolution.snapshot_reason)
            await self._refuse(send, code, api)
            return
        if member.role != "parent":
            await self._refuse(send, "parents_only", api, member.name)
            return
        scope.setdefault("state", {})["suite_member"] = member
        await self.app(scope, receive, send)

    async def _refuse(self, send, code: str, api: bool, name: str | None = None) -> None:
        refusal = REFUSALS[code]
        if api:
            body = json.dumps({"detail": refusal.title, "code": code}).encode("utf-8")
            await _send(send, refusal.status, body, "application/json")
        else:
            await _send(send, refusal.status, refusal_page(refusal, name).encode("utf-8"), "text/html; charset=utf-8")

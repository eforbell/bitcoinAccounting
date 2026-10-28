"""Where the web server listens (Home Base Feature-10 SID-002).

Under Home Base, SOVEREIGN_LISTEN=unix:<path> names a socket in a directory only this app's user and
nginx can enter, so nothing else on the host or the tailnet can reach the app around nginx. Without it,
the server listens on --host/--port (loopback by default).
"""

from __future__ import annotations

import os
import re
import socket
import stat
from collections.abc import Mapping
from dataclasses import dataclass

_UNIX = re.compile(r"^unix:(/[^\0]+\.sock)$")


@dataclass(frozen=True)
class ListenTarget:
    socket_path: str | None = None
    host: str | None = None
    port: int | None = None


def listen_target(env: Mapping[str, str], *, host: str, port: int) -> ListenTarget:
    value = (env.get("SOVEREIGN_LISTEN") or "").strip()
    if not value:
        return ListenTarget(host=host, port=port)
    match = _UNIX.match(value)
    if not match:
        raise ValueError(f"SOVEREIGN_LISTEN must look like unix:/path/app.sock, not {value}")
    return ListenTarget(socket_path=match.group(1))


def bind_unix_socket(path: str) -> socket.socket:
    """Bind the socket, replacing one left by a crash (only a socket: any other file is an error), and
    make it reachable by nginx's group (the directory decides who else)."""
    try:
        if not stat.S_ISSOCK(os.lstat(path).st_mode):
            raise RuntimeError(f"{path} exists and is not a socket")
        os.unlink(path)
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(path)
        os.chmod(path, 0o660)
    except BaseException:
        sock.close()
        raise
    return sock

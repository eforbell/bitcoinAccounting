"""Home Base socket listening (Feature-10 SID-002)."""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from web.app import create_app
from web.config import WebConfig
from web.listen import ListenTarget, bind_unix_socket, listen_target
from web.server import main


@pytest.fixture
def short_dir():
    """Socket paths are capped near 104 bytes (macOS); pytest's tmp_path can be longer."""
    path = Path(tempfile.mkdtemp(prefix="btc-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _get(path: str, url: str) -> bytes:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(path)
    client.sendall(f"GET {url} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
    reply = b""
    while chunk := client.recv(65536):
        reply += chunk
    client.close()
    return reply


def test_host_and_port_by_default_and_the_socket_when_home_base_names_one() -> None:
    assert listen_target({}, host="127.0.0.1", port=3010) == ListenTarget(host="127.0.0.1", port=3010)
    assert listen_target({"SOVEREIGN_LISTEN": "unix:/run/sovereign-apps/bitcoin-accounting/app.sock"}, host="127.0.0.1", port=3010) == ListenTarget(socket_path="/run/sovereign-apps/bitcoin-accounting/app.sock")
    for bad in ["tcp:0.0.0.0:3010", "unix:relative.sock", "unix:/run/x/app", "/run/x/app.sock"]:
        with pytest.raises(ValueError, match="must look like unix:"):
            listen_target({"SOVEREIGN_LISTEN": bad}, host="127.0.0.1", port=3010)


def test_the_socket_is_0660_replaces_a_stale_one_and_never_another_file(short_dir: Path) -> None:
    path = str(short_dir / "app.sock")
    # A crash (SIGKILL) leaves its socket behind.
    crashed = subprocess.Popen([sys.executable, "-c", f"import socket,time; s=socket.socket(socket.AF_UNIX); s.bind({path!r}); s.listen(); print('up', flush=True); time.sleep(60)"], stdout=subprocess.PIPE, text=True)
    assert crashed.stdout is not None and crashed.stdout.readline().strip() == "up"
    crashed.kill()
    crashed.wait()
    assert stat.S_ISSOCK(os.lstat(path).st_mode)
    sock = bind_unix_socket(path)
    try:
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o660
    finally:
        sock.close()
    other = short_dir / "file.sock"
    other.write_text("data")
    with pytest.raises(RuntimeError, match="exists and is not a socket"):
        bind_unix_socket(str(other))
    assert other.read_text() == "data"


def test_the_socket_comes_from_the_checkouts_env_file_and_reload_is_refused_with_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Home Base's units have no EnvironmentFile=: the launcher reads .env itself, before choosing where to listen."""
    import web.server

    env_file = tmp_path / ".env"
    env_file.write_text("SOVEREIGN_LISTEN=unix:/run/sovereign-apps/bitcoin-accounting/app.sock\n")
    monkeypatch.setattr(web.server, "ENV_FILE", env_file)
    monkeypatch.delenv("SOVEREIGN_LISTEN", raising=False)
    with pytest.raises(SystemExit):
        main(["--reload"])
    assert os.environ["SOVEREIGN_LISTEN"] == "unix:/run/sovereign-apps/bitcoin-accounting/app.sock"
    monkeypatch.delenv("SOVEREIGN_LISTEN")


def test_the_app_serves_its_mount_path_unchanged_over_the_socket(short_dir: Path) -> None:
    """nginx passes /bitcoin-accounting/... through unchanged (mount-preserving); FastAPI's root_path routes it."""
    app = create_app(config=WebConfig(web_base_path="/bitcoin-accounting"))
    path = str(short_dir / "app.sock")
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [bind_unix_socket(path)]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert _get(path, "/bitcoin-accounting/api/health").startswith(b"HTTP/1.1 200")
        assert _get(path, "/bitcoin-accounting/static/app.css").startswith(b"HTTP/1.1 200")
        page = _get(path, "/bitcoin-accounting/")
        assert page.startswith(b"HTTP/1.1 200") and b'src="static/app.js"' in page
    finally:
        server.should_exit = True
        thread.join(timeout=5)

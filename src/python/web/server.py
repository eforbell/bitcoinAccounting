"""Local launcher for the FastAPI web app."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from web.listen import bind_unix_socket, listen_target

# The checkout's .env, as db/__init__.py loads it. Read here too: where to listen (SOVEREIGN_LISTEN) is
# decided before uvicorn imports the app. Variables already in the environment win.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _load_env(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=path, override=False)


def build_parser() -> argparse.ArgumentParser:
    """Build the local web-server CLI parser."""
    parser = argparse.ArgumentParser(
        prog="bitcoin-accounting-web",
        description="Run the Bitcoin Accounting web app with uvicorn.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for the local web server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3010,
        help="Bind port for the local web server (default: 3010).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload for local development.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level (default: info).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the FastAPI app via uvicorn: on Home Base's socket when SOVEREIGN_LISTEN names one, else host:port."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _load_env(ENV_FILE)
    target = listen_target(os.environ, host=args.host, port=args.port)
    if target.socket_path:
        if args.reload:
            parser.error("--reload cannot be used with SOVEREIGN_LISTEN: the reloader's worker could not inherit the socket.")
        config = uvicorn.Config("web.app:create_app", factory=True, log_level=args.log_level)
        uvicorn.Server(config).run(sockets=[bind_unix_socket(target.socket_path)])
        return 0
    uvicorn.run(
        "web.app:create_app",
        factory=True,
        host=target.host,
        port=target.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

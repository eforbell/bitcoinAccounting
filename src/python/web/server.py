"""Local launcher for the FastAPI web app."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn


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
    """Launch the FastAPI app via uvicorn."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    uvicorn.run(
        "web.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

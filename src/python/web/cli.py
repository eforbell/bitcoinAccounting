"""Operational CLI helpers for the web service."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from web.config import WebConfigurationError
from web.startup import initialize_web_runtime


def build_parser() -> argparse.ArgumentParser:
    """Build the web operations CLI parser."""
    parser = argparse.ArgumentParser(
        prog="bitcoin-accounting-web-init",
        description="Validate web runtime configuration and initialize runtime schema.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the web initialization command."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = initialize_web_runtime()
    except (WebConfigurationError, Exception) as exc:
        if args.json:
            print(json.dumps({"status": "error", "detail": str(exc)}))
        else:
            print(f"Web init failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(result))
    else:
        print(
            "Web runtime ready: "
            f"backend={result['database_backend']} "
            f"base_path={result['base_path'] or '/'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

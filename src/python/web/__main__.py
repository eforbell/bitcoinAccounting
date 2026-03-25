"""Module launcher for `python -m web`."""

from __future__ import annotations

from web.server import main


if __name__ == "__main__":
    raise SystemExit(main())

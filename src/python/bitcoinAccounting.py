"""Packaged entrypoint for launching the Bitcoin Accounting TUI."""

from __future__ import annotations

from pathlib import Path


def _load_env() -> None:
    """Load a local .env file when present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Favor project-local execution: load .env from the current working directory.
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def main() -> None:
    """Launch the Textual TUI application."""
    _load_env()
    from tui.app import main as tui_main

    tui_main()


if __name__ == "__main__":
    main()

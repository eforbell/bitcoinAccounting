"""Top-level module entrypoint for launching the Crypto Accounting TUI.

Run with:
    python -m cryptoAccounting
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap() -> None:
    """Configure import path and environment for module execution."""
    repo_root = Path(__file__).resolve().parent
    module_root = repo_root / "src" / "python"
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=repo_root / ".env", override=False)
    except ImportError:
        # Optional dependency; environment variables may already be set.
        pass


def main() -> None:
    """Launch the Textual TUI application."""
    _bootstrap()
    from tui.app import main as tui_main

    tui_main()


if __name__ == "__main__":
    main()

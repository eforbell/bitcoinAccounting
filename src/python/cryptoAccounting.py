"""Legacy compatibility entrypoint for launching the Bitcoin Accounting TUI."""

from __future__ import annotations

import warnings

from bitcoinAccounting import main as _bitcoin_main


def main() -> None:
    warnings.warn(
        "`cryptoAccounting` is deprecated; use `bitcoinAccounting` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _bitcoin_main()


if __name__ == "__main__":
    main()

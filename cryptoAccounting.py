"""Legacy top-level module entrypoint for Bitcoin Accounting.

Run with:
    python -m cryptoAccounting
"""

from __future__ import annotations

import warnings

from bitcoinAccounting import main as _bitcoin_main


def main() -> None:
    warnings.warn(
        "`python -m cryptoAccounting` is deprecated; use `python -m bitcoinAccounting`.",
        DeprecationWarning,
        stacklevel=2,
    )
    _bitcoin_main()


if __name__ == "__main__":
    main()

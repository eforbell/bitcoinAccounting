"""Wallet-specific import parsers.

Each parser module in this package registers itself with the registry
when imported. The imports here ensure all parsers are loaded.
"""

# Import parsers to trigger registration
# Parsers will be added here as they are implemented:
from . import ledger  # noqa: F401
from . import trezor  # noqa: F401
# from . import sparrow
# from . import coldcard

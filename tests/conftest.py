import sys
import os
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))


DEFAULT_PARSER_MODULES = [
    "imports.exchanges.native",
    "imports.exchanges.coinbase",
    "imports.exchanges.coinbase_pro",
    "imports.exchanges.kraken",
    "imports.exchanges.strike",
    "imports.exchanges.river",
    "imports.exchanges.swan",
    "imports.exchanges.cashapp",
    "imports.exchanges.gemini",
    "imports.wallets.ledger",
    "imports.wallets.trezor",
    "imports.wallets.sparrow",
    "imports.wallets.coldcard",
]


def restore_default_parsers() -> None:
    """Restore default parser registrations if the global registry is empty.

    Some tests call clear_registry() and leave process-global parser state empty.
    This helper reloads parser modules so their @register decorators run again.
    """
    from imports.registry import get_parser_names

    if get_parser_names():
        return

    for module_name in DEFAULT_PARSER_MODULES:
        module = importlib.import_module(module_name)
        importlib.reload(module)

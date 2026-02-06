"""Import parsers for CSV transaction imports.

This package provides parsers for importing transaction data from various
exchanges, wallets, and native formats.

Usage:
    from imports import get_parser, get_all_parsers, detect_parser

    # Get a specific parser
    parser = get_parser('coinbase')
    colnames, transactions = parser.parse('coinbase_export.csv')

    # Auto-detect parser from file
    parser = detect_parser('unknown_file.csv')
    if parser:
        colnames, transactions = parser.parse('unknown_file.csv')

    # List all available parsers
    for parser in get_all_parsers():
        print(f"{parser.name}: {parser.description}")
"""

from .base import BaseImporter, FIAT_CURRENCIES, is_fiat
from .registry import (
    register,
    get_parser,
    get_all_parsers,
    detect_parser,
    get_parser_names,
    clear_registry,
)
from .validation import (
    ValidationResult,
    validate_transaction,
    validate_batch,
    detect_duplicates,
    get_transaction_warnings,
)

__all__ = [
    "BaseImporter",
    "FIAT_CURRENCIES",
    "is_fiat",
    "register",
    "get_parser",
    "get_all_parsers",
    "detect_parser",
    "get_parser_names",
    "clear_registry",
    "ValidationResult",
    "validate_transaction",
    "validate_batch",
    "detect_duplicates",
    "get_transaction_warnings",
]

# Import exchange and wallet parsers to trigger registration
# This must come after the registry is defined
from . import exchanges  # noqa: F401, E402
from . import wallets  # noqa: F401, E402

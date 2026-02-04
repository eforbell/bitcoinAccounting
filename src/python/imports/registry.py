"""Parser registry for import parsers.

This module provides a registry pattern for discovering and accessing import parsers.
Parsers register themselves using the @register decorator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseImporter

# Module-level registry mapping parser names to classes
_REGISTRY: dict[str, type[BaseImporter]] = {}


def register(cls: type[BaseImporter]) -> type[BaseImporter]:
    """Decorator to register an importer class.

    Usage:
        @register
        class CoinbaseImporter(BaseImporter):
            name = "Coinbase"
            ...

    Args:
        cls: The importer class to register

    Returns:
        The same class (unmodified)

    Raises:
        ValueError: If a parser with the same name is already registered
    """
    name = cls.name.lower()
    if name in _REGISTRY:
        raise ValueError(f"Parser '{cls.name}' is already registered")
    _REGISTRY[name] = cls
    return cls


def get_parser(name: str) -> BaseImporter | None:
    """Get a parser instance by name.

    Args:
        name: Parser name (case-insensitive)

    Returns:
        An instance of the parser, or None if not found
    """
    cls = _REGISTRY.get(name.lower())
    if cls is None:
        return None
    return cls()


def get_all_parsers() -> list[BaseImporter]:
    """Get instances of all registered parsers.

    Returns:
        List of parser instances, sorted by name
    """
    return [cls() for cls in sorted(_REGISTRY.values(), key=lambda c: c.name)]


def detect_parser(file_path: str) -> BaseImporter | None:
    """Auto-detect which parser can handle a file.

    Iterates through all registered parsers and returns the first one
    that claims it can handle the file.

    Args:
        file_path: Path to the CSV file to check

    Returns:
        A parser instance that can handle the file, or None if no match
    """
    for parser in get_all_parsers():
        if parser.detect(file_path):
            return parser
    return None


def get_parser_names() -> list[str]:
    """Get list of all registered parser names.

    Returns:
        List of parser names (lowercase), sorted alphabetically
    """
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    """Clear all registered parsers (for testing).

    Warning: Only use in tests. Production code should not call this.
    """
    _REGISTRY.clear()

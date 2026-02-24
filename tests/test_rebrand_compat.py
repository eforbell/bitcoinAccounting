"""Canonical module import tests for bitcoin naming."""

import importlib
import os
import sys
from pathlib import Path
import tomllib

import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))


def test_bitcoin_accounts_alias() -> None:
    from bitcoinAccounts import BitcoinAccounts, CryptoAccounts

    assert CryptoAccounts is BitcoinAccounts


def test_canonical_module_exports_both_class_names() -> None:
    from bitcoinAccounts import BitcoinAccounts, CryptoAccounts

    assert CryptoAccounts is BitcoinAccounts


def test_canonical_entrypoint_exports_main() -> None:
    from bitcoinAccounting import main as bitcoin_main

    assert callable(bitcoin_main)


def test_legacy_modules_are_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("cryptoAccounts")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("cryptoAccounting")


def test_pyproject_has_only_canonical_console_script_and_modules() -> None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    scripts = data["project"]["scripts"]
    assert "bitcoin-accounting" in scripts
    assert "crypto-accounting" not in scripts
    assert "crypto-tui" not in scripts

    py_modules = data["tool"]["setuptools"]["py-modules"]
    assert "bitcoinAccounts" in py_modules
    assert "bitcoinAccounting" in py_modules
    assert "cryptoAccounts" not in py_modules
    assert "cryptoAccounting" not in py_modules

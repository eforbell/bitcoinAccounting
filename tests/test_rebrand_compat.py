"""Compatibility tests for bitcoin*/crypto* module migration."""

import os
import sys

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))


def test_bitcoin_accounts_alias() -> None:
    from bitcoinAccounts import BitcoinAccounts, CryptoAccounts

    assert CryptoAccounts is BitcoinAccounts


def test_legacy_cryptoaccounts_shim_points_to_canonical() -> None:
    import cryptoAccounts
    from bitcoinAccounts import BitcoinAccounts

    assert cryptoAccounts.CryptoAccounts is BitcoinAccounts
    assert cryptoAccounts.BitcoinAccounts is BitcoinAccounts


def test_canonical_and_legacy_entrypoints_export_main() -> None:
    from bitcoinAccounting import main as bitcoin_main
    from cryptoAccounting import main as crypto_main

    assert callable(bitcoin_main)
    assert callable(crypto_main)

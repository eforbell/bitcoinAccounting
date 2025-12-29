"""Bootstrap module path for cryptoAccounting scripts.

This module automatically adds src/python to sys.path so scripts
can import cryptoAccounting modules without manual path manipulation
or environment variables.

Usage in scripts:
    import _bootstrap
    from cryptoAccounts import CryptoAccounts
"""
import sys
from pathlib import Path

# Find src/python relative to this script's location
script_dir = Path(__file__).resolve().parent
module_root = script_dir.parent / "python"

if str(module_root) not in sys.path:
    sys.path.insert(0, str(module_root))

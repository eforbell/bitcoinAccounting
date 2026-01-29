"""Bootstrap module path for cryptoAccounting scripts.

This module automatically adds src/python to sys.path so scripts
can import cryptoAccounting modules without manual path manipulation
or environment variables.

Also loads environment variables from .env file in repository root.

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

# Load environment variables from .env file in repository root
try:
    from dotenv import load_dotenv
    repo_root = script_dir.parent.parent  # src/scripts -> src -> repo_root
    dotenv_path = repo_root / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
except ImportError:
    # python-dotenv not installed - environment variables must be set manually
    pass

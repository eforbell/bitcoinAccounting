# Scripts Deployment Guide

This document explains how the scripts in `src/scripts/` establish the Python module root and how to deploy them to your system.

## Current Setup

The scripts in `src/scripts/` use bare imports like:
```python
from cryptoAccounts import CryptoAccounts
```

This works when the Python module root (`src/python/`) is in your `PYTHONPATH`.

## Recommended Deployment Options

### Option 1: Set REPO_ROOT Environment Variable (Recommended)

Set an environment variable pointing to the repository root. The scripts will automatically add `src/python/` to the path.

**On Linux/macOS:**
```bash
export REPO_ROOT=/path/to/cryptoAccounting
export PATH="$PATH:$HOME/bin"

# Then create symlinks in ~/bin:
ln -s /path/to/cryptoAccounting/src/scripts/balance ~/bin/balance
ln -s /path/to/cryptoAccounting/src/scripts/transfer ~/bin/transfer
# etc.

chmod +x ~/bin/balance ~/bin/transfer  # Make executable
```

**In your shell profile (~/.bashrc, ~/.zshrc, etc.):**
```bash
export REPO_ROOT=/path/to/cryptoAccounting
export PATH="$HOME/bin:$PATH"
```

**On Windows (PowerShell):**
```powershell
[Environment]::SetEnvironmentVariable("REPO_ROOT", "D:\path\to\cryptoAccounting", "User")
```

### Option 2: Set CRYPTO_ACCOUNTING_PYTHONPATH Directly

Explicitly set the path to the Python module directory.

**On Linux/macOS:**
```bash
export CRYPTO_ACCOUNTING_PYTHONPATH=/path/to/cryptoAccounting/src/python
```

**In ~/.bashrc or ~/.zshrc:**
```bash
export CRYPTO_ACCOUNTING_PYTHONPATH=$HOME/workspace/cryptoAccounting/src/python
```

### Option 3: Add to PYTHONPATH

Add the module root to Python's path search.

**On Linux/macOS:**
```bash
export PYTHONPATH="/path/to/cryptoAccounting/src/python:$PYTHONPATH"
```

**In ~/.bashrc or ~/.zshrc:**
```bash
export PYTHONPATH="$HOME/workspace/cryptoAccounting/src/python:$PYTHONPATH"
```

### Option 4: Use a Wrapper Script

Create a simple wrapper shell script that sets the paths before calling the Python script.

**Example `~/bin/balance`:**
```bash
#!/bin/bash
export REPO_ROOT=/path/to/cryptoAccounting
exec python3 /path/to/cryptoAccounting/src/scripts/balance "$@"
```

Then make it executable:
```bash
chmod +x ~/bin/balance
```

## Updated Script Template

For new scripts or when refactoring existing ones, use the improved pattern shown in `balance.example`:

```python
#!/usr/bin/env python3

import sys
import os

# Try environment variables first
module_root = os.getenv('CRYPTO_ACCOUNTING_PYTHONPATH')
if not module_root:
    repo_root = os.getenv('REPO_ROOT')
    if repo_root:
        module_root = os.path.join(repo_root, 'src', 'python')

if module_root and module_root not in sys.path:
    sys.path.insert(0, module_root)

try:
    from cryptoAccounts import CryptoAccounts
except ImportError as e:
    print(f"ERROR: Could not import cryptoAccounts. Please set REPO_ROOT or CRYPTO_ACCOUNTING_PYTHONPATH", file=sys.stderr)
    sys.exit(1)
```

## Quick Setup (Linux/macOS)

1. **Clone or locate the repo:**
   ```bash
   cd ~/workspace/cryptoAccounting
   ```

2. **Add to shell profile** (~/.bashrc, ~/.bash_profile, or ~/.zshrc):
   ```bash
   export REPO_ROOT=$HOME/workspace/cryptoAccounting
   export PATH="$HOME/bin:$PATH"
   ```

3. **Create symlinks in ~/bin:**
   ```bash
   mkdir -p ~/bin
   ln -s $REPO_ROOT/src/scripts/balance ~/bin/balance
   ln -s $REPO_ROOT/src/scripts/transfer ~/bin/transfer
   ln -s $REPO_ROOT/src/scripts/buySats ~/bin/buySats
   
   chmod +x ~/bin/balance ~/bin/transfer ~/bin/buySats
   ```

4. **Test it:**
   ```bash
   balance
   # Should show BTC balance
   ```

## Troubleshooting

**Error: "No module named 'cryptoAccounts'"**

1. Check `REPO_ROOT` is set correctly:
   ```bash
   echo $REPO_ROOT
   ls $REPO_ROOT/src/python/cryptoAccounts.py  # Should exist
   ```

2. Or check `CRYPTO_ACCOUNTING_PYTHONPATH`:
   ```bash
   echo $CRYPTO_ACCOUNTING_PYTHONPATH
   ls $CRYPTO_ACCOUNTING_PYTHONPATH/cryptoAccounts.py  # Should exist
   ```

3. If using symlinks, ensure the symlink target is correct:
   ```bash
   ls -l ~/bin/balance  # Should show link target
   ```

**Error: "Cannot connect to database"**

Check your database environment variables:
```bash
echo $PGHOST
echo $PGUSER
echo $PGDATABASE
```

See the main README.md for database setup instructions.

## Environment Variable Checklist

Before running scripts, ensure these are set:

```bash
# Module path (choose one)
export REPO_ROOT=/path/to/cryptoAccounting
# OR
export CRYPTO_ACCOUNTING_PYTHONPATH=/path/to/cryptoAccounting/src/python

# Database connection (optional if using defaults)
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=bitcoin_accounting
export PGPASSWORD=your-password
export PGDATABASE=crypto
```

## Next Steps

- Update existing scripts in `src/scripts/` to use the improved import pattern
- Add error handling for missing environment variables
- Consider a centralized configuration file instead of env vars (optional)

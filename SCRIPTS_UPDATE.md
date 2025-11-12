# Scripts Update Summary

All scripts in `src/scripts/` have been updated with improved module path handling and error messages.

## Changes Made

### Module Path Handling
Each script now:
1. Checks `CRYPTO_ACCOUNTING_PYTHONPATH` environment variable first
2. Falls back to `REPO_ROOT/src/python` if `REPO_ROOT` is set
3. Automatically adds the path to `sys.path` before importing
4. Provides helpful error messages if imports fail

### Updated Scripts

| Script | Purpose | Changes |
|--------|---------|---------|
| `balance` | Show account balances | Added path handling, cleanup, error handling |
| `transfer` | Transfer between accounts | Added path handling, cleaned indentation, error handling |
| `buySats` | Record BTC purchase | Added path handling, full interactive implementation |
| `sell` | Record BTC sale | Created new with path handling, full implementation |
| `trades` | Show trade history | Created new with path handling |
| `earnInterest` | Record interest income | Created new with path handling, full implementation |
| `export_tx` | Export ledger to CSV | Created new with path handling |

## Usage

Set up environment variables (choose one approach):

**Option 1: Set REPO_ROOT (Recommended)**
```bash
export REPO_ROOT=/path/to/cryptoAccounting
```

**Option 2: Set CRYPTO_ACCOUNTING_PYTHONPATH**
```bash
export CRYPTO_ACCOUNTING_PYTHONPATH=/path/to/cryptoAccounting/src/python
```

**Option 3: Add to PYTHONPATH**
```bash
export PYTHONPATH=/path/to/cryptoAccounting/src/python:$PYTHONPATH
```

Then run scripts:
```bash
./balance           # Show BTC balance
./balance ETH       # Show ETH balance
./transfer          # Interactive transfer
./buySats          # Interactive buy
./sell             # Interactive sell
./trades BTC       # Show BTC trade history
./earnInterest     # Record interest income
./export_tx ledger.csv BTC  # Export BTC transactions
```

## Deployment to ~/bin

```bash
# Create symlinks
mkdir -p ~/bin
for script in balance transfer buySats sell trades earnInterest export_tx; do
    ln -s /path/to/cryptoAccounting/src/scripts/$script ~/bin/$script
done

# Make executable (if needed)
chmod +x ~/bin/*

# Add ~/bin to PATH (in ~/.bashrc or ~/.zshrc)
export PATH="$HOME/bin:$PATH"
export REPO_ROOT=/path/to/cryptoAccounting

# Then use from anywhere
balance
transfer
buySats
```

## Error Handling

All scripts now include:
- Clear error messages if module path is not set
- Database connection error handling
- Graceful exit on Ctrl+C or EOF
- Exception handling for invalid inputs

See [SCRIPTS_DEPLOYMENT.md](SCRIPTS_DEPLOYMENT.md) for detailed deployment instructions.

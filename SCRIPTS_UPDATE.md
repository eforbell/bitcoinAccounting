# Scripts Update Summary

All scripts in `src/scripts/` have been updated with improved module path handling, diagnostic tools, and 2025+ per-wallet FIFO compliance features.

## Recent Updates (December 2025 - January 2026)

### New Diagnostic & Analysis Tools

| Script | Purpose | Key Features |
|--------|---------|-------------|
| `diagnose_balances` | Validate wallet balances and transfers | - Checks for unmatched withdrawals/deposits<br>- Identifies same-wallet consolidations<br>- 3% tolerance for historical exchange fees<br>- Uses net withdrawal amount (after fees) |
| `validate_transfers` | Validate withdrawal/deposit pairs | - Matches transfers between wallets<br>- Handles fee differences (3% tolerance)<br>- 7-day time window for matching<br>- Reports unmatched transactions |
| `compare_with_sparrow` | Compare database vs Sparrow wallet | - Validates balance accuracy<br>- Identifies missing/extra transactions<br>- Prevents duplicate matching<br>- Generates reconciliation report |
| `wallet_ledger` | Show detailed wallet transaction history | - Per-wallet FIFO order<br>- Running balance calculation<br>- Fee tracking<br>- Validates against get_wallet_balance() |
| `gains_tracker` | Review capital gains for any tax year | - Show all sales for a year<br>- Per-wallet or all wallets<br>- Short-term vs long-term breakdown<br>- Export to 1099-B CSV format<br>- 2025+ per-wallet FIFO warnings |
| `exchange_liquidity` | Show purchase history by wallet | - Identifies wallets with cost basis<br>- Shows purchased vs withdrawn amounts<br>- Dynamic wallet lookup from database<br>- Helps plan where to sell |
| `forecast_gains` | Simulate hypothetical sales | - FIFO lot calculation<br>- Per-wallet support<br>- Tax implications preview<br>- No transactions recorded |
| `wallet_balances` | Show all holdings by wallet | - Multi-coin support<br>- Custody breakdown<br>- Percentage allocations<br>- Active/inactive status |

### Critical Bug Fixes

1. **Balance Calculation (cryptoAccounts.py)**
   - Fixed `get_wallet_balance()` to use CASE statements for currency filtering
   - Bug: Was summing USD amounts as BTC (Strike showed -58302 BTC!)
   - Now correctly: `SUM(CASE WHEN buy_curr = coin THEN buy ELSE 0 END)`

2. **Fee Handling**
   - Removed fee subtraction from balance calculations
   - Fees now tracking-only (already included in buy/sell amounts)
   - Removed all "Stake" transaction filters for pure debit/credit accounting

3. **Transfer Matching**
   - Compare withdrawal net amount (sell - fee) to deposit amount
   - Increased tolerance from 1% to 3% for historical large exchange fees
   - Fixed duplicate matching (prevent same DB transaction matching multiple times)

### 1099-B Export Format Updates

Enhanced CSV export for tax filing compliance:
- Added **Term** column (Short/Long)
- **Reporting Category** left empty for user to fill (A/B/C/D/E/F)
- Column headers match IRS Form 8949:
  - Description
  - Date Sold
  - Sales Proceeds
  - Date Acquired
  - Cost or Other Basis
  - Term
  - Reporting Category
- Detailed instructions for category selection

### 2025+ Per-Wallet FIFO Compliance

All tools updated with warnings and guidance for IRS Rev. Proc. 2024-28:
- Mandatory per-wallet FIFO for 2025+
- `--wallet` parameter support across tools
- Clear warnings when using global FIFO for 2025+
- Documentation of basis quality (purchased vs transferred)

### Test Suite Enhancements

- All 15 unit tests passing
- New tests for fee handling
- Transfer matching validation
- Balance calculation verification

## Original Changes (Earlier Updates)

### Module Path Handling
Each script now:
1. Checks `CRYPTO_ACCOUNTING_PYTHONPATH` environment variable first
2. Falls back to `REPO_ROOT/src/python` if `REPO_ROOT` is set
3. Automatically adds the path to `sys.path` before importing
4. Provides helpful error messages if imports fail

### Core Transaction Scripts

| Script | Purpose | Changes |
|--------|---------|---------|
| `balance` | Show account balances | Added path handling, cleanup, error handling |
| `transfer` | Transfer between accounts | Added path handling, cleaned indentation, error handling |
| `buySats` | Record BTC purchase | Added path handling, full interactive implementation |
| `sell` | Record BTC sale | Created new with path handling, full implementation |
| `trades` | Show trade history | Created new with path handling |
| `earnInterest` | Record interest income | Created new with path handling, full implementation |
| `export_tx` | Export ledger to CSV | Created new with path handling |
| `export_1099b` | Export 1099-B worksheet | Enhanced with new format |

## Usage

All scripts use `_bootstrap.py` for automatic path setup. No environment variables required!

### Prerequisites

1. Install Python dependencies:
```bash
cd /path/to/cryptoAccounting
pip install -r requirements.txt
```

2. Configure database connection in `src/python/config.py`

### Running Scripts

Scripts work from anywhere - they automatically find the module path:

```bash
# From the scripts directory
cd src/scripts
./balance              # Show BTC balance
./balance ETH          # Show ETH balance
./wallet_balances BTC  # Show all wallets
./gains_tracker 2024   # Review 2024 capital gains
./exchange_liquidity BTC --wallet=Strike  # Check Strike purchase history

# Or with python directly
python src/scripts/balance
python src/scripts/gains_tracker 2024 BTC --export-1099b

# Or from anywhere after adding to PATH (see Deployment below)
balance
gains_tracker 2024
```

### Quick Reference

**Transaction Recording:**
- `buySats` - Record Bitcoin purchase
- `sell` - Record sale
- `transfer` - Transfer between wallets
- `earnInterest` - Record interest income

**Balance & Holdings:**
- `balance [COIN]` - Show total balance
- `wallet_balances [COIN] [--all]` - Holdings by wallet
- `wallet_ledger WALLET [COIN]` - Detailed transaction history
- `exchange_liquidity [COIN] [--wallet=NAME]` - Purchase history analysis

**Tax & Reporting:**
- `gains_tracker YEAR [COIN] [--wallet=NAME] [--export-1099b]` - Capital gains review
- `forecast_gains COIN QTY [PRICE] [--wallet=NAME]` - Simulate sale
- `export_1099b YEAR [--wallet=NAME]` - Export tax forms
- `export_tx FILE [COIN]` - Export transactions to CSV

**Validation & Diagnostics:**
- `diagnose_balances WALLET [COIN]` - Validate wallet balances
- `validate_transfers [COIN]` - Check withdrawal/deposit pairs
- `compare_with_sparrow WALLET CSV_FILE` - Reconcile with Sparrow wallet
- `trades [COIN]` - Show trade history

## Deployment to ~/bin

Simple deployment - just symlink the scripts:

```bash
# Create symlinks for frequently used scripts
mkdir -p ~/bin
cd ~/bin

# Link the scripts you use most
ln -s /path/to/cryptoAccounting/src/scripts/balance .
ln -s /path/to/cryptoAccounting/src/scripts/wallet_balances .
ln -s /path/to/cryptoAccounting/src/scripts/gains_tracker .
ln -s /path/to/cryptoAccounting/src/scripts/exchange_liquidity .
ln -s /path/to/cryptoAccounting/src/scripts/forecast_gains .
# ... add more as needed

# Make sure ~/bin is in your PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/bin:$PATH"

# Now use from anywhere - no environment variables needed!
balance
wallet_balances BTC
gains_tracker 2024
```

The `_bootstrap.py` module automatically:
1. Finds the repository root
2. Adds `src/python` to Python path
3. Handles imports cleanly
4. Works from any directory

No `REPO_ROOT`, `PYTHONPATH`, or `CRYPTO_ACCOUNTING_PYTHONPATH` needed!

## Error Handling

All scripts now include:
- Clear error messages if module path is not set
- Database connection error handling
- Graceful exit on Ctrl+C or EOF
- Exception handling for invalid inputs

See [SCRIPTS_DEPLOYMENT.md](SCRIPTS_DEPLOYMENT.md) for detailed deployment instructions.

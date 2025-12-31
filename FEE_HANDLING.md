# Fee Handling in CryptoAccounting

## Critical Principle

**The `fee` column in the ledger is FOR TRACKING ONLY.**

Fees are **already included** in the `buy` and `sell` amounts. They are NOT subtracted separately when calculating balances.

## Balance Calculation Formula

```
balance = buy - sell
```

**NOT:** `balance = buy - sell - fee`

## Why This Matters

When recording transactions:

### For Withdrawals/Transfers
The `sell` amount should include the total amount leaving the wallet (transferred amount + fee):
```python
# Transfer 0.5 BTC with 0.001 BTC fee
sell = 0.501  # 0.5 + 0.001
fee = 0.001   # For tracking only
```

### For Deposits
The `buy` amount is what enters the wallet (net of fees if paid by sender):
```python
# Receive 0.5 BTC (fee was paid by sender)
buy = 0.5
fee = 0.0
```

### For Trades
Both buy and sell are net amounts after any fees:
```python
# Buy 0.5 BTC for $25,000 with $50 fee
buy = 0.5        # BTC received
sell = 25050     # USD paid (including fee)
fee = 50         # For tracking only
```

## Implementation Status

### ✅ Correctly Implemented
- `get_wallet_balance()` in cryptoAccounts.py
- `get_balance()` SQL function (fees commented out)
- `get_balance_by_account()` SQL function
- `transfer_funds()` method (correctly adds fee to sell amount)
- `wallet_ledger` script
- `diagnose_balances` script
- All test files

### Database Validation
As of 2025-12-30, balances match Sparrow wallet exactly:
- CC: 0.25874310 BTC ✓
- Vault: 4.95855861 BTC ✓

## Historical Context

Prior to this fix, some code incorrectly subtracted fees from balances, causing discrepancies with actual wallet balances (Sparrow). The fee column was always intended for tracking and reporting purposes only, not for balance calculations.

## For Future Development

When adding new balance calculation code:
1. **Never subtract the fee column** from balances
2. The fee column is metadata for:
   - Tax reporting (1099-B)
   - Fee analysis
   - Cost basis calculations
   - Transaction auditing
3. Always use: `balance = buy - sell`

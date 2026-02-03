# Future Improvements

## Performance Optimizations to Consider

1. **N+1 Query Pattern** - Scripts that loop over exchanges/wallets and query inside the loop
   - `exchange_liquidity` was fixed (fetched all trades once per exchange)
   - Review other scripts for similar patterns:
     - `wallet_balances`
     - `wallet_ledger`
     - `diagnose_balances`
   - Pattern: Fetch all data once, group/filter in memory

2. **Balance Queries** - `get_wallet_balance(coin, wallet=None)` fetches all wallets
   - Consider caching or batch queries when called repeatedly
   - Could add `get_all_wallet_balances(coin)` single-query method

3. **Trade Cost Calculations** - `get_trade_cost()` does price lookups per trade
   - For large ledgers, consider batch price lookups
   - Could prefetch all prices for date range

## Resolved in Feature 3

All original items from this file were addressed in `feature/code-cleanup`:
- FIX-001 through FIX-007 (see feature-3-prd.json for details)

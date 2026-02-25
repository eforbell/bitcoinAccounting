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

## Future Integrity Enhancements

### Per-Exchange Coverage Monitor ("liquidity wall" early warning)

**Background:** All bitcoins are fungible, so chain-of-custody lot tracking across
wallets is not strictly necessary *provided* sales always happen at exchanges where
the seller has sufficient acquisition history to cover the disposal.  The invariant
is:

    total lifetime withdrawals + sales at exchange X
        ≤ total lifetime acquisitions at exchange X

When this holds, every sale at X has unambiguous, documentable cost basis drawn
entirely from X's own purchase history — no cross-wallet lot tracing required.

**The problem to detect:** As exchange accounts close (e.g. BlockFi) or balances
are swept to self-custody wallets, the "exit liquidity" at each exchange shrinks.
If bitcoin is later transferred *back* to an exchange in excess of what was
originally acquired there, the invariant breaks and chain-of-custody proof becomes
necessary for that portion.

**Proposed check:** A per-exchange variant of the existing `coverage_gap` finding:

- For each exchange: compute `acquired` (buys + deposits with known basis) and
  `disposed` (sells + withdrawals).
- Emit a warning when `disposed / acquired` exceeds a configurable threshold
  (e.g. 80 %) — "approaching liquidity wall".
- Emit a critical finding when `disposed > acquired` — invariant broken, basis
  proof required for the shortfall.

**Strategy implication:** When selling, prefer the exchange whose basis pool gives
the *highest blended cost* (smallest realized gain).  `forecast_gains --wallet`
already supports this analysis; the coverage monitor would add a proactive alert
before a transfer decision is made.

**Building blocks already in place:**
- `exchange_liquidity` script tracks per-exchange acquisition pools.
- `basis_continuity` coverage_gap check operates at the global coin level —
  per-exchange scoping is the delta.
- Transfer-pair integrity validates that send/receive amounts balance, which is
  the prerequisite for any lot-propagation work.

**Note on step-up basis:** For holdings never sold, the cost basis resets to
fair-market value at the date of inheritance (IRC §1014), making the closed-exchange
problem moot for that portion.  The coverage monitor is most valuable for the
portion intended for sale during the holder's lifetime.

---

## Resolved in Feature 3

All original items from this file were addressed in `feature/code-cleanup`:
- FIX-001 through FIX-007 (see feature-3-prd.json for details)

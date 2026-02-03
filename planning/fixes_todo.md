# Minor Issues - RESOLVED in Feature 3

All issues addressed in feature/code-cleanup branch.

## Resolved Items

1. ~~**Dead code (Line 35)** - `self.connection = None`~~
   **FIX-001**: Removed backward compatibility shim. Tests use backend abstraction.

2. ~~**Incomplete Deposit/Withdrawal import (Lines 204-209)**~~
   **FIX-002**: Queries now executed with proper parameters.

3. ~~**Module-level `now` (Line 10)**~~
   **FIX-003**: Replaced with None defaults and runtime evaluation in all methods.

4. ~~**get_balance vs get_balance_by_account inconsistency (Lines 56-78)**~~
   **FIX-004**: get_balance_by_account() now excludes Stake transactions, consistent with get_balance().

5. ~~**Duplicate wallet filtering logic (Lines 427-455 vs 642-662)**~~
   **FIX-005**: Extracted to _get_purchase_lots() helper method.

## Additional Cleanup

6. **Legacy import methods removed** (FIX-006)
   - import_transactions_rvn_mining
   - import_transactions_nexo_csv
   - import_transactions_ada_csv
   - import_transactions_ledger_csv

7. **New wallet_imports.py module** (FIX-007)
   Bitcoin-only wallet import utilities:
   - import_ledger_live_csv()
   - import_trezor_suite_csv()
   - import_sparrow_csv()
   - import_coldcard_csv()

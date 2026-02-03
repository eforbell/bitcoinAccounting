# Feature 3: Code Cleanup and Consistency Fixes

**Status**: Planned
**Branch**: `feature/code-cleanup`
**Stories**: FIX-001 through FIX-005 (5 stories)

## Summary

Address minor issues identified during the SQLite migration refactor. These are code quality improvements that don't change functionality but improve maintainability and consistency.

### Goals
- Remove dead code from backward compatibility shims
- Fix incomplete legacy code paths
- Eliminate module-level state evaluated at import time
- Ensure consistency between similar methods
- Extract duplicate logic into reusable helpers

## Issues Addressed

From `planning/fixes_todo.md`:

### 1. Dead Code (Line 35)
```python
self.connection = None  # Keep connection attribute for backward compatibility with tests
```
Tests have been updated to use the new backend abstraction. This can be removed.

### 2. Incomplete Deposit/Withdrawal Import (Lines 204-209)
```python
elif transaction['trans_type'] == "Deposit":
    query = self.getDepositQuery()
    # Note: This case is incomplete in original code - query defined but not executed
```
Query is defined but never executed. Should be completed or removed with clear error.

### 3. Module-level `now` (Line 10)
```python
now = datetime.now()
```
Evaluated at import time. Methods using `now` as default parameter get stale timestamps.

### 4. Balance Consistency (Lines 56-78)
`get_balance()` excludes 'Stake' transactions via BalanceCalculator, but `get_balance_by_account()` doesn't. Should be consistent.

### 5. Duplicate Wallet Filtering (Lines 427-455 vs 642-662)
The trade/interest purchase filtering logic is duplicated between `get_sales_for_1099b()` and `forecast_capital_gains_fifo()`. Should be extracted to a helper method.

## Story Breakdown

| ID | Title | Complexity | Key Deliverable |
|----|-------|------------|-----------------|
| FIX-001 | Remove dead code | Low | Remove `self.connection = None` |
| FIX-002 | Complete or remove deposit/withdrawal import | Low | Execute queries or raise NotImplementedError |
| FIX-003 | Fix module-level now | Low | Use `None` default with runtime evaluation |
| FIX-004 | Consistency in balance methods | Low | Add Stake exclusion to get_balance_by_account |
| FIX-005 | Extract duplicate filtering logic | Medium | Create `_get_purchase_lots()` helper |

## File Changes

```
src/python/cryptoAccounts.py     # All fixes applied
planning/fixes_todo.md           # Mark items resolved
tests/test_cleanup.py            # NEW: Tests for fixes
```

## Testing Strategy

- Existing tests should all pass (no behavior changes for FIX-001, FIX-003)
- FIX-002: Add test for deposit/withdrawal import path
- FIX-004: Add test confirming Stake exclusion consistency
- FIX-005: Refactor tests to use new helper

## Risk Assessment

**Low Risk**: These are code quality improvements that don't change external behavior (except FIX-002 and FIX-004 which fix bugs).

## Files

- PRD: [feature-3-prd.json](feature-3-prd.json)

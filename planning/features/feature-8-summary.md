# Feature-8: CryptoAccounts Refactoring

## Summary
Refactor the monolithic 918-line `cryptoAccounts.py` into a clean, testable architecture by extracting specialized query classes following the dependency injection pattern already established in the codebase.

## Problem Statement
The `CryptoAccounts` class has grown into a "god object" with too many responsibilities:
- Data access (transactions, balances, prices)
- Transaction recording (deposits, withdrawals, trades)
- Tax calculations (1099-B, FIFO matching)
- Data export (CSV)
- Query string generation (legacy `getXQuery()` methods)
- Wallet management

This creates several issues:
- Hard to test individual components
- Difficult to maintain (918 lines)
- Mixed abstraction levels (raw SQL alongside business logic)
- Code duplication (FIFO logic duplicated in 2 methods)
- Legacy patterns (query string builders) alongside modern patterns (query classes)

## Solution
Extract specialized query classes to `db/queries/` following the existing pattern:

1. **TransactionQuery** - Transaction filtering and retrieval
2. **LedgerWriter** - Transaction recording operations
3. **CapitalGainCalculator** - FIFO cost basis and tax calculations
4. **WalletQuery** - Wallet metadata and balance queries

After refactoring, `CryptoAccounts` becomes a thin facade (≈300 lines) that delegates to specialized query classes.

## Benefits
- **Maintainability**: 918 lines → 300 lines in main class
- **Testability**: Each query class testable independently
- **Reusability**: Query classes usable across CLI, web APIs, reports
- **Consistency**: All code follows same architectural pattern
- **Code Quality**: No raw SQL in main class, clear separation of concerns

## Technical Approach
- Follow existing query class pattern (dependency injection via `__init__`)
- Maintain backward compatibility (all public methods unchanged)
- Incremental extraction (one class at a time with tests)
- Add test coverage before refactoring risky code

## Implementation Phases
1. **Phase 1**: Remove dead code (get_bitcoin_price)
2. **Phase 2**: Extract 4 query classes
3. **Phase 3**: Refactor import_transactions to use LedgerWriter
4. **Phase 4**: Add missing test coverage
5. **Phase 5**: Update documentation

## Success Metrics
- ✅ cryptoAccounts.py: 918 lines → ~300 lines (67% reduction)
- ✅ Test coverage: ~70% → 85%+
- ✅ All existing tests pass (100%)
- ✅ 4 new query classes following established pattern
- ✅ ~250 lines of new tests added

## Timeline
- **Story Points**: 10 stories
- **Priority**: Medium (code quality, not user-facing)
- **Dependencies**: None (builds on existing architecture)

## Files Modified/Created
**Modified**: `cryptoAccounts.py`, `db/queries/__init__.py`, `AGENTS.md`
**Created**: 4 query class files, 2 test files, planning docs

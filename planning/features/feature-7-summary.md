# Feature 7: Export Improvements

## Overview
Modernize the `export_tx` script to match the capabilities and usability of `import_csv`, with particular focus on wallet filtering (similar to `wallet_ledger`) and better CLI design.

## Problem Statement
The current `export_tx` script has minimal functionality compared to import capabilities:
- Only supports basic coin filtering
- No wallet/exchange filtering (users manually grep CSV for wallet)
- No date range filtering
- No preview/dry-run option
- Uses basic positional arguments instead of modern CLI options
- No help text or usage examples

Users want to export wallet-specific transaction history for reconciliation and analysis, but currently must:
1. Export entire ledger with `export_tx`
2. Manually filter CSV in Excel/text editor
3. Risk mistakes in manual filtering

## Solution
Add wallet filtering and other essential options to `export_tx`, following patterns established by `import_csv` and `wallet_ledger`.

## Key Features

### 1. Wallet Filtering
```bash
export_tx output.csv --wallet Strike --coin BTC
```
- Filter transactions by wallet/exchange name
- Uses `WHERE exchange = :wallet` SQL pattern from `wallet_ledger`
- Combines with existing coin filtering

### 2. Date Range Filtering
```bash
export_tx output.csv --start-date 2024-01-01 --end-date 2024-12-31
```
- Filter by date range (YYYY-MM-DD format)
- Useful for tax year exports, quarterly analysis
- Both dates optional (can specify only start or only end)

### 3. Dry-Run Preview
```bash
export_tx --wallet Coldcard --dry-run
```
- Preview transactions without writing file
- Shows applied filters and summary statistics
- Displays first 5 transactions in formatted table
- Helps verify filters before export

### 4. Modern CLI Options
```bash
export_tx --help

Usage: export_tx [OPTIONS] [OUTPUT_FILE]

Options:
  --coin COIN           Filter by cryptocurrency (e.g., BTC, ETH)
  --wallet WALLET       Filter by wallet/exchange name
  --start-date DATE     Start date (YYYY-MM-DD format)
  --end-date DATE       End date (YYYY-MM-DD format)
  --dry-run             Preview transactions without exporting
  -h, --help            Show this help message

Examples:
  export_tx output.csv --wallet Strike --coin BTC
  export_tx output.csv --start-date 2024-01-01 --end-date 2024-12-31
  export_tx --wallet Coldcard --dry-run
```

## Implementation Approach

### Phase 1: Backend Method (EXPORT-001)
Update `CryptoAccounts.export_transactions_csv()` to accept wallet and date range filters, using parameterized SQL queries.

### Phase 2: CLI Modernization (EXPORT-002)
Replace `sys.argv` parsing with `argparse`, add new options following `import_csv` patterns.

### Phase 3: Dry-Run Preview (EXPORT-003)
Implement preview mode with formatted table output and summary statistics.

### Phase 4: Testing (EXPORT-004)
Comprehensive unit and integration tests for all new functionality.

### Phase 5: Documentation (EXPORT-005)
Update README.md with examples and usage patterns.

## Benefits

### For Users
- **Wallet-specific exports** without manual filtering
- **Date range filtering** for tax years, quarters
- **Preview before export** to verify filters
- **Better CLI** with help text and examples
- **Consistency** with import_csv patterns

### For Developers
- **Reusable patterns** from wallet_ledger and import_csv
- **Comprehensive tests** for export functionality
- **Foundation** for future export features
- **Backward compatible** - existing scripts continue working

## Success Metrics
- Wallet filtering works correctly (verified by tests)
- Date range filtering handles edge cases (timezone, boundaries)
- Dry-run preview shows accurate transaction counts
- CLI provides helpful error messages
- All existing tests pass (zero regressions)
- Round-trip export→import produces identical data

## Out of Scope (Future Enhancements)
- Transaction type filtering
- Custom column selection
- Alternative export formats (JSON, Excel)
- Export registry pattern
- Aggregated/summary exports
- Piping to stdout

## Timeline
Estimated: 1-2 sessions
- Session 1: EXPORT-001, EXPORT-002 (core functionality)
- Session 2: EXPORT-003, EXPORT-004, EXPORT-005 (preview, tests, docs)

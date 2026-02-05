# Feature 4: Exchange Import Parsers (CLI)

**Status**: In Progress
**Branch**: `feature/exchange-import-parsers`
**Stories**: IMP-001 through IMP-013 (13 stories)

## Summary

Add import parsers for 8 major Bitcoin exchanges plus a native format, enabling users to onboard their transaction history from various sources via CLI. This establishes the parser infrastructure that Feature 5 (TUI Wizard) will build upon.

### Goals
- Support importing from major Bitcoin exchanges (Coinbase, Kraken, Strike, River, Swan, Cash App, Gemini, Fold)
- Provide a native format for backup/restore and round-trip capability
- Handle withdrawal destination assignment with sensible defaults
- Enable dry-run previews before committing imports
- Auto-detect source format when possible

## Supported Sources (9)

| Source | Format | Complexity | Notes |
|--------|--------|------------|-------|
| **Native** | Our own CSV format | Low | Round-trip with export_tx |
| Coinbase | Transaction history CSV | Medium | Multiple tx types, rewards |
| Kraken | Ledger CSV (13 cols) | High | Pair matching by refid |
| Strike | Transaction history | Low | Direct purchases |
| River | 2 formats (BTC/Account) | Medium | Auto-detect format |
| Swan Bitcoin | Deposits/Purchases | Low | DCA focused |
| Cash App | Gain/Loss CSV | Medium | No cost basis for external |
| Gemini | Transaction history | Medium | Earn/interest support |
| Fold | Yearly BTC history | Low | Rewards focused |

## Key Design Decisions

### Withdrawal Handling
When importing from exchanges, withdrawals go to unknown destinations:
- `--withdraw-to WALLET` flag assigns all withdrawals to specified wallet
- Without flag: uses `"{Exchange}-Withdrawal"` placeholder
- Comment added: `"Review: Verify destination wallet"`

### Native Format
Clean column names for round-trip:
```
trans_type,buy,buy_curr,sell,sell_curr,fee,fee_curr,exchange,group,comment,created_date
```
Also accepts legacy export format (with spaces/periods).

## CLI Usage

```bash
import_csv --list                                    # List parsers
import_csv --source coinbase file.csv                # Explicit source
import_csv file.csv                                  # Auto-detect
import_csv --source coinbase --withdraw-to Ledger file.csv  # Set withdrawal dest
import_csv --source strike --dry-run file.csv        # Preview only
import_csv --format coinbase                         # Show expected columns
```

## Story Breakdown

| ID | Title | Priority | Complexity |
|----|-------|----------|------------|
| IMP-001 | Base importer class and registry | 1 | Medium |
| IMP-002 | Transaction validation utilities | 2 | Medium |
| IMP-003 | CLI entry point (import_csv) | 3 | Medium |
| IMP-004 | Native format parser | 4 | Low |
| IMP-005 | Coinbase parser | 5 | Medium |
| IMP-006 | Kraken parser | 6 | High |
| IMP-007 | Strike parser | 7 | Low |
| IMP-008 | River parser | 8 | Medium |
| IMP-009 | Swan Bitcoin parser | 9 | Low |
| IMP-010 | Cash App parser | 10 | Medium |
| IMP-011 | Gemini parser | 11 | Medium |
| IMP-012 | Fold parser | 12 | Low |
| IMP-013 | Documentation | 13 | Low |

## File Structure

```
src/python/
├── imports/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── validation.py
│   └── exchanges/
│       ├── __init__.py
│       ├── native.py
│       ├── coinbase.py
│       ├── kraken.py
│       ├── strike.py
│       ├── river.py
│       ├── swan.py
│       ├── cashapp.py
│       ├── gemini.py
│       └── fold.py

src/scripts/
└── import_csv

tests/
├── test_import_parsers.py
└── fixtures/csv_samples/
```

## Testing Strategy

- Unit tests for each parser with sample CSV fixtures
- Validation tests for error scenarios
- Integration tests for CLI with in-memory SQLite
- Minimum 85% coverage for parser code

## Risk Assessment

**High:** Kraken pair matching complexity, exchange format changes
**Medium:** Date format variations, large file performance
**Mitigation:** Extensive test fixtures, format version detection

## Files

- PRD: [feature-4-prd.json](feature-4-prd.json)

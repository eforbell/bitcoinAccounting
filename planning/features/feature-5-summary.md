# Feature 5: Wallet Import Integration

## Overview

Integrate the 4 standalone wallet parsers from `wallet_imports.py` into the CLI import system built in Feature 4. This consolidates all import functionality under one architecture and gives wallet users the same developer experience as exchange imports.

## Problem Statement

Feature 3 extracted wallet import functions into `wallet_imports.py` as a code cleanup task. Feature 4 built a robust CLI import system with registry, validation, dry-run, and auto-detection. These two efforts are disconnected:

- **Exchange imports**: Full CLI integration via `import_csv`
- **Wallet imports**: Standalone functions requiring manual Python calls

## Solution

Convert the 4 wallet functions into registered `BaseImporter` classes under `imports/wallets/`, enabling:

```bash
# Before (manual Python)
from wallet_imports import import_ledger_live_csv
cols, txs = import_ledger_live_csv("ledger.csv")
crypto.import_transactions(txs)  # manual validation, duplicate check

# After (CLI)
import_csv ledger.csv                                    # auto-detect
import_csv --source ledger --dry-run ledger.csv          # preview
import_csv --withdraw-to "Cold Storage" ledger.csv       # with destination
```

## Scope

### In Scope
- 4 wallet parsers: Ledger Live, Trezor Suite, Sparrow, Coldcard
- New `imports/wallets/` package structure
- Full CLI integration (--list, --format, --source, --withdraw-to, --dry-run)
- Removal of orphaned `wallet_imports.py`
- Documentation updates

### Out of Scope
- New wallet support (BlueWallet, Electrum, etc.)
- UTXO-level tracking
- Address chain management
- Multi-signature wallet handling

## Architecture

```
src/python/imports/
├── __init__.py          (updated to import wallets)
├── base.py              (unchanged)
├── registry.py          (unchanged)
├── validation.py        (unchanged)
├── exchanges/
│   └── ... (8 existing parsers)
└── wallets/             ← NEW
    ├── __init__.py
    ├── ledger.py        ← LedgerImporter
    ├── trezor.py        ← TrezorImporter
    ├── sparrow.py       ← SparrowImporter
    └── coldcard.py      ← ColdcardImporter
```

## User Stories

| ID | Title | Priority |
|----|-------|----------|
| WAL-001 | Create wallets package structure | 1 |
| WAL-002 | Ledger Live importer class | 2 |
| WAL-003 | Trezor Suite importer class | 3 |
| WAL-004 | Sparrow Wallet importer class | 4 |
| WAL-005 | Coldcard importer class | 5 |
| WAL-006 | Remove standalone wallet_imports.py | 6 |
| WAL-007 | Documentation update | 7 |

## Key Design Decisions

1. **Reuse BaseImporter as-is**: The existing base class and helper methods (`_get_withdrawal_exchange()`, `_get_withdrawal_comment()`) work perfectly for wallets

2. **source_type = "wallet"**: Distinguishes wallets from exchanges in `--list` output for clarity

3. **--withdraw-to semantics**: Works identically to exchanges - wallet withdrawals need a destination too

4. **No new CLI flags**: Existing infrastructure handles everything

## Success Criteria

- [ ] `import_csv --list` shows all 4 wallet parsers with type "wallet"
- [ ] Auto-detection works for each wallet's CSV format
- [ ] `--dry-run` previews wallet transactions before import
- [ ] `--withdraw-to` sets withdrawal destinations correctly
- [ ] Validation catches errors in wallet CSV data
- [ ] `wallet_imports.py` is deleted with no test failures
- [ ] Documentation covers wallet export instructions

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Coldcard format varies by firmware | Medium | Medium | Document supported versions, flexible column matching |
| Sparrow satoshi/BTC detection | Low | Low | Existing logic handles both formats |

## Timeline

- **Stories**: 7
- **Complexity**: Low (mechanical refactoring)
- **Dependencies**: Feature 4 complete (merged)

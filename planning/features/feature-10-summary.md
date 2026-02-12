# Feature-10: Data Integrity Foundations

## Problem

New users entering data for the first time face several data integrity traps:

1. **Every wallet/exchange input is free-text** -- the Record Transaction screen uses `Input()` widgets with hardcoded defaults ("Strike", "Ledger"), and CLI scripts use `session.prompt()`. There's no dropdown of existing wallets.

2. **No name normalization** -- "Coinbase", "coinbase", and " Coinbase " are stored as three separate wallets. Balances fragment silently. Once entered, there's no way to fix it from the UI (see Feature-12).

3. **TUI Import Wizard has no duplicate detection** -- the CLI `import_csv` script warns about potential duplicates via `detect_duplicates()`, but the TUI wizard skips this entirely. A user can import the same CSV twice with no warning.

4. **CLI scripts crash on bad input** -- entering "abc" for a quantity causes an unguarded `float()` conversion that dumps a raw Python traceback.

## Solution

Quick, targeted fixes at system boundaries to prevent bad data from entering:

| Story | What | Effort |
|-------|------|--------|
| DIF-001 | Strip whitespace from wallet names at storage layer | Small |
| DIF-002 | Replace free-text exchange input with wallet dropdown (Buy form) | Medium |
| DIF-003 | Extend wallet dropdown to Sell, Transfer, Interest forms | Small (reuse DIF-002 pattern) |
| DIF-004 | Add wallet dropdown to Import Wizard withdraw-to and wallet-name fields | Small |
| DIF-005 | Port duplicate detection to TUI Import Wizard preview step | Medium |
| DIF-006 | Guard CLI scripts against invalid numeric input | Small |

## Design

### Wallet Selector Pattern (DIF-002 through DIF-004)

All wallet input fields across the TUI share a common pattern:

```
[ Select: existing wallets + "+ New Wallet..." ]
[ Input: new wallet name (hidden until needed) ]
```

- Populated from `WalletQuery.get_wallets()` on screen mount
- When `+ New Wallet...` is selected, an Input appears below for the new name
- New names are stripped of whitespace
- When database is empty, shows only `+ New Wallet...` with helpful placeholder text
- Same helper method reused across Record screen and Import Wizard

### Whitespace Normalization (DIF-001)

Applied at `LedgerWriter` level -- every method that accepts an exchange parameter calls `.strip()` before storage. Query methods also strip before matching. This is invisible to the user but prevents the most common data fragmentation issue.

### Duplicate Detection in TUI (DIF-005)

The Import Wizard step 3 (preview) calls the existing `detect_duplicates()` function from `imports/validation.py`. If matches are found, a yellow warning banner appears above the preview table showing the count. This matches the CLI's behavior -- warning only, not a blocker.

## Non-Goals

- **Case normalization** (e.g., forcing "coinbase" → "Coinbase") -- deferred. This requires a migration strategy for existing databases and a decision about canonical naming. Whitespace trimming is safe and non-controversial; case changes need more thought.
- **Foreign key constraints** between `ledger.exchange` and `wallets.wallet_id` -- deferred to Feature-11 (Wallet Management) which introduces proper wallet lifecycle.
- **Transaction editing** -- separate feature (Feature-12). This feature prevents mistakes; Feature-12 fixes them.

## Dependencies

- None. All stories build on existing infrastructure (WalletQuery, detect_duplicates, LedgerWriter).

## Testing Strategy

- Unit tests for whitespace normalization (storage and query)
- TUI tests using `app.run_test()` for wallet selector behavior
- TUI tests for duplicate detection warning display
- Manual verification for CLI script input guarding (interactive prompts)

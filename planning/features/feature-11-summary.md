# Feature-11: Wallet Management Screen

## Problem

The `wallets` table exists in the database schema with columns for type, custody, description, active status, and notes -- but there is no interface to manage it. Wallets are phantom entities: they appear only as distinct `exchange` strings extracted from ledger transactions, with custody type guessed from name heuristics.

This creates several problems for new users:

1. **No way to create wallets before importing** -- wallets only exist after transactions reference them
2. **No way to edit wallet metadata** -- custody type, description, and active status are unmanageable
3. **No way to fix naming mistakes** -- if a user records transactions under "Stike" instead of "Strike", there's no rename capability. Balances fragment across the two names.
4. **No way to merge duplicates** -- "Coinbase" and "coinbase" can't be consolidated

## Solution

A dedicated Wallet Management TUI screen (press **W**) that makes wallets first-class entities:

### Screen Layout

```
Header: "Wallet Management"
DataTable:
  Name | Type | Custody | Description | Active | Tx Count
  ─────┼──────┼─────────┼─────────────┼────────┼─────────
  Coinbase | exchange | custodial | Main exchange | Yes | 142
  Ledger   | hardware | self-custodied | Nano X | Yes | 87
  Strike   | exchange | custodial |  | Yes | 45
Footer: [N]ew  [E]dit  [R]ename  [M]erge  [D]eactivate  [Esc]Back
```

### Operations

| Key | Operation | Safety Level |
|-----|-----------|-------------|
| **N** | Create new wallet | Safe -- new record, no existing data affected |
| **E** | Edit selected wallet metadata | Safe -- changes metadata only, not transactions |
| **D** | Toggle active/inactive | Safe -- soft toggle, reversible |
| **R** | Rename wallet | Destructive -- updates all ledger references, requires confirmation |
| **M** | Merge two wallets | Destructive -- reassigns transactions and deletes source, requires confirmation |

### Data Layer: WalletQuery Extensions

New methods added to the existing `WalletQuery` class (following Feature-8 Query Object pattern):

- `add_wallet(wallet_id, wallet_type, custody, ...)` -- INSERT into wallets table
- `update_wallet(wallet_id, **kwargs)` -- UPDATE specific fields
- `rename_wallet(old_id, new_id)` -- UPDATE wallets.wallet_id + UPDATE all ledger.exchange rows atomically
- `merge_wallets(source_id, target_id)` -- UPDATE ledger.exchange for source → target, DELETE source wallet
- `sync_wallets_from_ledger()` -- create wallet records for any exchange names in ledger that don't have a wallets table entry (bridges the implicit→explicit gap)

### Sync on Mount

When the Wallet Management screen opens, it calls `sync_wallets_from_ledger()` to ensure every wallet referenced in transactions has a proper wallets table record. This bridges the gap for existing databases where wallets were never formally created. Custody type is inferred from the name heuristic (same logic that already exists in `infer_custody_type()`).

## Stories

| ID | Title | Effort |
|----|-------|--------|
| WM-001 | Add wallet CRUD methods to WalletQuery | Medium |
| WM-002 | Wallet Management TUI screen with DataTable | Medium |
| WM-003 | Create Wallet modal | Medium |
| WM-004 | Edit Wallet modal | Small (reuses Create pattern) |
| WM-005 | Rename Wallet with confirmation | Medium |
| WM-006 | Merge Wallets with confirmation | Medium |
| WM-007 | Update documentation and navigation | Small |

## Dependencies

- **Feature-10 (DIF-001)** recommended first -- whitespace normalization prevents new duplicates while this feature provides tools to fix existing ones
- No hard blockers -- can be built independently

## Non-Goals

- **Foreign key enforcement** between ledger.exchange and wallets.wallet_id -- would require a migration for existing databases. The sync-on-mount approach provides the same practical benefit without schema changes.
- **Wallet balance editing** -- balances are derived from transactions, not stored directly. To fix a balance, fix the transactions (Feature-12).
- **Multi-select operations** -- bulk rename/merge deferred. Single-wallet operations cover the primary use cases.

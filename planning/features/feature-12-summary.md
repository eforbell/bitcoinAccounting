# Feature-12: Transaction Editor

## Problem

Once a transaction is committed to the ledger, it is **permanent**. There is no edit, delete, or undo capability anywhere in the system -- not in the TUI, not in CLI scripts, not in the query layer. The only way to fix a mistake is to open the SQLite database directly and run manual SQL.

This is the single biggest gap for new users. Mistakes are inevitable when learning the system -- wrong amounts, wrong wallets, duplicate entries, typos. Without a correction mechanism, users either live with bad data or abandon the tool.

## Solution

A transaction editor integrated into the existing Ledger screen. Press Enter on any transaction row to open a detail view with Edit, Delete, and (for deleted transactions) Restore capabilities.

### Architecture

```
Ledger Screen (existing)
  └── [Enter] on row → TransactionDetailModal (new)
        ├── [Edit] → EditTransactionModal (new)
        │     └── Shows diff preview → Confirm → LedgerWriter.update_transaction()
        ├── [Delete] → Confirmation dialog (new)
        │     └── Warns about transfer pairs → Confirm → LedgerWriter.soft_delete_transaction()
        └── [Restore] (only for deleted rows)
              └── LedgerWriter.restore_transaction()
```

### Soft-Delete Design

Transactions are never physically deleted. Instead:

- Two new columns added to ledger: `deleted INTEGER DEFAULT 0`, `deleted_date TEXT`
- All existing queries get `WHERE deleted = 0` filter (backward compatible -- existing rows have `deleted = 0`)
- Deleted transactions can be viewed via "Show Deleted" toggle in the Ledger filter panel
- Deleted transactions can be restored at any time

This preserves the full audit trail and makes mistakes recoverable.

### Schema Migration

The `deleted` and `deleted_date` columns are added via `ALTER TABLE` during database initialization. This is safe for existing databases:
- SQLite `ALTER TABLE ... ADD COLUMN` is a no-op if the column already exists (with proper error handling)
- New columns default to `0` and `NULL`, so existing rows are unaffected
- No data migration needed

## Stories

| ID | Title | Effort | Risk |
|----|-------|--------|------|
| TXE-001 | Add soft-delete columns to ledger schema | Medium | High -- touches all queries |
| TXE-002 | Add update/delete/restore methods to LedgerWriter | Medium | Low -- new methods only |
| TXE-003 | Transaction detail modal from Ledger screen | Medium | Low -- read-only display |
| TXE-004 | Edit Transaction modal with diff preview | Large | Medium -- form validation |
| TXE-005 | Delete Transaction with transfer pair warning | Medium | Medium -- heuristic detection |
| TXE-006 | Show Deleted toggle and Restore flow | Medium | Low -- extends existing filter panel |

## Dependencies

- **Feature-10** recommended first -- smart wallet dropdowns are reused in the edit modal's exchange field
- **Feature-11** optional but helpful -- wallet management provides the wallet list that populates the edit modal's exchange selector
- No hard blockers -- can be built independently (edit modal falls back to free-text for exchange field if wallet selectors aren't available)

## Non-Goals

- **Bulk edit/delete** -- single-transaction operations only in this feature. Bulk operations can be added later.
- **Physical delete** -- all deletes are soft-deletes. A future "purge deleted" operation could physically remove soft-deleted rows, but that's not in scope.
- **Edit history / versioning** -- the soft-delete timestamp provides basic audit trail, but full versioning (storing previous values of edited fields) is deferred.
- **CLI transaction editor** -- TUI only in this feature. CLI scripts could add `--edit` and `--delete` flags later.

## Key Design Decisions

### Why soft-delete instead of hard delete?

1. **Recoverability** -- users can undo mistakes without database expertise
2. **Audit trail** -- for tax compliance, knowing what was changed and when matters
3. **Simplicity** -- no need for a separate "trash" table or undo stack
4. **Performance** -- adding `WHERE deleted = 0` to queries is negligible

### Why edit-in-place instead of "delete and re-create"?

1. **Preserves transaction ID** -- downstream references (if any) remain valid
2. **Atomic** -- single UPDATE vs. DELETE + INSERT
3. **Cleaner UX** -- user sees their change as a modification, not a replacement
4. **Less error-prone** -- no risk of forgetting a field when re-creating

### Why warn about transfer pairs on delete?

Transfers are recorded as two linked transactions (withdrawal + deposit). Deleting one side creates an orphaned transaction that will show up as an unmatched transfer in `validate_transfers`. The warning doesn't prevent deletion -- it informs the user so they can delete both sides if intended.

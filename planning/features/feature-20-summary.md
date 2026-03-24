# Feature-20: Web Ledger, Transaction Entry, and Wallet Management

## Purpose

Feature-20 brings the operational write and correction surfaces to the web so routine management can happen from phone or desktop without losing the safety of the existing TUI fallback.

## Timing

Drafted on **March 24, 2026**.

Recommended earliest execution: **April 2, 2026**.

## Scope

1. Ledger explorer with filters and deleted visibility.
2. Transaction detail, edit, delete, and restore flows.
3. Manual buy/sell/transfer/interest entry.
4. Wallet CRUD, rename, merge, and active/inactive state management.
5. Audit and safety polish for destructive actions.

## Why Feature-20 Follows Dashboard

The read surfaces should stabilize first, then the web app can take on higher-risk write workflows. The TUI remains available as fallback while the web write paths mature.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WOP-001 | Ledger explorer | Foundation for most operational drill-down |
| WOP-002 | Transaction detail/edit/delete/restore | Makes corrections possible on the web |
| WOP-003 | Manual transaction entry | Covers routine operator input flows |
| WOP-004 | Wallet management | Supports tax-critical wallet hygiene |
| WOP-005 | Audit + safety polish | Hardens write flows before broader reliance |

## Risk Controls

1. Write-path trust risk
   Control: validate aggressively, confirm destructive actions, and test rollback behavior.
2. Wallet rename/merge risk
   Control: preserve existing atomic wallet operations and show transaction-count warnings.
3. Mobile complexity risk
   Control: keep quick entry mobile-friendly while allowing denser editing on desktop.

## Definition of Done

- Ledger browsing and transaction corrections are available on the web.
- Manual transaction entry covers the core flows.
- Wallet management is web-accessible and remains tax-safe.
- Destructive actions are explicit, reversible where appropriate, and clearly communicated.

# Feature-15: Treasury Integrity Foundations

## Purpose

Feature-15 introduces a deterministic integrity layer for long-hold treasury management. The goal is to continuously validate that ledger state, wallet mappings, and cost basis remain coherent and auditable even when sell activity is infrequent.

## Timing

Drafted on **February 24, 2026**.

Recommended earliest execution: **March 1, 2026**.

## Scope

1. Reconciliation engine for expected vs observed balances by coin/wallet.
2. Transfer-pair integrity checks for internal movement consistency.
3. Cost-basis continuity checks for missing/ambiguous basis.
4. Treasury health scoring with configurable thresholds.
5. CLI reporting + planning artifact closeout.

## Why Feature-15 Exists

For a diamond-hands operating mode, primary risk is often data drift rather than disposal optimization. This feature makes stack correctness measurable and repeatable before introducing heavier attestation UX.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| TIF-001 | Ledger reconciliation engine | Establishes baseline correctness signal |
| TIF-002 | Transfer-pair integrity checks | Catches the highest-frequency classification issues |
| TIF-003 | Cost-basis continuity monitor | Prepares future tax confidence with low sale volume |
| TIF-004 | Treasury health score | Unifies findings into operator-friendly signal |
| TIF-005 | CLI report + metadata updates | Ships a usable interface and closes governance loop |

## Risk Controls

1. False positives in matching logic
   - Control: deterministic fixtures + threshold tuning before default enablement.
2. Query performance on larger ledgers
   - Control: add benchmark dataset and optimize to backend-native SQL paths.
3. Severity overload
   - Control: opinionated defaults and concise top-finding summaries.

## Definition of Done

- Integrity checks run deterministically from canonical transaction data.
- Findings classify severity and include remediation hints.
- Health score persists and trends across snapshots.
- CLI report exports JSON/CSV and human-readable summary.
- Planning/progress artifacts capture implementation learnings.

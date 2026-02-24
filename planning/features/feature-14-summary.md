# Feature-14: Legacy Name Removal (Post-Deprecation)

## Purpose

Feature-13 established canonical `bitcoin*` naming while preserving compatibility (`crypto*` shims, aliases, and path fallback). Feature-14 is the cleanup phase that removes those temporary compatibility layers.

## Timing

Drafted on **February 19, 2026**.

Recommended earliest execution: **July 1, 2026** (after the stated deprecation window and initial public stabilization).

## Scope

1. Remove legacy Python module shims (`cryptoAccounts`, `cryptoAccounting`).
2. Remove legacy console script aliases (`crypto-accounting`, `crypto-tui`).
3. Finalize long-term data path policy (retain or remove legacy fallback).
4. Purge remaining legacy wording from docs and script headers.
5. Update tests and planning metadata for canonical-only behavior.

## Why Separate Feature-14?

Keeping cleanup in a dedicated feature reduces risk:

- Feature-13 handled migration with user safety.
- Feature-14 handles intentional breaking changes with explicit release communication.
- Rollback is simpler if done as one concentrated cleanup PR.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| LNR-001 | Remove legacy module shims | Core runtime surface first |
| LNR-002 | Remove legacy console aliases | Packaging/CLI cleanup after runtime |
| LNR-003 | Finalize path policy | Locks long-term storage behavior |
| LNR-004 | Purge legacy docs language | Align user-facing guidance with reality |
| LNR-005 | Tests + governance cleanup | Finish with verification and documentation |

## Risk Controls

1. Breaking automation risk
Control: pre-flight confirmation with known users and explicit release note warnings.

2. Legacy data path confusion
Control: either keep fallback long-term or provide explicit migration script/steps before removal.

3. Recovery risk after removals
Control: preserve a rollback commit that reintroduces shims if needed.

## Definition of Done

- No runtime dependency remains on `crypto*` module names.
- No packaging alias remains for `crypto-accounting` or `crypto-tui`.
- Docs and examples are canonical-only (except historical release notes).
- Tests reflect canonical-only behavior.
- Planning artifacts updated and Feature-14 marked complete.

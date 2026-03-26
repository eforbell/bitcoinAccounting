# Feature-25: Wallet Verification Hardening

## Purpose

Feature-25 hardens the shipped wallet-verification flow from Feature-23 by tightening correctness, scan semantics, and operator trust boundaries without changing the core product direction.

## Timing

Drafted on **March 26, 2026**.

Recommended earliest execution: **next web follow-up cycle after Feature-23 merge**.

## Scope

1. Decimal-safe BTC arithmetic for verified balance and drift calculations.
2. Real gap-limit-based discovery semantics instead of storing `gap_limit` as metadata only.
3. Explicit confirmed-vs-unconfirmed verification policy.
4. Verification-path efficiency improvements for dashboard and persistence helpers.
5. Typed verification status/coverage enums and cleaner operator-facing backend failures.

## Why This Follow-Up Matters

Feature-23 proved the product value with real self-custody and multisig wallets, but some of the remaining implementation details are now trust-boundary issues rather than optional polish. This follow-up keeps the green `🔰 Verified` signal defensible as wallet depth, scan cost, and operator reliance increase.

## Planning Principles

- Preserve the successful Core-plus-Electrum architecture from Feature-23.
- Prefer correctness and clarity over broadening scope.
- Tighten the meaning of verification before adding remembered sources or richer rollups.
- Keep the operator signal trustworthy even when scans are deep, partial, stale, or pending.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WVH-001 | Decimal-safe verification arithmetic | Prevents false drift/pass outcomes at the core comparison layer |
| WVH-002 | Real gap-limit discovery semantics | Aligns implementation with the stated scan model and operator expectations |
| WVH-003 | Confirmed/unconfirmed balance policy | Clarifies what counts as verified balance and how pending activity is surfaced |
| WVH-004 | Verification-path performance cleanup | Reduces repeated DB/setup work and keeps dashboard/verification reads efficient |
| WVH-005 | Typed status/coverage contract cleanup | Makes verification state less error-prone across API, UI, and persistence |

## Definition of Done

- Verified balance and drift calculations avoid float precision ambiguity.
- `gap_limit` materially affects discovery behavior instead of being stored-only metadata.
- The app clearly states whether pending/unconfirmed funds affect the verification outcome.
- Dashboard and wallet verification reads avoid obvious repeated work.
- Verification state values are constrained by typed contracts rather than loose strings.

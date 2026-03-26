# Feature-23 Implementation Plan

## Goal

Ship private, on-demand wallet balance verification for Bitcoin wallets in the web app by:

- accepting modern output descriptors from the operator
- using local Bitcoin Core 29+ as the v1 descriptor authority
- querying a local Electrum-compatible server for balance/history by scripthash
- comparing verified chain balance to ledger balance
- storing non-sensitive verification results for dashboard and wallet-detail visibility

## V1 Design Decision

Feature-23 keeps descriptor orchestration in Python, but **does not make Python the source of truth for descriptor semantics**.

V1 should use:

- a Python-owned `DescriptorEngine` interface
- a `BitcoindDescriptorEngine` production implementation
- local Bitcoin Core 29+ RPCs for:
  - descriptor validation and canonicalization
  - checksum handling
  - multipath expansion
  - ranged address derivation
- an Electrum-compatible client for:
  - scripthash balance lookups
  - scripthash history lookups

This keeps the app Python-first without forcing the web service to implement descriptor grammar and derivation logic itself.

MVP product posture:

- Bitcoin Core 29+ is a hard requirement for Feature-23 v1.
- V1 is balance-only.
- Remembered descriptor sources are deferred.
- Default verification recency window is 30 days unless overridden by environment configuration.
- Wallet detail should be able to show a strong green `Verified` state when a self-custody wallet is recently verified and clean.
- Portfolio should show a top-level `Verified` posture only when all eligible self-custody wallets are recently verified, fully covered, and clean.

## Proposed Package Layout

```text
src/python/web/
├── models_verification.py
├── routes/
│   └── verification.py
└── services/
    ├── descriptor_engine.py
    ├── electrum_client.py
    └── wallet_verification.py

tests/
├── test_bitcoind_descriptor_engine.py
├── test_electrum_client.py
├── test_web_wallet_verification.py
└── test_verification_findings.py
```

## Core Workflow

1. Operator submits one combined descriptor or a complete set of branch-specific descriptors.
2. `DescriptorEngine` validates and normalizes the descriptor set with local Bitcoin Core.
3. `DescriptorEngine` expands multipath descriptors into concrete branch descriptors where needed.
4. Verification service applies a gap-limit-based discovery policy to determine how far each branch should be derived.
5. `DescriptorEngine` derives addresses for the needed branch range.
6. Verification service converts each derived address to `scriptPubKey`, then to Electrum `scripthash`.
7. Electrum client loads balance and optionally history per `scripthash`.
8. Verification service aggregates branch balances, tracks highest observed used or scanned index, and compares the verified chain balance to the ledger wallet balance.
9. Service persists result metadata and exposes verified/partial/failed/stale states to the UI.

For MVP, step 7 should only require balance queries. History lookup can remain optional or deferred.

## Initial Story Grouping

### Slice 1: WVV-001

Deliver:

- verification result schema
- result persistence
- result status model
- API/read model skeleton

This can start immediately and does not depend on the final descriptor-engine implementation details.

### Slice 2: WVV-002 foundation

Deliver:

- `DescriptorEngine` Python interface
- `BitcoindDescriptorEngine` stub and RPC contract
- Electrum client interface and error model
- test fixtures for real descriptors

This is the most important technical seam because it defines how the rest of the feature composes.

### Slice 3: WVV-003

Deliver:

- manual verification session endpoint
- descriptor input validation
- fast preflight plausibility scan for obvious mismatch or no-anchor wallets
- gap-limit-based scan policy
- address derivation -> scripthash -> Electrum balance flow
- persisted verification result

This is the first operator-visible, end-to-end slice.

### Slice 4: WVV-004

Deliver:

- wallet-detail verification card
- dashboard verification summary
- partial/stale/failed/drift-detected state rendering
- wallet-level green `Verified` state for recent clean self-custody verification
- stricter portfolio-level `Verified` posture only when all eligible self-custody wallets are recently verified, fully covered, and clean

### Slice 5: WVV-007

Deliver:

- mismatch-to-finding mapping
- alertable verification states
- structured verification metadata for integrity surfaces

### Deferred for later slices

- WVV-005 remembered verification sources
- WVV-006 Sparrow wallet-file unlock/integration

These are useful but should not block shipping the descriptor-session baseline.

## First Code Pass

Recommended first implementation tasks:

1. Add `models_verification.py` with result/status resources.
2. Add persistence helpers for verification runs and latest wallet verification state.
3. Add `DescriptorEngine` protocol/interface.
4. Add `BitcoindDescriptorEngine` with methods such as:
   - `inspect_descriptor(...)`
   - `expand_descriptor_set(...)`
   - `derive_addresses(...)`
5. Add `ElectrumClient` with methods such as:
   - `get_scripthash_balance(...)`
   - `get_scripthash_history(...)` as deferred or optional for MVP
6. Add verification service orchestration:
   - descriptor input -> normalized branches
   - ledger eligibility / anchor check for whether verification is meaningful
   - shallow preflight plausibility scan before deeper Electrum work
   - gap-limit-based branch discovery
   - derived addresses -> scripthashes
   - balance aggregation
   - highest-used/highest-scanned metadata persistence
   - coverage classification
   - result persistence
7. Add one authenticated manual verification route.
8. Add focused tests using real fixture descriptors and mocked RPC responses.

## Fixture Requirements

Before implementation is trusted, collect fixture descriptors for:

- Sparrow single-sig combined descriptor
- Sparrow multisig combined descriptor
- Bitcoin Core descriptor export
- one Coldcard export shape
- one branch-specific partial-coverage case
- one invalid checksum or malformed descriptor

The acceptance bar should be real-fixture validation, not only hand-written parser examples.

## Scan Policy Recommendation

V1 should follow a Sparrow-style wallet-discovery model rather than a one-shot fixed range:

- maintain a per-branch discovery boundary using `highest used index + gap limit`
- persist enough metadata from successful runs to avoid restarting from pure zero-knowledge each time
- on the first verification run for a wallet, ask the operator how many addresses to scan and prefill a conservative default ceiling of `50`
- apply a conservative hard ceiling to prevent runaway scans
- allow an operator override when a wallet is known to have deeper address usage

The app should not show full `Verified` when a scan hits the hard ceiling before satisfying the policy.

## Fast Bailout Recommendation

V1 should avoid expensive deep scans when the operator is clearly using the wrong descriptor or when the wallet has nothing meaningful to verify.

Recommended behavior:

- first check whether the ledger wallet has meaningful self-custody or on-chain-relevant activity
- if not, return an operator-readable `not meaningful to verify yet` style result rather than scanning deeply
- if yes, run a shallow plausibility scan on the supplied descriptor material before the full gap-limit discovery pass
- if the shallow scan finds no plausible activity or balance where the ledger strongly suggests there should be some, fail fast as likely descriptor mismatch or insufficient scan depth

This preflight should be a plausibility filter, not a tx-by-tx proof requirement. Feature-23 v1 remains balance verification, not full transaction reconciliation.

## Important Constraints

1. Do not let the web app claim full wallet verification when descriptor coverage is partial.
2. Do not persist descriptor material by default.
3. Do not make Python descriptor grammar logic the hidden production source of truth in v1.
4. Do not block the rest of the app when local Core or Electrum is unavailable; return explicit operator-readable failure states.
5. Keep the verification result model separate from wallet CRUD and ledger accounting tables.
6. Portfolio-level `Verified` must be a strict aggregate signal, not a loose summary badge.

## Remaining Questions

These are the only questions I still consider materially blocking:

1. What exact internal gap-limit setting should back the discovery policy when the first-run scan ceiling defaults to 50 addresses unless the operator overrides it?

## Exit Criteria For Feature-23 Start

The feature is ready to implement when:

- `planning/current-feature.json` points to Feature-23
- the Core-backed `DescriptorEngine` posture is accepted
- the descriptor fixture set is assembled
- the MVP UI/status posture is accepted
- the first implementation slice is defined as `WVV-001 + WVV-002 foundation`

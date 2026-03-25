# Feature-23: Descriptor-Based Wallet Verification

## Purpose

Feature-23 adds private, on-demand Bitcoin wallet verification to the web app by comparing ledger balances against balances derived from registered or session-provided wallet descriptors over a local Electrum-compatible server, while avoiding persistent storage of sensitive descriptor material by default.

## Timing

Drafted on **March 25, 2026**.

Recommended earliest execution: **April 21, 2026**.

## Scope

1. Verification session model and result persistence for ledger-vs-chain balance checks.
2. Electrum-protocol-backed chain query abstraction for private local servers.
3. Descriptor-first verification flow with support for external/change descriptor sets.
4. Sparrow-aware operator workflow, starting with manual descriptor entry and future wallet-file unlock paths.
5. Dashboard, wallet-detail, and integrity surfaces for verified balance, drift, and failure states.

## Why Feature-23 Matters

Bitcoin Accounting currently tracks the operator's intent in PostgreSQL/SQLite, but not the chain reality that the ledger is supposed to describe. Descriptor-based verification closes that gap without relying on foreign APIs. It gives private operators a way to detect missing imports, fee mistakes, or wallet drift using infrastructure they already control.

## Planning Principles

- Descriptor-first, not xpub-first. Multisig and modern wallet setups require full descriptor coverage.
- Electrum protocol as common ground. Server choice (`electrs`, `mempool/electrs`, `Frigate`, or similar) remains an operator deployment concern.
- On-demand by default. Verification secrets should be loaded only when needed unless the operator explicitly opts into persistence.
- Persist results freely; persist descriptor material only by explicit operator choice.
- Support multiple chain accounts per wallet at the model layer even if the first UI exposes only one.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WVV-001 | Verification domain model + result persistence | Establishes the privacy boundary and canonical verification outputs |
| WVV-002 | Electrum chain-query backend abstraction | Decouples verification logic from any single server implementation |
| WVV-003 | Manual descriptor verification session | Ships the safest baseline flow without requiring secret persistence |
| WVV-004 | Wallet detail + dashboard verification surfaces | Makes drift and verified state visible in daily use |
| WVV-005 | Optional remembered verification sources | Adds operator convenience without making persistence mandatory |
| WVV-006 | Sparrow wallet source research/integration path | Opens a native workflow for advanced operators while preserving encryption posture |
| WVV-007 | Integrity finding integration + alerts | Turns verification mismatches into actionable operational signals |

## Risk Controls

1. Secret-handling risk
   Control: default to session-only descriptor handling, persist only verification outputs, and require explicit opt-in for stored sources.
2. False-confidence risk
   Control: define verification narrowly as balance verification for registered descriptor accounts, and clearly label partial or stale coverage.
3. Protocol/provider risk
   Control: build against an internal Electrum-compatible abstraction rather than binding the feature to one server implementation.

## Definition of Done

- Operators can run an on-demand BTC verification against a local Electrum-compatible server using descriptor input.
- The app records non-sensitive verification outcomes such as verified balance, drift, chain height, timestamp, and failure state.
- Wallet and dashboard views can distinguish ledger balance from verified chain balance.
- Descriptor persistence is optional, not assumed, and clearly separated from normal ledger data.
- The integrity layer can surface verification mismatches as findings rather than leaving them as ad hoc UI warnings.

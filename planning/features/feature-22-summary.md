# Feature-22: Web Block Clock and Bitcoin Node Presence

## Purpose

Feature-22 connects the web dashboard to the household Bitcoin node stack so the app reflects the live timechain behind the operator's accounting, without turning the dashboard into a full node console.

## Timing

Drafted on **March 25, 2026**.

Recommended earliest execution: **April 14, 2026**.

## Scope

1. Optional Bitcoin RPC-backed chain status service for the web runtime.
2. Dashboard block clock card with essential node and chain metrics.
3. Lightweight API/read model for chain status and degraded states.
4. Refresh/staleness policy suitable for phone and desktop use.
5. Operator docs for local-node configuration on `numenor`-style deployments.

## Why Feature-22 Matters

The current web dashboard is useful, but it is still only reporting ledger state. Adding a block clock and node presence panel makes the app feel grounded in Bitcoin itself: blocks advancing, peers connected, mempool shifting, sync healthy. It reinforces the sovereignty story without yet taking on the heavier problem of wallet verification.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| BTC-001 | Node config + runtime service seam | Establishes optional, non-blocking Bitcoin RPC access |
| BTC-002 | Chain status API/read model | Normalizes node metrics into stable web payloads |
| BTC-003 | Dashboard block clock card | Delivers visible operator value on the home screen |
| BTC-004 | Refresh, stale-state, and degraded UX polish | Keeps the feature trustworthy under real node outages or sync lag |
| BTC-005 | Docs + deployment notes | Makes the feature repeatable on private household hosts |

## Risk Controls

1. Node availability risk
   Control: keep Bitcoin integration optional and non-fatal; the dashboard must still load when the node is unavailable.
2. Polling/performance risk
   Control: fetch only a small set of RPC calls and define a conservative refresh cadence before adding anything heavier.
3. UI scope-creep risk
   Control: keep v1 to a compact status card rather than cloning the full `bitcoin-tui` surface.

## Definition of Done

- Authenticated dashboard can show a compact block clock / node presence card.
- The card reports current height, sync posture, peers, and mempool summary when local RPC is available.
- The web app degrades cleanly when chain status is disabled or unreachable.
- Mobile and desktop layouts both present the chain status clearly.
- Deployment guidance exists for cookie-authenticated local `bitcoind` setups.

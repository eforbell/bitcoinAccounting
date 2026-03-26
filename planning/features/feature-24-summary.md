# Feature-24: Web Trades and Liquidity View

## Purpose

Feature-24 ports the TUI trades and exchange-liquidity analysis into the web app so operators can inspect trade history, cost basis, and exchange-side liquidity from the same authenticated browser shell as the rest of the web product.

## Timing

Drafted on **March 25, 2026**.

Shipped on **March 25, 2026** via PR **#31**.

## Scope

1. Authenticated trades API with pagination and exchange filtering.
2. Authenticated liquidity API with per-exchange balances and average cost.
3. Web Trades page with Trade History and Liquidity sub-views.
4. Cost basis summary cards covering exchange balances, cold storage, and total holdings.

## Why Feature-24 Matters

The web app already covered dashboard, ledger, wallets, and imports, but operators still had to drop back to the TUI for a cost-basis-first view of actual trades and sale capacity by exchange. This feature closes that gap with a read-only analytical view that stays aligned with the existing Python trade and balance logic.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WTR-001 | Trades API endpoints, models, and service layer | Establishes the read model the UI depends on |
| WTR-002 | Trade History web view with pagination | Delivers immediate browser-side visibility into trades |
| WTR-003 | Liquidity web view with cost basis summary | Adds the exchange liquidity analysis operators use for planning |
| WTR-004 | Exchange filter and responsive polish | Makes the feature practical on both desktop and mobile |

## Risk Controls

1. Cost basis trust risk
   Control: reuse existing trade and balance query logic rather than reimplementing calculations in the frontend.
2. UI density risk
   Control: split the page into Trade History and Liquidity sub-views instead of trying to show all analysis at once.
3. Performance risk
   Control: keep liquidity read-only and paginated where needed, with server-side slicing for the trade list.

## Definition of Done

- Authenticated operators can browse paginated trade history in the web app.
- The web app exposes exchange liquidity and average-cost summaries through stable API routes.
- The Trades page works as a responsive browser equivalent of the TUI trades/liquidity screen.
- Cost basis and holdings summary cards make exchange exposure and cold-storage posture visible at a glance.

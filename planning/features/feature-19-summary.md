# Feature-19: Web Portfolio Dashboard and Wallet Views

## Purpose

Feature-19 delivers the daily-use read experience for the web app: total BTC holdings, cost basis, custody posture, wallet balances, and recent activity optimized for quick phone checks with richer desktop drill-down.

## Timing

Drafted on **March 24, 2026**.

Recommended earliest execution: **March 30, 2026**.

## Scope

1. Portfolio summary API and responsive dashboard.
2. Wallet balances and custody breakdown.
3. Wallet detail pages with recent activity.
4. Recent transaction strip and quick actions.
5. Refresh/caching policy for habitual use.

## Why Feature-19 Matters

Once tax workflows are on the web, the next most valuable capability is habitual visibility. The dashboard becomes the “phone home screen” for the app: current stack, basis, wallet posture, and quick entry into deeper ledger/tax work.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WPF-001 | Portfolio summary API + mobile dashboard | Establishes the daily-use landing page |
| WPF-002 | Wallet balances + custody | Makes sovereignty posture visible |
| WPF-003 | Wallet detail view | Enables direct drill-down from dashboard |
| WPF-004 | Recent transactions + quick actions | Shortens common operator flows |
| WPF-005 | Refresh/caching policy | Keeps the dashboard trustworthy and responsive |

## Risk Controls

1. Number drift risk
   Control: derive dashboard outputs directly from existing query classes.
2. Ambiguous custody risk
   Control: clearly label inferred custody vs explicit wallet metadata.
3. Performance risk
   Control: keep reads light and define explicit refresh behavior before adding heavier caching.

## Definition of Done

- The web app has a phone-friendly portfolio landing page.
- Wallet balances and custody are easy to inspect.
- Recent activity and quick actions are reachable in one or two taps.
- Dashboard values stay consistent with ledger and tax views.

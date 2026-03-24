# Feature-18: Web Tax Reporting and Forecasting

## Purpose

Feature-18 brings the primary reason for the app to the web first: tax reporting, wallet-separated FIFO handling, 1099-B export, and hypothetical sale forecasting suitable for routine phone access and deeper desktop review.

## Timing

Drafted on **March 24, 2026**.

Recommended earliest execution: **March 27, 2026**.

## Scope

1. Web gains tracker with year/coin/wallet filters.
2. Wallet-separated 1099-B export workflow.
3. Hypothetical sale forecasting with lot-level drill-down.
4. Explicit 2025+ IRS wallet-separation guidance and warnings.
5. Lightweight saved presets and recent export history.

## Why Feature-18 Comes Early

This product exists primarily to support tax reporting and forecasting. A web app that ships portfolio cards before tax workflows would miss the main operator value. Imports can follow as a day-2 web feature because the TUI and CLI remain available as fallback.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WTX-001 | Web gains tracker | Fastest path to everyday tax visibility |
| WTX-002 | Wallet-separated 1099-B export | Critical 2025+ compliance-oriented workflow |
| WTX-003 | Sale forecasting | High-value planning workflow for desktop and mobile |
| WTX-004 | Policy guidance + warnings | Prevents misuse of convenience flows |
| WTX-005 | Presets + recent history | Speeds repeated operator workflows |

## Risk Controls

1. Tax logic divergence risk
   Control: compare web outputs directly against existing Python calculator outputs.
2. Wallet-separation confusion risk
   Control: make wallet scope explicit and required by default for 2025+ flows.
3. Mobile oversimplification risk
   Control: provide summary-first mobile views with desktop drill-down into lots.

## Definition of Done

- Gains tracker, 1099-B export, and forecast flows are usable from the web.
- Wallet-separated tax handling is first-class in the UI and API.
- CSV outputs remain practically compatible with downstream tax workflows.
- Web tax results match the current Python core exactly.

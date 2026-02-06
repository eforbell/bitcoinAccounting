# Feature 6: Fiat Currency Tracking

## Overview

Add fiat (USD, EUR, stablecoins) deposit and withdrawal tracking to exchange CSV
importers. The system currently filters all imports to BTC-only, silently dropping
fiat flowing in and out of exchanges. This captures those records for complete
cash-flow visibility.

## Problem Statement

When importing exchange CSVs, USD deposits (ACH transfers, wires) and USD
withdrawals (back to bank) are filtered out. This means the ledger has no record
of fiat entering or leaving exchanges — only the BTC trades that happen in between.

For exchanges like Kraken and Gemini that include fiat rows in their exports, the
data is right there but gets dropped by the BTC-only filter.

## Solution

Modify 5 exchange parsers to pass fiat deposits/withdrawals through alongside BTC
transactions:

- **Kraken** — Remove BTC filter from deposit/withdrawal handlers
- **Swan** — Add "USD Deposit" handler (currently returns None)
- **River** — Add "Cash Deposit" handler to Account Activity parser
- **Gemini** — Add Symbol='USD' to xlsx filter
- **Coinbase Pro** — New importer class for Coinbase Pro export format (paired match/fee rows, trade grouping by trade_id)

No changes to Strike (BTC-only platform), Cash App (BTC gain/loss export only),
or standard Coinbase (existing importer unchanged until export format confirmed).

## Scope

### In Scope
- Shared FIAT_CURRENCIES constant (USD, EUR, GBP + stablecoins)
- Fiat deposit/withdrawal parsing for 4 existing exchanges + 1 new parser
- Trade filtering unchanged (BTC must be on one side)
- Documentation updates

### Out of Scope
- Exchange fiat balance reconciliation
- Cash flow reporting
- Fiat-to-fiat trade tracking
- New exchange parsers

## Architecture

One new file: `src/python/imports/exchanges/coinbase_pro.py` for the Coinbase Pro
importer. Changes to existing parsers in `src/python/imports/exchanges/` and shared
helper in `src/python/imports/base.py`. Database layer untouched — already
currency-agnostic.

## User Stories

| ID | Title | Priority |
|----|-------|----------|
| FIAT-000 | Add FIAT_CURRENCIES constant and is_fiat() helper | 1 |
| FIAT-001 | Kraken fiat deposits and withdrawals | 2 |
| FIAT-002 | Swan USD deposits | 3 |
| FIAT-003 | River cash deposits | 4 |
| FIAT-004 | Gemini xlsx USD credit/debit | 5 |
| FIAT-005 | Coinbase Pro importer class | 6 |
| FIAT-006 | Documentation update | 7 |

## Key Design Decisions

1. **Default-on**: No --include-fiat flag. Fiat captured automatically.
2. **Stablecoins = fiat**: USDC, GUSD, BUSD treated as fiat for deposit/withdrawal.
3. **Trade filter unchanged**: BTC must be on one side. No altcoin-to-altcoin trades.
4. **No database changes**: import_transactions() accepts any buy_curr/sell_curr string.

## Success Criteria

- [ ] Kraken USD/EUR deposits and withdrawals imported from CSV
- [ ] Swan USD deposits imported instead of skipped
- [ ] River Cash Deposits imported from Account Activity CSV
- [ ] Gemini xlsx USD credits/debits imported
- [ ] Coinbase Pro trades, deposits, and withdrawals imported (new parser)
- [ ] All existing BTC import tests still pass unchanged
- [ ] Altcoin deposits/withdrawals still filtered (only fiat + BTC pass through)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Coinbase Pro trade pairing complexity | Medium | Medium | Multi-fill orders create many match rows per trade_id — must handle variable row counts |
| Stablecoin set incomplete | Low | Low | FIAT_CURRENCIES is a frozenset, easy to extend |

## Timeline

- **Stories**: 7
- **Complexity**: Low-Medium (filter modifications + small handlers)
- **Dependencies**: Feature 5 complete (merged)

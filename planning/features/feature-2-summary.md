# Feature 2: Bitcoin Portfolio Visualizations

**Status**: Planned
**Branch**: `feature/bitcoin-visualizations`
**Stories**: VIZ-001 through VIZ-006 (6 stories, last one optional)

## Summary

Generate compelling visual insights into your Bitcoin accumulation strategy with a focus on the "Personal Orange Plot" - a Saylor-style visualization showing your BTC purchases overlaid on historical BTC-USD price data.

### Goals
- Make your Bitcoin strategy tangible and shareable (PNGs)
- Show purchase discipline and DCA effectiveness at a glance
- Visualize custody sovereignty progress
- Leverage existing query infrastructure (no new database queries)
- Smart defaults with power-user configurability

## The Star Feature: Personal Orange Plot 🧡

Inspired by Michael Saylor's Strategy orange plot, but for your personal stack:
- **BTC-USD price history** as thick orange line (yfinance data)
- **Your purchases** as large orange dots (size proportional to BTC amount)
- **Your sales** as green dots (back to greenbacks)
- **Cost basis overlay** as dashed blue line (optional, using existing BasisCalculator)
- **Summary stats** in subtitle: Total invested, current value, unrealized gain

## Supporting Visualizations

1. **Balance Growth Chart**
   - Cumulative BTC balance over time
   - Area fill shows your growing stack
   - Milestone markers (0.1 BTC, 1 BTC, 10 BTC, etc.)

2. **Custody Breakdown** (Stacked Area)
   - Self-custodied (green) vs Custodial (orange) vs Multisig (blue)
   - Shows your journey toward self-sovereignty
   - "Self-Sovereignty Index" in subtitle

## CLI Usage

```bash
# Generate all charts with all-time data
btc_viz

# Year-to-date only
btc_viz --range ytd

# Last 5 years
btc_viz --range 5y

# Just the orange plot
btc_viz --chart orange

# Custom date range
btc_viz --start-date 2020-01-01 --end-date 2023-12-31

# Output to specific directory
btc_viz --output ~/Desktop/bitcoin-report/

# Use logarithmic scale
btc_viz --log-scale

# Optional: Generate PDF report (VIZ-006)
btc_viz --pdf
```

## Tech Stack

- **yfinance** (new): Fetch BTC-USD price history from Yahoo Finance
- **matplotlib** (existing): Chart generation
- **pandas** (existing): Data manipulation
- **reportlab** (optional): PDF generation for VIZ-006

## File Structure

```
src/python/viz/
├── __init__.py              # Exports chart classes
├── config.py                # VizConfig dataclass
├── data_fetcher.py          # PriceDataFetcher (yfinance wrapper)
├── orange_plot.py           # OrangePlot class (THE star)
├── balance_chart.py         # BalanceChart class
├── custody_chart.py         # CustodyChart class
└── report.py                # OPTIONAL: PDF report generator

src/scripts/
└── btc_viz                  # CLI script

output/viz/                  # Default output directory (gitignored)
├── btc_orange_plot_2026-01-28.png
├── btc_balance_2026-01-28.png
└── btc_custody_2026-01-28.png
```

## User Stories Breakdown

| Story | Title | Priority | Complexity |
|-------|-------|----------|------------|
| VIZ-001 | Infrastructure & price data fetching | 1 | Medium |
| VIZ-002 | Orange Plot (star feature!) | 2 | High |
| VIZ-003 | Balance growth chart | 3 | Low |
| VIZ-004 | Custody breakdown | 4 | Medium |
| VIZ-005 | CLI script & docs | 5 | Medium |
| VIZ-006 | PDF report (optional) | 6 | Medium |

**Estimated effort**: 5-6 stories, ~2-3 weeks with testing

## Design Decisions

### Date Ranges
- **Presets**: `ytd`, `1y`, `5y`, `all` (default)
- **Custom**: `--start-date` and `--end-date` flags
- **Smart defaults**: From first transaction to today

### Chart Styling
- **Orange theme**: Primary color for BTC (matching Bitcoin branding)
- **Green accents**: Self-custody, sales (greenbacks)
- **Blue**: Cost basis, multisig
- **300 DPI**: Print quality
- **10x6 inches**: Standard presentation size

### Data Sources (All Existing!)
- Purchases/Sales: `TradeQuery.get_trades('BTC')`
- Balance: `BalanceCalculator.get_balance('BTC')`
- Custody: Join ledger with wallets table
- Cost Basis: `BasisCalculator.get_avg_purchase_price('BTC')`
- BTC-USD Price: yfinance (new, but simple)

### Price Data Caching
- Cache to `~/.cryptoaccounting/cache/btc_prices.parquet`
- Only fetch new dates (incremental updates)
- Fallback to cached data if API fails

## Future Enhancements

- Multi-coin support (ETH, other assets)
- Interactive Plotly charts (hover for transaction details)
- DCA simulation: "What if I had bought $X/week since 2020?"
- Performance dashboard (IRR, Sharpe ratio, max drawdown)
- Comparison overlay with MicroStrategy, Tesla holdings
- Tax-year specific views for IRS reporting
- Web dashboard with live updates

## Success Metrics

- [ ] Generate orange plot in < 5 seconds for 5 years of data
- [ ] Charts render correctly with 1 transaction, 100 transactions, 1000+ transactions
- [ ] Clear error messages for edge cases (no data, API failure)
- [ ] Visual appeal: Users want to share their orange plot on social media
- [ ] Utility: Charts provide actionable insights about accumulation strategy

## Why This Matters

Bitcoin accumulation is a long game. Visualizations:
1. **Make progress tangible** - See your stack grow
2. **Validate your strategy** - Did DCA work? Is cost basis improving?
3. **Motivate discipline** - The orange plot rewards consistent accumulation
4. **Shareable proof** - Show your conviction (or share anonymously)
5. **Tax prep helper** - Visual summary for accountant review

The orange plot, in particular, is an **emotional** visualization. It's your personal Bitcoin journey, overlaid on the most important financial chart of the 21st century.

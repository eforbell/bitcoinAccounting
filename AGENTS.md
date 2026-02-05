# Agent Learnings

## For python develpment, always prefer a local virtualenvs over the system python interpreter!

## Python 3.9 Compatibility

**Issue**: Python 3.9 doesn't support `|` union syntax for type hints (e.g., `str | None`)

**Solution**: Add `from __future__ import annotations` at the top of all files using modern type hint syntax. This enables PEP 563 postponed evaluation of annotations, making the `|` syntax work on Python 3.9.

**Files affected**: All files in `src/python/db/`

## Type Checking with Optional Dependencies

**Issue**: `mypy --strict` flags optional dependencies like psycopg2 as missing when type stubs aren't installed

**Solution**: Use `TYPE_CHECKING` pattern to conditionally import for type checking only:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg2
else:
    try:
        import psycopg2
    except ImportError:
        psycopg2 = None  # type: ignore[assignment]
```

This allows mypy to see the types during checking while handling runtime ImportError gracefully.

## SQLite Row Factory

**Pattern**: To get column names in query results, set `row_factory`:

```python
connection = sqlite3.connect(db_path)
connection.row_factory = sqlite3.Row  # Enables dict(row) conversion
```

This allows treating rows as dictionaries instead of tuples.

## Named Placeholders for Cross-Database Compatibility

**Decision**: Use `:named` placeholder syntax instead of `%s` (psycopg2) or `?` (sqlite3)

**Rationale**: Both psycopg2 and sqlite3 support named parameters with dictionary arguments, avoiding the need for separate query formats per backend.

```python
# Works on both backends
backend.execute("SELECT * FROM ledger WHERE coin = :coin", {"coin": "BTC"})
```

## Database Abstraction Interface Design

**Pattern**: Hide cursor management inside backend methods, return data structures directly:

- `execute()` → `list[dict]`
- `execute_one()` → `dict | None`
- `execute_scalar()` → `Any`

This provides a cleaner interface than exposing cursors to calling code.

## SQLite Schema Auto-Creation

**Pattern**: Automatically create schema tables on backend initialization for convenience:

```python
class SqliteBackend:
    def __init__(self, db_path=None, auto_create_tables=True):
        # ... connect to database ...
        if auto_create_tables:
            create_tables(self)
```

**Benefit**: Users don't need to manually run DDL scripts - tables are created on first use.

**Testing**: Set `auto_create_tables=False` in tests that create custom schemas to avoid conflicts.

## SQLite Type Mappings from PostgreSQL

- `SERIAL4` → `INTEGER PRIMARY KEY` (auto-increments without AUTOINCREMENT keyword)
- `VARCHAR(n)` → `TEXT`
- `FLOAT8`/`NUMERIC`/`DOUBLE PRECISION` → `REAL`
- `TIMESTAMP` → `TEXT` (store as ISO 8601: 'YYYY-MM-DD HH:MM:SS')
- `BOOLEAN` → `INTEGER` (0/1)

## CREATE TABLE IF NOT EXISTS

**Pattern**: Always use `IF NOT EXISTS` for idempotent DDL:

```sql
CREATE TABLE IF NOT EXISTS ledger (...);
```

This allows `create_tables()` to be called multiple times safely without errors.

## Cross-Database Query Compatibility

**Challenge**: Date/time functions differ significantly between SQLite and PostgreSQL:

- PostgreSQL: `EXTRACT('year' FROM date)`, `DATE_PART('minute', diff)`
- SQLite: `CAST(strftime('%Y', date) AS INTEGER)`, `julianday()` for differences

**Solution**: Use backend type detection with separate SQL generation methods:

```python
from ..sqlite import SqliteBackend

if isinstance(self.backend, SqliteBackend):
    query = self._get_sqlite_query()
else:
    query = self._get_postgres_query()
```

**Benefit**: Maintains identical semantics across backends while using each database's native functions for optimal performance.

## SQLite Date Calculations

**julianday() for time differences**: SQLite's `julianday()` returns fractional days since 4714 BC. Multiply by 1440 (minutes per day) to get minute-level precision:

```sql
-- Get minute difference between two timestamps
ABS((julianday(date) - julianday(:price_date)) * 1440)
```

This enables fuzzy date matching: find the price on the same calendar day with the smallest time difference.

## Query Class Pattern with Dependency Injection

**Pattern**: Create query classes that accept backend instances:

```python
class PriceLookup:
    def __init__(self, backend: DatabaseBackend) -> None:
        self.backend = backend
```

**Benefits**:
- Testable: can inject in-memory backend for fast tests
- Flexible: works with any backend implementation
- Composable: query classes can depend on other query classes

## COALESCE for NULL Handling in Aggregate Queries

**Pattern**: Use `COALESCE` to handle NULL results from aggregate functions like `SUM()`:

```sql
SELECT COALESCE(SUM(buy), 0) - COALESCE(SUM(sell), 0) AS balance
```

**Why**: When no rows match, `SUM()` returns NULL rather than 0. COALESCE converts NULL to 0 for arithmetic.

**Design Decision**: Balance functions return `0.0` (not `None`) for empty results. This matches accounting semantics where "no transactions" means "zero balance", not "unknown balance". Use `None` for lookups where data is truly missing (like price lookups).

## CASE Expressions for Perspective-Based Queries

**Pattern**: Use CASE expressions to calculate values from the perspective of a specific coin in buy/sell transactions:

```sql
SELECT
    CASE
        WHEN buy_curr = :coin THEN buy
        WHEN sell_curr = :coin THEN -sell
    END AS to_quantity,
    CASE
        WHEN buy_curr = :coin THEN sell / buy
        WHEN sell_curr = :coin THEN buy / sell
    END AS price
FROM ledger
WHERE (buy_curr = :coin OR sell_curr = :coin)
```

**Key Insights**:
- Use negative values to indicate direction (sell = negative quantity, buy = positive)
- Price calculation depends on perspective: always `counter_amount / coin_amount`
- CASE expressions allow pivoting transaction data to a single coin's point of view
- This pattern works across both SQLite and PostgreSQL without modification

## Return Types for Collections

**Pattern**: Query methods that return multiple results should return empty list `[]` when no data found, not `None`:

```python
def get_trades(self, coin: str) -> list[dict[str, Any]]:
    results = self.backend.execute(query, {"coin": coin})
    return [dict(row) for row in results]  # Returns [] if no results
```

**Design Decision**:
- Return `None`: when looking up a single optional value (e.g., price lookup, date lookup)
- Return `[]`: when returning a collection/list of items (e.g., trades, transactions)
- Return `0.0`: when aggregating values where zero is meaningful (e.g., balance, sum)

## Type Hints for Generic Collections in Strict Mode

**Issue**: `mypy --strict` requires type parameters for generic types like `dict` and `list`

**Solution**: Always specify generic parameters:

```python
# Wrong (fails strict mode)
def get_trades(self, coin: str) -> list[dict]:
    ...

# Correct
def get_trades(self, coin: str) -> list[dict[str, Any]]:
    ...
```

**Required imports**: `from typing import Any` when using `dict[str, Any]`

## Dependency Injection for Composed Query Classes

**Pattern**: Query classes that depend on other query classes should accept optional dependencies via constructor:

```python
class TradeQuery:
    def __init__(
        self,
        backend: DatabaseBackend,
        price_lookup: PriceLookup | None = None
    ) -> None:
        self.backend = backend
        if price_lookup is None:
            price_lookup = PriceLookup(backend)
        self.price_lookup = price_lookup
```

**Benefits**:
- Testability: Can inject mock PriceLookup for isolated testing
- Flexibility: Caller can provide custom implementation if needed
- Convenience: Auto-creates dependency if not provided (zero-config for simple use)

**Design Decision**: Always provide default None and auto-create in constructor. This balances testability with ease of use.

## Floating-Point Comparison in Tests

**Issue**: Direct equality checks fail for floating-point arithmetic due to precision errors:

```python
assert trade['unit_cost'] == 49500.0  # FAILS: 49500.00000000001 == 49500.0
```

**Solution**: Use `pytest.approx()` for floating-point comparisons:

```python
assert trade['unit_cost'] == pytest.approx(49500.0)
assert trade['total_cost'] == pytest.approx(25200.0)
```

**When to use**: Any test assertion involving calculated float values (prices, costs, balances with division/multiplication). Not needed for integer comparisons or exact float literals stored directly.

## Cross-Currency Cost Calculations

**Pattern**: When calculating costs across different currencies, chain lookups to convert:

```python
# Trade: BTC bought with EUR, need cost in USD
# Step 1: Get EUR/BTC price from trade data
eur_per_btc = trade['price']  # From trade record

# Step 2: Lookup EUR/USD conversion rate
eur_to_usd = price_lookup.get_price('EUR', 'USD', trade_date)

# Step 3: Calculate USD cost
if eur_to_usd is not None:
    usd_per_btc = eur_per_btc * eur_to_usd
    total_cost = usd_per_btc * abs(quantity)
else:
    usd_per_btc = None
    total_cost = None
```

**Key Insights**:
- Always use `abs(quantity)` for total_cost calculation (cost is always positive, even for sells)
- Propagate None through calculations: if any price lookup fails, set all derived values to None
- Store the actual price date used for conversion (`cost_curr_quote_date`) for audit trails
- Direct trades in the target currency skip the lookup (e.g., USD trade with USD cost_currency)

## Weighted Average Calculations

**Pattern**: Calculate weighted average price by summing cost-weighted quantities:

```python
# Filter to valid purchases (quantity > 0, unit_cost not None)
purchases = [t for t in trades if t["quantity"] > 0 and t["unit_cost"] is not None]

# Calculate weighted average
total_cost: float = sum(t["unit_cost"] * t["quantity"] for t in purchases)
total_quantity: float = sum(t["quantity"] for t in purchases)
avg_price: float = total_cost / total_quantity
```

**Key Insights**:
- Filter out None values BEFORE aggregation - don't let None propagate into sum()
- Filter to purchases only (quantity > 0) - sales have negative quantity and should be excluded
- Return None when no valid purchases exist (not 0.0) - None indicates "no data", not "zero cost"
- Explicit type annotations on intermediate variables help mypy --strict infer return type correctly

## Mypy Strict Mode with Generator Expressions

**Issue**: `mypy --strict` can't infer return type from division of sum() generator expressions:

```python
# Fails strict mode: "Returning Any from function declared to return Optional[float]"
return sum(trade["unit_cost"] * trade["quantity"] for trade in purchases) / sum(...)
```

**Solution**: Add explicit type annotations for intermediate values:

```python
total_cost: float = sum(trade["unit_cost"] * trade["quantity"] for trade in purchases)
total_quantity: float = sum(trade["quantity"] for trade in purchases)
avg_price: float = total_cost / total_quantity
return avg_price
```

**Why**: Mypy can't infer that dictionary access returns float/int from generator expressions. Explicit annotations eliminate the ambiguity.

## Income Transactions Schema Pattern

**Pattern**: Interest Income and Dividend transactions use specific field patterns in the ledger table:

```python
{
    'trans_type': 'Interest Income',
    'buy_curr': 'BTC',          # The coin received
    'buy': 0.001,               # Amount received
    'sell_curr': '',            # Empty string for income (no counter-currency)
    'sell': 0.0,                # Zero for income (nothing sold)
}
```

**Key Insights**:
- Interest and dividend income are both recorded with trans_type = 'Interest Income'
- sell_curr is empty string (not NULL) and sell is 0.0 for income transactions
- Only buy_curr and buy fields contain meaningful data
- get_dividend_cost() and get_interest_income() query the same data (functionally identical)
- Both functions are kept separate for API compatibility with PostgreSQL stored procedures

## Backend Abstraction Refactoring

**Critical Rule**: Raw SQL queries passed to backend.execute() are NOT transformed between databases

**Pattern**: Always use query class abstractions when available. If raw SQL has database-specific syntax, create a new query class method.

**Examples of database-specific SQL to avoid**:
- PostgreSQL: `date::date`, `information_schema.tables`
- SQLite: `sqlite_master`, different date functions

**Solution**: Use existing query classes (PriceLookup, TradeQuery, BalanceCalculator, etc.) or create new methods in query classes with backend type detection.

## DateTime Handling Across Backends

**Issue**: SQLite stores timestamps as TEXT (ISO 8601 strings), PostgreSQL returns datetime objects

**Pattern**: Always parse dates when processing query results:

```python
if isinstance(date_value, str):
    date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
```

**Where this is needed**:
- Processing results from TradeQuery, IncomeQuery
- FIFO calculations that compare dates
- Any date arithmetic or comparisons

## Test Migration from Mocks to Real Data

**Old pattern** (don't use):
```python
self.mock_cursor.fetchall.side_effect = [(data1,), (data2,)]
```

**New pattern** (correct):
```python
backend = SqliteBackend(':memory:', auto_create_tables=True)
crypto = CryptoAccounts(backend=backend)
crypto.execute_trade(...)  # Insert real data
```

**Benefits**:
- Tests actual database behavior, not mocks
- Catches SQL errors and type conversion issues
- Works identically for SQLite and PostgreSQL backends

## PostgreSQL to SQLite Migration Tool

**Pattern**: Use a MigrationResult class to track migration progress and verification:

```python
class MigrationResult:
    def add_table_result(self, table: str, source_count: int, migrated_count: int) -> None:
        """Track row counts for verification."""

    def verify(self) -> bool:
        """Verify all source counts match migrated counts."""

    def summary(self) -> str:
        """Generate human-readable summary."""
```

**Key Insights**:
- Convert PostgreSQL datetime objects to ISO 8601 strings during migration
- Convert PostgreSQL Decimal objects to float for SQLite compatibility
- SQLite parameter binding cannot handle Decimal types - must convert to float
- Use `force` flag to handle existing file (default: abort if exists)
- Use `dry_run` flag to preview migration without writing data
- Clean up partial SQLite file on migration failure
- Skip migration with warning if PostgreSQL ledger is empty
- Verify row counts after migration to ensure data integrity

## Type Conversion for Migration (PostgreSQL to SQLite)

**Critical Issue**: PostgreSQL returns Decimal objects for NUMERIC/FLOAT8 columns, but SQLite parameter binding cannot handle Decimal types. This causes "Error binding parameter :name - probably unsupported type" errors.

**Pattern**: Convert all PostgreSQL-specific types to SQLite-compatible types:

```python
from decimal import Decimal

def convert_value_for_sqlite(value: Any) -> Any:
    """Convert PostgreSQL types to SQLite-compatible types."""
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(value, Decimal):
        return float(value)
    return value
```

**Apply to all row values before inserting into SQLite**:

```python
def convert_row_timestamps(row: dict[str, Any]) -> dict[str, Any]:
    return {key: convert_value_for_sqlite(value) for key, value in row.items()}
```

**Types that need conversion**:
- `datetime` → ISO 8601 string (`'2025-01-28 10:30:00'`)
- `Decimal` → float (PostgreSQL NUMERIC/FLOAT8 columns)
- `str`, `int`, `float`, `bool`, `None` → unchanged (compatible with both)

## CLI Script Pattern

**Pattern**: Use argparse for command-line arguments with descriptive help:

```python
#!/usr/bin/env python3
import argparse
import _bootstrap  # Adds src/python to sys.path

parser = argparse.ArgumentParser(description="...")
parser.add_argument('--output', '-o', help='...')
parser.add_argument('--dry-run', '-n', action='store_true', help='...')
parser.add_argument('--force', '-f', action='store_true', help='...')
```

**Best Practices**:
- Include long and short flag variants (--output, -o)
- Use `action='store_true'` for boolean flags
- Return exit codes: 0 for success, 1 for errors
- Print errors to stderr with `file=sys.stderr`

## CLI Script Integration Testing

**Pattern**: Test CLI script functionality by testing the underlying CryptoAccounts methods with in-memory SQLite:

```python
def test_balance_script():
    backend = SqliteBackend(':memory:', auto_create_tables=True)
    crypto = CryptoAccounts(backend)

    # Test the methods used by the script
    crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')
    balance = crypto.get_balance('BTC')
    assert balance == 0.5
```

**Why not subprocess scripts directly?**:
- Many scripts have interactive prompts (input/PromptSession)
- Testing methods provides better isolation and error messages
- Faster execution (no process spawning overhead)
- Same code paths exercised (scripts just call these methods)

## Understanding CryptoAccounts API Return Types

**Common return types that differ from typical patterns**:

1. **get_transactions(coin: str) → tuple**:
   - Returns `(headers_list, transactions_list)`
   - `headers_list`: List of column names
   - `transactions_list`: List of transaction dicts
   - Example: `headers, txs = crypto.get_transactions('BTC')`

2. **get_sales_for_1099b(coin, tax_year, wallet) → tuple**:
   - Returns `(form_b_rows, summary_rows)`
   - Two different formats for different export types
   - Both are lists of dicts

3. **forecast_capital_gains_fifo(coin, quantity, sale_price_usd, wallet) → tuple**:
   - Returns complex tuple structure (not dict)
   - Just verify it returns something (implementation may change)

4. **get_wallets(active_only=False) → list**:
   - May return empty list if wallets table not populated
   - Wallets can exist implicitly in ledger without wallets table entry

5. **get_wallet_balance(coin, wallet) → float**:
   - Note parameter order: `coin` first, then `wallet`
   - Different from get_balance_by_account(coin, account)

6. **add_price_pair(pair_date, to_curr, from_curr, price)**:
   - Parameter is `pair_date`, not `date`
   - Use named parameters for clarity

## Fee Handling in Ledger

**Critical Understanding**: Fees are tracked separately but NOT deducted from balance calculations

**Pattern**: When recording a trade with fees:

```python
crypto.execute_trade(
    buy=0.1, buy_curr='BTC',
    sell=5000, sell_curr='USD',
    fee=0.0001, fee_curr='BTC'
)
# Balance will be 0.1 BTC, not 0.0999
# The fee field is for tracking/reporting only
```

**Why**: The buy/sell amounts represent the actual amounts exchanged. Fees are recorded for tax and reporting purposes but are already reflected in the buy/sell amounts or handled separately depending on the transaction type.

**Example from tests**:
```python
# Transfer with fee: sell includes transferred amount AND fee
withdrawal_amount = transferred_amount + fee_amount
```

## Testing CLI Scripts with SQLite Backend

**Success criteria for SQL-011**:
- All 16 CLI scripts' core functionality verified
- Tests use real in-memory SQLite database
- No mocking of database calls
- Each test class covers one script's primary operations
- Tests verify method calls succeed without errors

**Coverage approach**:
- Read-only scripts: Verify method executes and returns expected type
- Write scripts: Verify data persists correctly after operation
- Complex scripts: Verify primary workflow completes successfully

**Total test count**: 19 integration tests covering 16 CLI scripts

## User Documentation Best Practices

**Pattern**: When documenting a new feature that replaces or supplements existing functionality, organize documentation to guide users to the best path first:

**Structure for dual-option features**:
1. **Intro**: Update project description to be option-neutral
2. **Quick Start**: Lead with the simpler/recommended option
3. **Alternative Options**: Document other approaches clearly labeled
4. **Choosing Between Options**: Explicit comparison with use cases
5. **Migration Guide**: Step-by-step migration from old to new approach
6. **Troubleshooting**: Common issues specific to each option

**SQL-012 Example**: SQLite vs PostgreSQL documentation
- Lead with SQLite (zero-config, easier for most users)
- Include PostgreSQL as "Option 2: For Advanced Users"
- Provide explicit "Choosing SQLite vs PostgreSQL" section
- Include complete migration guide with verification steps
- Add troubleshooting for both backends

**Environment Variable Documentation**:
- Group by purpose (database selection, SQLite config, PostgreSQL config)
- Show default values explicitly
- Include example values for clarity
- Explain when each variable is required vs optional

**Migration Documentation Pattern**:
1. Preview command (--dry-run)
2. Actual migration command
3. Verification steps (numbered list)
4. Rollback or troubleshooting if issues found
5. Permanence step (update shell profile)

**Troubleshooting Section Pattern**:
- Use clear symptom headers ("Database is locked", not "Error handling")
- Include **Cause** and **Solution** subsections
- Provide copy-paste ready command examples
- Link related concepts where appropriate

**Key Principle**: Optimize for user success on first attempt. Make the easiest path obvious, while documenting advanced options completely.

## Cross-Currency Trade Cost Calculations - CRITICAL

**Anti-Pattern**: Using raw SQL queries that only handle USD/stablecoins directly:

```sql
-- ❌ WRONG - Only counts USD and stablecoins, sets other currencies to 0
SELECT SUM(CASE
    WHEN sell_curr = 'USD' THEN sell
    WHEN sell_curr IN ('USDC', 'GUSD', 'BUSD', 'USDT') THEN sell
    ELSE 0  -- This causes massive underreporting!
END) as usd_value
FROM ledger WHERE trans_type = 'Trade' AND buy_curr = :coin
```

**Problem**: Trades in EUR, GBP, or other crypto are counted as $0 cost, drastically underreporting cost basis.

**Example Impact**:
- Kraken: Should be $35,033 → Incorrectly shows $7,193 (79% underreported)
- Total basis: Should be $44,141 → Incorrectly shows $41,151 (7% underreported)

**Correct Pattern**: Use `TradeQuery.get_trade_cost()` which does proper price lookups:

```python
# ✅ CORRECT - Uses price lookup for all currencies
all_trades = crypto.trade_query.get_trade_cost(coin, cost_currency='USD')
exchange_purchases = [
    t for t in all_trades
    if t.get('exchange') == exchange and t.get('quantity', 0) > 0
]
total_usd_spent = sum(
    t['total_cost'] for t in exchange_purchases
    if t.get('total_cost') is not None
)
```

**How it works**:
- USD trades → use direct value
- Stablecoins → treat as 1:1 USD
- EUR/GBP/other fiat → look up exchange rate from `pair_price` table
- Other crypto → look up price in USD from `pair_price` table

**Critical for**:
- `exchange_liquidity` script - shows cost basis by exchange
- `export_1099b` script - generates tax reports
- Any cost basis calculations

**Always**: Use query class abstractions (`TradeQuery`, `BasisCalculator`) instead of raw SQL for cost calculations. The query classes handle cross-currency conversion correctly.

## Visualization Package Patterns (VIZ-001)

### Package Structure
- Visualization code lives in `src/python/viz/` (parallel to `db/` package)
- Follows same patterns as db package: `__init__.py` exports public API, implementation in submodules

### Optional Dependencies with TYPE_CHECKING
```python
if TYPE_CHECKING:
    import pandas as pd
    import yfinance as yf
else:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        pd = None  # type: ignore[assignment]
        yf = None  # type: ignore[assignment]
```
This pattern allows mypy to see types while handling missing dependencies gracefully at runtime.

### Price Data Caching Strategy
- Cache location: `~/.cryptoaccounting/cache/btc_prices.parquet`
- Format: Parquet (requires `pyarrow` or `fastparquet`)
- Strategy: Load cache → Fetch only missing dates → Merge with `pd.concat()` → Deduplicate → Save
- Graceful degradation: Use cached data with warning if API fails, error only if no cache available

### yfinance Integration
- Ticker: `yf.Ticker("BTC-USD").history(start, end)` for Bitcoin price data
- Column normalization: API returns 'Open', 'High', etc. - normalize to lowercase ('open', 'high')
- Expected columns: open, high, low, close, volume

### Testing Patterns
- Use temporary directories for cache in tests (`tempfile.TemporaryDirectory`)
- Mock yfinance with `@patch('src.python.viz.data_fetcher.yf.Ticker')`
- DataFrame comparisons: Use `pd.testing.assert_frame_equal(df1, df2, check_freq=False)` to ignore index frequency differences

## VIZ-002: Orange Plot (Personal Bitcoin Accumulation Visualization)

### Matplotlib Chart Generation
- Figure creation: `fig, ax = plt.subplots(figsize=(10, 6))` for presentation-ready charts
- Close figures after saving: `plt.close(fig)` to free memory and prevent warnings
- Save with high DPI: `fig.savefig(output_path, dpi=config.dpi, bbox_inches='tight')` for print quality
- Auto-format dates: `fig.autofmt_xdate()` nicely rotates and aligns date labels

### Scatter Plot Sizing
- Size parameter is in points^2, scale for visibility: `size = btc_amount * 500`
- Transparency helps with overlapping points: `alpha=0.6`
- Edge colors provide definition: `edgecolors="black", linewidth=0.5`
- `zorder=5` ensures scatter points appear above line plots

### Running Cost Basis Calculation
- Pattern: Iterate chronologically, maintain cumulative sums
- Formula: `running_basis = cumulative_cost / cumulative_btc`
- Skip None values: `if purchase["unit_cost"] is None: continue` before accumulation
- Sort by date first: `sorted(purchases, key=lambda t: t["date"])` to ensure correct order

### Date Range Resolution
- Preset strings ('ytd', '1y', '5y', 'all') vs tuple (start, end)
- 'ytd': Jan 1 of current year to now
- '1y': today minus 365 days
- '5y': today minus 5 years (1825 days)
- 'all': First transaction date to now (query ledger for min date)

### DataFrame Index Lookups
- Use `get_indexer([date], method='nearest')` to find closest date in price data
- Returns array of indices, access with `[0]` for single value
- Then use `.iloc[idx]` to retrieve the row/value

### Trade Data from Database
- TradeQuery.get_trade_cost() returns unit_cost based on trade currency
- Direct trades (trade_curr == cost_currency): unit_cost comes from trade price (sell/buy ratio)
- Cross-currency trades: unit_cost requires price lookup, may be None if unavailable
- Test missing prices: Use different currency (e.g., EUR trade, USD costs, no EUR-USD conversion)

### Chart Annotation and Summary Stats
- Calculate totals from purchase list: `sum(p["quantity"] for p in purchases)`
- Current value: `total_btc * latest_price`
- Unrealized gain %: `((current_value - total_invested) / total_invested) * 100`
- Include sign: `gain_sign = "+" if gain >= 0 else ""`
- Display in subtitle: Multi-line title with `\n` separator

### Color Palette (Bitcoin Theme)
- Orange (#FF9500): BTC price line, purchase markers (the "orange pill")
- Green (#34C759): Sales markers (returning to "greenbacks")
- Blue (#007AFF): Cost basis line (dashed)
- Black edges: Definition on scatter points

## VIZ-003: Balance Chart (Bitcoin Stack Growth Over Time)

### Area Chart with Fill
- Plot line and fill area simultaneously:
  ```python
  ax.plot(dates, balances, color='#FF9500', linewidth=2.5, label='BTC Balance')
  ax.fill_between(dates, balances, alpha=0.3, color='#FF9500', label='Accumulated BTC')
  ```
- `fill_between()` creates shaded area under curve
- Use `alpha=0.3` for semi-transparent fill that doesn't obscure data

### Cumulative Balance Calculation
- Pattern: Initialize at 0, iterate chronologically, sum quantities
- Add start point (date=start, balance=0) and end point (date=end, balance=final)
- This creates smooth line from origin to current date
- Sort trades by date BEFORE accumulation: `sorted(trades, key=lambda t: t['date'])`

### Milestone Markers (Horizontal Lines)
- Use `ax.axhline()` for horizontal reference lines
- Style: `linestyle=':'` (dotted), `alpha=0.5`, `color='gray'`
- Add text labels on right side: `ax.text(end_date, milestone, ' X.XX BTC', ha='left')`
- Standard Bitcoin milestones: 0.01, 0.1, 0.5, 1, 2, 5, 10, 21, 50, 100
- Only show milestones up to 110% of max balance

### Negative Balance Detection
- Check during calculation loop: `if balance < -0.00000001`
- Allow small negative values for floating point errors
- Issue warning with `warnings.warn(msg, RuntimeWarning)`
- Continue processing (don't fail) - negative balance may be data error but chart is still useful

### Single Transaction Edge Case
- Still creates valid chart: start point (0) → transaction point → end point (final)
- Results in simple 2-segment line
- No special handling needed with start/end point pattern

### Balance Data Structure
- List of dicts: `[{'date': datetime, 'balance': float}, ...]`
- Always sorted by date
- Include start point, all transaction points, and end point
- Makes plotting straightforward: extract to parallel lists

## VIZ-004: Custody Chart (Bitcoin Holdings by Custody Type)

### Stacked Area Charts
- Use `ax.stackplot()` for stacked areas:
  ```python
  ax.stackplot(
      dates,
      *[balances_by_type[ct] for ct in custody_types],
      labels=[...],
      colors=[...],
      alpha=0.8
  )
  ```
- Takes unpacked lists of values (one per custody type)
- Stacks from bottom to top in order provided
- Order matters: put most important (self-custodied) on bottom for visibility

### Wallet Metadata Integration
- JOIN ledger with wallets table: match ledger.exchange to wallets.wallet_id
- Graceful degradation: if wallets table empty/missing, all transactions marked as "unknown"
- Query pattern:
  ```python
  try:
      wallets = backend.execute("SELECT wallet_id, custody FROM wallets WHERE active = 1")
      # Build mapping dict
  except Exception:
      return {}  # No wallet data available
  ```

### Custody Type Normalization
- Accept various naming conventions: "self", "cold", "hardware" → "self-custodied"
- Accept "exchange", "hot" → "custodial"
- Accept "multi-sig", "collaborative" → "multisig"
- Use `.lower()` for case-insensitive matching
- Unknown/unrecognized types → "unknown" category

### Multi-dimensional Balance Tracking
- Data structure: `[{'date': datetime, 'self-custodied': float, 'custodial': float, 'multisig': float, 'unknown': float}, ...]`
- Update specific custody type balance on each transaction
- Initialize all custody types to 0.0 at start
- Copy current state on each transaction (snapshot)

### Filtering Empty Categories
- Before plotting, filter out custody types with zero final balance
- Check: `current_totals[ct] > 0.00000001` (allow for floating point errors)
- Single custody type case: stackplot works fine with single area (not truly "stacked")
- Zero balance across all types: raise ValueError (no data to plot)

### Self-Sovereignty Index
- Metric: percentage of holdings in self-custody
- Formula: `(self_custodied_balance / total_balance) * 100`
- Display in subtitle as motivational indicator
- Shows progress toward Bitcoin's core value proposition (self-sovereignty)

### Color Palette (Custody Theme)
- Green (#34C759): self-custodied (sovereignty, security)
- Orange (#FF9500): custodial (convenience, counterparty risk)
- Blue (#007AFF): multisig (collaborative security)
- Gray (#8E8E93): unknown (missing metadata)

### Legend with Current Balances
- Include current balance in each label: "Self-Custodied: 0.60000000 BTC"
- Use `.replace('-', ' ').title()` to format custody type names
- Position: "upper left" so it doesn't obscure data

## VIZ-005: CLI Script (btc_viz - Brings It All Together)

### Argparse CLI Pattern
- Use `argparse.ArgumentParser()` with `formatter_class=argparse.RawDescriptionHelpFormatter` for formatted epilog
- Mutually exclusive groups: `parser.add_mutually_exclusive_group()` for `--range` vs `--start-date`
- Action flags: `action="store_true"` for boolean flags like `--no-cost-basis`
- Choices validation: `choices=['ytd', '1y', '5y', 'all']` for enum-like arguments
- Type conversion: `type=int` for numeric arguments like `--dpi`

### Argument Validation
- Separate validation function: `validate_arguments(args)` after parsing
- Check logical constraints: `--start-date` requires `--end-date`
- Validate formats: `datetime.strptime(date_str, "%Y-%m-%d")` catches bad formats
- Check ranges: dates not in future, DPI between 72-600
- Raise `ValueError` with clear message on validation failure

### Date Range Resolution
- Convert preset strings to actual date tuples: "ytd" → (Jan 1, today)
- Custom dates: parse with `datetime.strptime()`, default end to `datetime.now()`
- Return union type: `str | tuple[datetime, datetime]` for flexibility
- Pass through to VizConfig which handles both formats

### Chart Generation Orchestration
- Loop through requested chart types: ["orange", "balance", "custody"]
- Try/except per chart: don't let one failure stop others
- Track generated charts: `dict[str, Path]` mapping chart type to output file
- Track errors separately: continue on error, report at end
- Print progress: "Generating orange plot..." with ✓/✗ indicators

### Summary Statistics
- Optional summary (don't fail if it errors)
- Query trades, calculate totals, get current price
- Display: date range, transaction counts, total BTC, total USD, current value, unrealized gain
- List generated chart paths with checkmarks
- Use separator lines (=====) for visual structure

### Exit Codes
- 0: Success (all requested charts generated)
- 1: Argument validation error
- 2: No transaction data
- 3: All chart generation failed
- 130: KeyboardInterrupt (Ctrl+C)

### Error Handling Strategy
- `ValueError`: Validation errors (exit 1)
- `RuntimeError` with "No Bitcoin transactions": No data (exit 2)
- `KeyboardInterrupt`: User cancelled (exit 130)
- Other exceptions: Unexpected error with traceback (exit 3)
- Partial success: Generate what we can, warn about failures, exit 0

### Module Imports in Scripts
- Add `src/python` to `sys.path`: `sys.path.insert(0, str(Path(__file__).parent.parent / "python"))`
- Use package imports: `from db import get_backend` (not `from src.python.db`)
- Add `from __future__ import annotations` for Python 3.9 compatibility with `|` union syntax

### Testing CLI Scripts
- Use `subprocess.run()` to invoke script (more realistic than importing)
- Test help flag: `--help` returns 0 and shows usage
- Test validation: invalid arguments return exit code 1
- Test empty data: returns appropriate error code
- Test success path: create test database, run script, verify output files exist
- Pass env vars: `env={"SQLITE_DB_PATH": str(db_path)}` to use test database

### Timezone Handling with yfinance
- **Critical Issue**: yfinance returns timezone-aware pandas DatetimeIndex (UTC)
- Database datetimes are timezone-naive (no timezone info)
- Comparison fails: "Invalid comparison between dtype=datetime64[ns, UTC] and datetime"
- **Solution**: Strip timezone from pandas index after fetching:
  ```python
  if price_data.index.tz is not None:
      price_data.index = price_data.index.tz_localize(None)
  ```
- Always do this immediately after fetching from yfinance
- Alternative would be to make all datetime objects timezone-aware, but that's more complex

### Import Compatibility Pattern
- Challenge: Code needs to work in two contexts:
  1. Tests: `from src.python.viz import BalanceChart`
  2. CLI: sys.path has src/python, imports `from viz import BalanceChart`
- **Solution**: Try/except imports:
  ```python
  try:
      from src.python.db.backend import DatabaseBackend
  except ModuleNotFoundError:
      from db.backend import DatabaseBackend  # type: ignore[import]
  ```
- Primary import (src.python) for tests, fallback for CLI
- Add `# type: ignore[import]` to fallback to satisfy mypy

## PDF Generation with ReportLab

**Pattern**: Use reportlab for multi-page PDF reports combining charts and text

```python
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

# Create canvas
c = canvas.Canvas(str(output_path), pagesize=letter)
page_width, page_height = letter

# Draw text
c.setFont("Helvetica-Bold", 24)
c.drawCentredString(width / 2, height - 2 * inch, "Title")

# Draw image (scaled to fit)
img = ImageReader(str(image_path))
img_width, img_height = img.getSize()
scale = min(max_width / img_width, max_height / img_height)
c.drawImage(str(image_path), x, y, img_width * scale, img_height * scale)

# New page
c.showPage()

# Save
c.save()
```

**Key learnings**:
- ImageReader handles PNG images from matplotlib
- Scale images to fit within margins: `scale = min(max_width / img_width, max_height / img_height)`
- Use `inch` unit for layout calculations (imported from reportlab.lib.units)
- Word wrapping: use `stringWidth()` to measure text and break lines manually
- Optional dependency: wrap imports in try/except, raise ImportError with installation instructions
- Multi-page layout: `showPage()` between pages
- Coordinate system: (0,0) is bottom-left, not top-left

## Multi-Sig as Self-Custody

**Decision**: When calculating self-sovereignty metrics, include both single-sig self-custody AND multisig

**Rationale**: Multisig is self-custody on steroids - even stronger sovereignty than single-sig cold storage. Even if a 3rd party holds one key in a quorum, the user still maintains control.

**Implementation**:
```python
total_self_custody = self_custodied + multisig
self_sovereignty_pct = (total_self_custody / total_btc) * 100
```

## IMP-008: River – Two-Format Parser Pattern

River ships two CSV exports that overlap in columns:
- **Account Activity** (21 cols) – superset; has `Reference Code`, `Transaction Type`, `Bitcoin Price Amount`
- **Bitcoin Activity** (8 cols) – subset; type must be inferred from `Tag` + sent/received pattern

**Detection order matters**: always check the superset markers first.  The subset check includes an explicit guard (`'transaction type' not in header`) so Account Activity files don't accidentally match as Bitcoin Activity.

**Withdrawal inference in Bitcoin Activity**: there is no type column — a withdrawal is identified as `Tag == '' AND Sent Currency == 'BTC' AND Sent Amount > 0`.

**Buy sell amount**: Account Activity provides `Total Amount` (sent + fee) directly; Bitcoin Activity requires computing `sent + fee` with a currency-match guard to avoid mixing a BTC fee into a USD sell total.

## IMP-003: import_csv CLI — Exchange Import Entry Point

### import_transactions Trade Gap
- `import_transactions()` in cryptoAccounts.py originally handled: Interest Income, Mining, Deposit, Withdrawal — but NOT Trade
- Added Trade elif branch using `getTradeQuery()` to complete the method
- All exchange parsers produce Trade transactions, so this was a prerequisite for the import pipeline

### CLI Script Structure
- Uses `import _bootstrap` (not raw sys.path manipulation) — consistent with simpler scripts like `balance`
- `--list` and `--format` are info-only commands: no FILE arg or DB access needed
- FILE is `nargs='?'` (optional positionally) so --list/--format work without it
- argparse converts `--withdraw-to` to `args.withdraw_to` automatically (hyphen → underscore)

### Exit Code Convention
- 0: success (including --list, --format, --help, empty file)
- 1: argument errors (missing FILE, file not found, unknown --source/--format parser)
- 2: parse errors (auto-detect failed, parse() exception, validation failure)
- 3: import errors (database write failure)

### Withdrawal Comment Limitation
- `getWithdrawQuery()` does NOT store the `comment` field — only Interest Income query includes comment
- The withdrawal review comment ("Review: Verify destination wallet") is set in the transaction dict but lost on DB insert
- The `exchange` field IS stored correctly (withdraw_to destination works as expected)

### Testing Strategy for CLI Scripts
- Subprocess tests: CLI flag behavior (help, list, error exits) — no DB needed
- Programmatic integration tests: register a test parser class, create temp CSV, exercise the full pipeline: parse → validate → detect_duplicates → import_transactions → query DB
- Test parser class defined at module level without @register; manually call `register(cls)` in setup_method after `clear_registry()`
- This avoids "already registered" errors across test methods

## IMP-009: Swan — DCA Platform Patterns

- Swan is Bitcoin-only DCA: no asset filtering needed (all rows are BTC)
- **Status filtering**: Real DCA platforms have Pending rows for in-flight ACH
  purchases. Filter by Status (case-insensitive) and silently drop Pending/Failed.
- **group field for analytics**: Set `group='DCA'` on all purchases. This field
  survives `import_transactions()` and is queryable downstream.
- Total (USD) includes fee — consistent with Coinbase's Total semantics. Fee is
  still tracked separately for tax reporting.

## IMP-010: Cash App — Data-Quality Warnings During Parse

- Cash App's Gain/Loss CSV omits cost basis for external wallet Receives.
  Both empty string and literal "0.00" represent this — check the parsed float,
  not the raw string.
- **warnings.warn() during parse()** is the right place for data-quality alerts
  that don't block import. The warning appears in CLI output and is testable
  with `pytest.warns(UserWarning)`.
- **Asserting NO warning was emitted**: use `warnings.catch_warnings()` +
  `simplefilter("error")` — any warning becomes an exception, failing the test.
- Tag the comment field with the issue text so the flag survives into the DB:
  `"Cost basis $0 - verify before tax filing"`.

## IMP-011: Gemini — Dual CSV + xlsx Dispatch

- **Detection and parse dispatch on extension**: `detect()` and `parse()` branch
  on `.xlsx` vs `.csv` extension. Each sub-path is fully independent — the CSV
  path is unchanged from its original implementation.
- **Dynamic column mapping for xlsx**: Gemini's xlsx has 30+ columns that vary
  by account holdings (per-asset Amount/Fee/Balance triplets). Never hardcode
  column indices. Build a `{header_lower: col_index}` dict from row 1 at runtime;
  missing columns silently resolve to 0.0 via a `_to_float(None)` helper.
- **Negative-amount convention**: Gemini stores Buy USD amounts and fees as
  negative (accounting: money leaving = negative). Apply `abs()` unconditionally
  to all amount fields in the xlsx path.
- **openpyxl quirks with Gemini exports**:
  - `load_workbook(read_only=True)` only returns 1 column because the file lacks
    a default style. Use the default `read_only=False`.
  - openpyxl emits `UserWarning: Workbook contains no default style` — this is
    harmless and expected for Gemini exports.
- **xlsx test fixtures**: Use openpyxl programmatically to create temp xlsx files
  in tests (`_make_xlsx` helper). Only include the minimal columns the parser
  reads — dynamic mapping means extras are ignored. Use `datetime` objects for
  Date cells so `_fmt_dt()` formats them correctly.
- Symbol filter (`BTCUSD` / `BTC`) is the primary row gate in xlsx, analogous
  to `base-asset == BTC` in the CSV path.

## WAL-001: Wallet Import Package Structure

- **Package organization**: `src/python/imports/` contains two subpackages:
  - `exchanges/` for exchange parsers (Coinbase, Kraken, etc.)
  - `wallets/` for wallet parsers (Ledger, Trezor, Sparrow, Coldcard)
- **Registration pattern**: Each subpackage has `__init__.py` that imports all
  parser modules to trigger registration via the `@register` decorator
- **Top-level imports**: `imports/__init__.py` imports both subpackages to ensure
  all parsers are registered when the imports package is loaded:
  ```python
  from . import exchanges  # noqa: F401, E402
  from . import wallets    # noqa: F401, E402
  ```
- **Lazy evaluation**: Parser modules are only imported when the imports package
  is imported, avoiding circular dependencies and enabling clean test isolation
- **source_type field**: Used to distinguish exchange parsers (`source_type='exchange'`)
  from wallet parsers (`source_type='wallet'`) in CLI output


## WAL-002: Ledger Live Importer

- **Ledger Live CSV format**: Operations export with 11 columns including:
  - Operation Date (datetime string), Currency, Operation Type (IN/OUT)
  - Amount (float), Fees (float), Hash (transaction ID)
  - Account Name, xpub (extended public key for account)
  - Cost Currency, Cost, Cost at Export (USD equivalent values)
- **Operation type mapping**: Ledger uses simple IN/OUT types
  - `IN` → Deposit (BTC received)
  - `OUT` → Withdrawal (BTC sent)
- **BTC-only filtering**: Multi-currency wallet, must filter on `Currency == 'BTC'`
  and skip all other assets (ETH, etc.)
- **Zero-amount transactions**: Skip transactions where parsed amount == 0
  (empty CSV cells or explicit zeros)
- **Withdrawal fee handling**: Apply `fee_curr = 'BTC' if fee > 0 else ''` pattern
  to avoid orphan currency labels on zero-fee withdrawals
- **Absolute value on withdrawals**: Amounts may come as negative in OUT operations,
  always apply `abs(value)` when setting sell amount
- **csv.DictReader.fieldnames type**: Returns `Sequence[str] | None`, not `list[str]`.
  Convert with `list(reader.fieldnames)` before passing to functions expecting list.
- **Wallet parser registration**: Import in `imports/wallets/__init__.py` with
  `from . import ledger  # noqa: F401` to trigger @register decorator


## WAL-002 Enhancement: --wallet-name Requirement

- **Semantic problem with wallet withdrawals**: Original design used
  `exchange='Ledger-Withdrawal'` placeholder for unspecified withdrawal
  destinations, creating ambiguity:
  - Looks like a wallet name (conflicts with user-named "Ledger" wallet)
  - Doesn't clearly signal "missing data" vs "actual destination"
  - For deposits, `exchange='Ledger'` (hardcoded) doesn't match user's naming
- **Solution**: Require `--wallet-name` parameter for wallet imports
  - Deposits (IN): `exchange=wallet_name` (user-specified, e.g., "MyLedger")
  - Withdrawals (OUT): `exchange=withdraw_to` or placeholder if unspecified
  - Placeholder still used for unknown withdrawals (could be wallet or exchange)
- **CLI validation**: import_csv checks `source_type == 'wallet'` and requires
  `--wallet-name` parameter, failing with exit code 1 if missing
- **BaseImporter.parse() signature change**:
  ```python
  def parse(self, file_path: str, wallet_name: str | None = None, 
            withdraw_to: str | None = None) -> tuple[list[str], list[dict]]
  ```
- **Backward compatibility**: Exchange parsers ignore wallet_name parameter
  (default None, not used in exchange logic)
- **PRD updates**: All wallet parser stories (WAL-002 through WAL-005) updated
  to specify parse() signature and --wallet-name requirement
- **Usage examples**:
  ```bash
  # Wallet import (required)
  import_csv --wallet-name Ledger ledger.csv
  
  # With withdrawal destination
  import_csv --wallet-name Ledger --withdraw-to Coldcard ledger.csv
  
  # Exchange import (wallet-name ignored)
  import_csv coinbase.csv
  ```


## WAL-003: Trezor Suite Importer

- **Trezor Suite CSV format**: Transaction export with 7 columns including:
  - Date (YYYY-MM-DD), Time (HH:MM:SS), Type (recv/sent/received/send)
  - Amount (float BTC), Fee (float BTC)
  - Address (destination/source), TX ID (transaction hash)
- **Date and Time combination**: Separate columns that must be combined:
  - If both present: `created_date = f"{date_str} {time_str}"`
  - If only Date: `created_date = date_str`
  - Pattern: gracefully handles missing Time column
- **Transaction type mapping**: Trezor uses recv/sent variants (case-insensitive)
  - `recv` or `received` → Deposit (BTC received)
  - `sent` or `send` → Withdrawal (BTC sent)
  - Type column is case-normalized with `.lower()` before matching
- **Detection heuristic**: Uses 'tx id' column as distinctive marker
  - Ledger uses 'hash', making 'tx id' + 'address' + 'date' a unique fingerprint
  - Avoids false positives with other wallet/exchange formats
- **Bitcoin-only**: Unlike Ledger, Trezor Suite's BTC export is single-currency
  - No currency filtering needed (unlike Ledger's multi-currency export)
  - All rows are BTC transactions by definition
- **Similarities to Ledger parser**: Same patterns apply:
  - Zero-amount filtering, zero-fee handling (`fee_curr=''`), abs() on withdrawals
  - wallet_name for deposits, withdraw_to for withdrawals
  - Review comment for unspecified withdrawal destinations
- **Test fixture**: 5 transactions covering recv, received, sent, send types with
  varying amounts and fees (including zero-fee withdrawals)
- **26 comprehensive tests**: Detection (4), parsing (17), registration (3), integration (2)
  - All tests pass, zero regressions on full suite (590 total tests)

## WAL-004: Sparrow Wallet importer class

- **Satoshi to BTC conversion**: Sparrow exports use satoshis by default
  - Primary conversion: `value_sats / 100_000_000` for both Value and Fee columns
  - Fallback pattern: If int() conversion fails, try float() for decimal BTC values
  - Enables handling both native satoshi exports and manually-edited decimal files
- **Two-step parsing pattern**:
  ```python
  try:
      value_sats = int(value_str)  # Try as satoshis first
      return value_sats / 100_000_000
  except ValueError:
      return float(value_str)  # Fallback to decimal BTC
  ```
- **Sign-based transaction type**: Value sign determines deposit vs withdrawal
  - Positive value → Deposit (BTC received to wallet)
  - Negative value → Withdrawal (BTC sent from wallet)
  - Always apply `abs(value_btc)` when setting sell amount for withdrawals
- **Label → comment mapping**: Sparrow's Label column becomes transaction comment
  - Empty labels result in `None` comment for deposits
  - For withdrawals, combine label with review comment using "; " separator
  - Pattern: `f"{label}; {withdrawal_comment}"` if both exist
- **Detection heuristic**: Combination of 'label' + 'balance' columns is distinctive
  - Most wallet exports don't include running balance
  - Label field is unique to Sparrow's export format
  - Requires all 5 columns: date, label, value, balance, txid
- **Case-insensitive column matching**: Uses `_normalize_header()` helper
  - Handles LABEL vs Label vs label variations
  - Same pattern as Trezor and Ledger parsers
- **Zero-fee handling**: Empty `fee_curr` string when fee == 0
  - Prevents orphan "BTC" label on zero-fee withdrawals
  - Consistent with other wallet parsers
- **Test fixture**: 5 transactions with satoshi values (50M, -20M, 10M, -5M, 25M)
  - Mix of positive/negative values, varying fees, descriptive labels
  - Tests satoshi-to-BTC conversion accuracy across range of amounts
- **27 comprehensive tests**: Detection (4), parsing (17), registration (3), integration (3)
  - Includes tests for satoshi conversion, decimal fallback, label preservation
  - All tests pass, 617 total tests passing (27 new + 590 existing)

## WAL-005: Coldcard Importer

- **Coldcard CSV format**: Address explorer export with 5 columns:
  - Date (YYYY-MM-DD), Type (receive/send), Amount (decimal BTC), Fee (decimal BTC), TXID
- **Dual detection mode**: Supports both type-based and sign-based transaction detection
  - Type column present: `receive`/`received`/`in` → Deposit, `send`/`sent`/`out` → Withdrawal
  - Type column empty: positive amount → Deposit, negative amount → Withdrawal
  - Handles firmware version variations where type column may be absent
- **Detection heuristic**: Uses `type` + `amount` + `txid` columns as distinctive markers
  - Trezor: has 'tx id' (with space) and 'address' — excluded by negative checks
  - Sparrow: has 'value'/'label'/'balance' instead of 'amount'/'type'
  - Ledger: has 'operation type' instead of 'type'
  - Negative checks `'address' not in header` and `'label' not in header` prevent false positives
- **Amount format**: Decimal BTC (not satoshis like Sparrow) — no conversion needed
- **Case-insensitive**: Both column names and type values are normalized with `.lower()`
- **Consistent patterns**: Same as all wallet parsers:
  - Zero-amount filtering, zero-fee handling (`fee_curr=''`), abs() on amounts
  - wallet_name for deposits, withdraw_to for withdrawals
  - Review comment for unspecified withdrawal destinations
- **30 comprehensive tests**: Detection (5), parsing (20), registration (3), integration (2)
  - Includes type variants, sign-based fallback, case-insensitive matching, invalid data handling
  - All tests pass, 647 total tests passing (30 new + 617 existing)

## WAL-006: Removing Orphaned Modules

- **Verification before deletion**: Always grep the full codebase for imports/references
  before removing a module. Planning/documentation references don't count as active usage.
- **Pattern**: When migrating standalone functions to a class-based system (e.g.,
  `wallet_imports.py` functions → `imports/wallets/*.py` classes), the standalone
  module becomes dead code once all parsers are migrated and tested.
- **Confidence check**: Run the full test suite after deletion to confirm no hidden
  dependencies exist (dynamic imports, exec(), etc.).

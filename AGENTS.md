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

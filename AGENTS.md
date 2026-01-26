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

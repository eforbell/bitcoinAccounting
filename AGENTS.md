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

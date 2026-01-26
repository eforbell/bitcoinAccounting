"""Database exceptions."""


class DatabaseError(Exception):
    """Unified database error wrapping backend-specific exceptions.

    This exception wraps psycopg2.Error and sqlite3.Error to provide
    a consistent error handling interface regardless of backend.
    """
    pass

#!/usr/bin/env python3
"""Run PostgreSQL migrations using psycopg2.

Usage:
    python migrations/run_migration.py

Reads connection parameters from .env file (same as the app).
Must be run as a user with ALTER TABLE privileges (e.g. table owner).

Override connection with environment variables:
    PGUSER=postgres PGPASSWORD=... python migrations/run_migration.py
"""

import os
import sys
from pathlib import Path

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

try:
    import psycopg2
except ImportError:
    print("psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def run_migration():
    params = {
        "host": os.getenv("PGHOST", "localhost"),
        "port": os.getenv("PGPORT", "5432"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", ""),
        "database": os.getenv("PGDATABASE", "postgres"),
    }
    sslmode = os.getenv("PGSSLMODE")
    if sslmode:
        params["sslmode"] = sslmode

    print(f"Connecting to {params['host']}:{params['port']}/{params['database']} as {params['user']}...")

    conn = psycopg2.connect(**params)
    conn.autocommit = True
    cur = conn.cursor()

    print("Running migration: 001_add_soft_delete_columns")
    cur.execute("ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted_date TEXT")

    # Verify
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ledger' AND column_name IN ('deleted', 'deleted_date')")
    cols = [row[0] for row in cur.fetchall()]
    print(f"Verified columns present: {cols}")

    cur.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    run_migration()

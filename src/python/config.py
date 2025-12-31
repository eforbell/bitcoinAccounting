import os
import psycopg2

"""
Simple DB connection helper for the project.
Reads connection parameters from environment variables with sensible defaults.

Environment variables used:
- PGHOST (default: 127.0.0.1)
- PGPORT (default: 5432)
- PGUSER (default: bitcoin_accounting)
- PGPASSWORD (default: empty)
- PGDATABASE (default: crypto)
- PGSSLMODE (optional)

Usage:
from config import connect
conn = connect()
"""


def connect():
    params = {
        'host': os.getenv('PGHOST', '192.0.2.10'),
        'port': os.getenv('PGPORT', '5432'),
        'user': os.getenv('PGUSER', 'bitcoin_accounting'),
        'password': os.getenv('PGPASSWORD', '####'),
        'database': os.getenv('PGDATABASE', 'postgres'),
        'connect_timeout': 5
    }
    sslmode = os.getenv('PGSSLMODE')
    if sslmode:
        params['sslmode'] = sslmode
    return psycopg2.connect(**params)

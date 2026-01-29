#!/usr/bin/env python3
"""Test script to verify .env file loading works correctly.

This script checks if environment variables are being loaded from .env file.
"""
import os
import sys
from pathlib import Path

# Add src/python to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root / "src" / "python"))

print("Testing .env file loading...")
print("=" * 60)

# Test 1: Check if .env file exists
env_file = repo_root / ".env"
if env_file.exists():
    print(f"✓ .env file found at: {env_file}")
else:
    print(f"✗ .env file NOT found at: {env_file}")
    print("  Create it by copying .env.example:")
    print(f"  cp {repo_root}/.env.example {env_file}")

print()

# Test 2: Import db package (should auto-load .env)
try:
    from db import get_backend
    print("✓ Successfully imported db package")
except ImportError as e:
    print(f"✗ Failed to import db package: {e}")
    sys.exit(1)

print()

# Test 3: Check environment variables
print("Environment variables:")
print("-" * 60)
env_vars = ['DB_BACKEND', 'SQLITE_DB_PATH', 'PGHOST', 'PGUSER', 'PGPASSWORD', 'PGDATABASE']
for var in env_vars:
    value = os.getenv(var)
    if value:
        # Mask password
        if 'PASSWORD' in var:
            display = '*' * len(value) if value else None
        else:
            display = value
        print(f"  {var}: {display}")
    else:
        print(f"  {var}: (not set)")

print()

# Test 4: Try to create backend
db_backend = os.getenv('DB_BACKEND', 'sqlite')
print(f"Attempting to create {db_backend} backend...")
print("-" * 60)

try:
    backend = get_backend()
    print(f"✓ Successfully created {db_backend} backend")
    backend.close()
except Exception as e:
    print(f"✗ Failed to create backend: {e}")
    if db_backend == 'postgres':
        print("\nIf using PostgreSQL, ensure these are set in .env:")
        print("  PGHOST, PGUSER, PGPASSWORD, PGDATABASE")

print()
print("=" * 60)
print("Test complete!")

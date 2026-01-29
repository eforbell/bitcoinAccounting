# Security Fix Summary - 2026-01-28

## Issue Summary

**CRITICAL SECURITY BREACH**: PostgreSQL credentials were hardcoded in `src/python/db/postgres.py` and pushed to GitHub in commit `34803d8`.

### Exposed Information
- Database host: `192.0.2.10`
- Database user: `bitcoin_accounting`
- Database password: `REDACTED-ROTATED` (now changed ✓)
- Database name: `postgres`

## Root Causes

1. **Hardcoded default values** in postgres.py for sensitive credentials
2. **No .env file support** - code used `os.getenv()` but Python doesn't auto-load .env files
3. **Missing security documentation** - no warnings about credential management
4. **No .env.example template** - developers didn't have a safe pattern to follow

## Fixes Applied

### 1. Removed Hardcoded Credentials ✓
**File**: `src/python/db/postgres.py`

**Before**:
```python
params: dict[str, Any] = {
    'host': os.getenv('PGHOST', '192.0.2.10'),  # ❌ Hardcoded
    'user': os.getenv('PGUSER', 'bitcoin_accounting'),  # ❌ Hardcoded
    'password': os.getenv('PGPASSWORD', 'REDACTED-ROTATED'),  # ❌ EXPOSED
    'database': os.getenv('PGDATABASE', 'postgres'),  # ❌ Hardcoded
}
```

**After**:
```python
# Require critical credentials from environment
required_vars = ['PGHOST', 'PGUSER', 'PGPASSWORD', 'PGDATABASE']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    raise DatabaseError(
        f"Missing required environment variables: {', '.join(missing)}. "
        "Set these in your environment or .env file."
    )

params: dict[str, Any] = {
    'host': os.getenv('PGHOST'),  # ✓ Required
    'user': os.getenv('PGUSER'),  # ✓ Required
    'password': os.getenv('PGPASSWORD'),  # ✓ Required
    'database': os.getenv('PGDATABASE'),  # ✓ Required
}
```

**Result**: Code now *requires* environment variables and fails with clear error message if missing.

### 2. Added .env File Support ✓
**Files**:
- `requirements.txt` - Added `python-dotenv`
- `src/scripts/_bootstrap.py` - Auto-loads `.env` for all CLI scripts
- `src/python/db/__init__.py` - Auto-loads `.env` when importing db package

**Result**: All scripts and Python imports automatically load `.env` file from repository root.

### 3. Created .env.example Template ✓
**File**: `.env.example`

Provides safe template with:
- All required environment variables documented
- No default sensitive values
- Clear comments about security
- Instructions to copy to `.env`

### 4. Added Security Documentation ✓
**File**: `SECURITY.md`

Documents:
- Credential management best practices
- What to do if credentials are exposed
- Code review checklist
- Incident log (this breach documented)

### 5. Updated README ✓
**File**: `README.md`

Updated PostgreSQL setup instructions to:
- Emphasize using `.env` file
- Show `cp .env.example .env` workflow
- Remove examples with `export` commands that could be copy-pasted with real credentials
- Note that `.env` is in `.gitignore`

## Testing

Run the test script to verify environment loading:
```bash
python3 test_env_loading.py
```

Expected output:
- Shows if `.env` file exists
- Lists which environment variables are set
- Tests backend creation
- Confirms auto-loading works

## Action Items for Users

### Required (If Using PostgreSQL):
1. ✓ **Change database password** (already done)
2. **Install updated dependencies**:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
3. **Create .env file**:
   ```bash
   cp .env.example .env
   ```
4. **Edit .env with your credentials**:
   ```bash
   # Use your favorite editor
   nano .env
   # Fill in: DB_BACKEND, PGHOST, PGUSER, PGPASSWORD, PGDATABASE
   ```
5. **Test the connection**:
   ```bash
   python3 test_env_loading.py
   ```

### Optional (Recommended):
- Review `SECURITY.md` for best practices
- Consider using SQLite instead (no credentials needed)
- If using GitHub Actions or CI/CD, use secrets management

## Files Changed

### Modified:
- `src/python/db/postgres.py` - Removed hardcoded credentials, added validation
- `src/scripts/_bootstrap.py` - Added .env loading
- `src/python/db/__init__.py` - Added .env loading
- `requirements.txt` - Added python-dotenv
- `README.md` - Updated PostgreSQL setup instructions

### Created:
- `.env.example` - Template for environment variables
- `SECURITY.md` - Security policy and incident log
- `SECURITY_FIX_SUMMARY.md` - This document
- `test_env_loading.py` - Environment loading test script

## Commit Plan

Ready to commit with:
```bash
git add .env.example SECURITY.md SECURITY_FIX_SUMMARY.md test_env_loading.py
git add src/python/db/postgres.py src/scripts/_bootstrap.py src/python/db/__init__.py
git add requirements.txt README.md
git commit -m "security: Remove hardcoded credentials and add .env support

BREAKING CHANGE: PostgreSQL credentials must now be provided via environment
variables. Hardcoded defaults have been removed for security.

- Remove hardcoded database credentials from postgres.py
- Add python-dotenv for automatic .env file loading
- Create .env.example template for safe credential management
- Add SECURITY.md with credential management policy
- Update README with .env setup instructions
- Add test script to verify environment loading

Users must create .env file (copy from .env.example) and set:
PGHOST, PGUSER, PGPASSWORD, PGDATABASE

PostgreSQL password was rotated after accidental exposure in commit 34803d8.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

## Prevention Measures

Going forward:
- ✓ No hardcoded IPs, hostnames, or credentials
- ✓ All sensitive config via environment variables with NO defaults
- ✓ Clear error messages when required variables missing
- ✓ `.env` file in `.gitignore`
- ✓ `.env.example` as template (never contains real credentials)
- ✓ Security policy documented
- Code review checklist in SECURITY.md

## Notes

- The exposed password has been changed ✓
- The problematic commit (34803d8) is still in git history
- Consider using `git filter-branch` or BFG Repo-Cleaner if you want to remove from history (advanced)
- SQLite backend requires no credentials - good default for most users

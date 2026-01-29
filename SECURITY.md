# Security Policy

## Credential Management

**CRITICAL: NEVER commit credentials to version control**

### Required Practices

1. **Use Environment Variables**
   - All database credentials MUST be provided via environment variables
   - Never use hardcoded defaults for sensitive values (passwords, hosts, usernames)
   - Store credentials in `.env` file locally (this file is in `.gitignore`)

2. **Template File**
   - Use `.env.example` as a template
   - Copy `.env.example` to `.env` and fill in your actual values
   - The `.env` file is automatically ignored by git

3. **Required Environment Variables**
   ```bash
   # For PostgreSQL backend
   PGHOST=your-database-host
   PGUSER=your-database-user
   PGPASSWORD=your-secure-password
   PGDATABASE=your-database-name
   PGPORT=5432  # optional
   PGSSLMODE=require  # optional
   ```

4. **Code Review Checklist**
   - [ ] No hardcoded IPs, hostnames, or server addresses
   - [ ] No hardcoded usernames or database names as defaults
   - [ ] No hardcoded passwords (EVER)
   - [ ] All sensitive config uses `os.getenv()` WITHOUT default values
   - [ ] Missing required environment variables raise clear errors

### What to Do If Credentials Are Exposed

If credentials are accidentally committed and pushed to GitHub:

1. **Immediately rotate the exposed credentials**
   ```sql
   -- In PostgreSQL
   ALTER USER username WITH PASSWORD 'new-secure-password';
   ```

2. **Update your local `.env` file** with new credentials

3. **Remove the credentials from the code** (make a new commit)

4. **Consider removing from git history** (advanced)
   - Use `git filter-branch` or BFG Repo-Cleaner
   - Force push to rewrite history (CAUTION: affects all collaborators)
   - See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository

### Incident Log

#### 2026-01-28: PostgreSQL Credentials Exposed
- **Commit:** 34803d8 (feat: SQL-001 - Database abstraction layer foundation)
- **File:** src/python/db/postgres.py
- **Exposed:** Database host (192.0.2.10), username (bitcoin_accounting), password
- **Action Taken:**
  - Code updated to require environment variables
  - Added clear error messages for missing credentials
  - Created .env.example template
  - Documented in SECURITY.md
- **Required Action:** Change PostgreSQL password for user 'bitcoin_accounting'

## Reporting Security Issues

If you discover a security vulnerability, please:
1. Do NOT open a public issue
2. Email the repository owner directly
3. Include details about the vulnerability and steps to reproduce

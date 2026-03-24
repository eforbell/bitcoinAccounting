# Web Deploy Notes

This web service is intended to run as a Python process behind nginx on a subpath mount.

Recommended production shape:
- host: `numenor`
- app dir: `/data/apps/bitcoinAccounting`
- systemd service: `bitcoin-accounting-web`
- upstream bind: `127.0.0.1:3010`
- external path: `/bitcoin-accounting/`
- database: PostgreSQL on the same host

## Required env

```env
BITCOIN_ACCOUNTING_ENV=production
DB_BACKEND=postgres
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=bitcoin_accounting
PGUSER=bitcoin_accountant
PGPASSWORD=...
BITCOIN_ACCOUNTING_AUTH_ENABLED=1
BITCOIN_ACCOUNTING_AUTH_PASSPHRASE=...
BITCOIN_ACCOUNTING_SESSION_SECRET=...
BITCOIN_ACCOUNTING_WEB_BASE_PATH=/bitcoin-accounting
BITCOIN_ACCOUNTING_WEB_DOCS=0
```

## PostgreSQL prep

The web init command validates PostgreSQL connectivity and ensures web-owned tables, but it does not create the full legacy accounting schema on PostgreSQL.

Initialize the core PostgreSQL schema first:

```sh
psql -U <db-admin> -d <database> -f src/sql/tables.sql
```

Then validate runtime:

```sh
.venv/bin/bitcoin-accounting-web-init
```

## Subpath contract

The app is expected to survive behind nginx on a subpath mount.

Rules:
- nginx should strip the `/bitcoin-accounting/` prefix before proxying upstream
- `BITCOIN_ACCOUNTING_WEB_BASE_PATH` must still be set to `/bitcoin-accounting`
- future frontend assets and `fetch()` calls must use relative paths, never absolute `/...` paths
- auth cookies are scoped to the configured base path, not `/`

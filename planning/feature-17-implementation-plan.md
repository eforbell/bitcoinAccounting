# Feature-17 Implementation Plan

## Goal

Stand up the first production-capable web foundation for Bitcoin Accounting:

- Python API service in front of the existing domain/query core
- Stable JSON contracts
- Private auth suitable for a self-hosted sovereignty app
- PostgreSQL-first production posture
- TUI/CLI preserved as fallback surfaces

## Recommendation

Use **FastAPI** for Feature-17.

Why:

- Strong fit for explicit request/response JSON models.
- Good ergonomics for incremental authenticated API work.
- Easy OpenAPI/docs during development, even if disabled in production later.
- Natural fit for a Python-first backend where domain code already exists.

Avoid for now:

- Moving domain logic into Node/Express.
- Building a GraphQL layer.
- Premature background job infrastructure.
- SQLite as the primary recommended production backend for web mode.

## Production Backend Policy

For the web app:

- **Recommended production backend:** PostgreSQL
- **Supported fallback backend:** SQLite

SQLite remains valid for low-concurrency or demo/self-contained installs, but PostgreSQL should be the documented and tested primary deployment mode for the web application because:

- the primary operator already runs production on PostgreSQL
- concurrent request handling is a better fit for PostgreSQL
- tax-critical write paths deserve the stronger production posture

## Proposed Initial Package Layout

```text
src/python/web/
├── __init__.py
├── app.py
├── auth.py
├── config.py
├── dependencies.py
├── models.py
├── routes/
│   ├── __init__.py
│   ├── health.py
│   ├── auth.py
│   ├── portfolio.py
│   └── tax.py
└── services/
    ├── __init__.py
    ├── portfolio.py
    └── tax_reporting.py
```

## Initial Story Grouping

Feature-17 is written as five stories, but implementation can reasonably start in these slices:

### Slice 1: WEB-001 + WEB-002

Deliver:

- framework bootstrap
- app factory
- health route
- core response models
- request-safe backend dependency

This is the best first implementation slice because it creates the web shape without locking auth or frontend decisions too early.

### Slice 2: WEB-003

Deliver:

- bootstrap auth config
- login/logout/session endpoints
- route protection dependency

Keep auth intentionally simple:

- single-user or very-light household model
- session cookie
- secure passphrase/password

### Slice 3: WEB-004 + WEB-005

Deliver:

- explicit PostgreSQL-first docs and config
- request lifecycle guidance
- logging, startup validation, health/readiness notes
- deployment/runbook baseline

## First Code Pass

Recommended first implementation tasks on this branch:

1. Add web package skeleton under `src/python/web/`
2. Add FastAPI dependency to project metadata if not already present
3. Create `web.app:create_app()`
4. Add `/api/health`
5. Add typed JSON models for:
   - wallet
   - transaction
   - portfolio summary
   - gains summary
   - forecast summary
6. Add backend dependency helper that constructs a backend per request/context
7. Add tests for app boot and health route

## Important Constraints

1. Do not make the web layer depend on TUI screen modules.
2. Do not expose TUI-shaped labels like `"Buy Cur."` in web JSON.
3. Do not reuse one long-lived `BitcoinAccounts()` instance globally for all requests.
4. Do not weaken current TUI/CLI behavior while introducing web infrastructure.
5. Keep environment/config names compatible with the existing DB abstraction where possible.

## Open Questions

1. Should the frontend for early Feature-17 be:
   - static HTML/JS served by Python
   - React app served separately
   - Express-served frontend hitting Python API

2. Should auth bootstrap from:
   - one configured passphrase in env
   - one stored app user record
   - existing wallet/operator metadata plus a new auth table

3. Should OpenAPI/docs remain enabled on the Tailscale network in development only, or also in private production?

## Exit Criteria For Feature-17 Start

The branch is ready to implement when:

- `planning/current-feature.json` points to Feature-17
- branch is `feature/web-foundation-api-platform`
- FastAPI decision is accepted
- PostgreSQL-first production stance is accepted
- first slice is defined as `WEB-001 + WEB-002`

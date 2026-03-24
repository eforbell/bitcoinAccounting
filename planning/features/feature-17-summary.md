# Feature-17: Web Foundation, API Layer, Auth, and Deployment

## Purpose

Feature-17 establishes the production web architecture for Bitcoin Accounting: a Python API layer in front of the existing domain core, stable JSON contracts for frontend consumption, private auth suitable for a sovereignty app, and a deployment posture optimized for self-hosted bare metal over Tailscale.

## Timing

Drafted on **March 24, 2026**.

Recommended earliest execution: **March 25, 2026**.

## Scope

1. Choose and scaffold the Python web framework.
2. Define canonical JSON models for core resources.
3. Add lightweight private auth and session handling.
4. Formalize PostgreSQL-first production policy and request-safe DB lifecycle.
5. Document deployment, health checks, and operational posture.

## Key Platform Decision

For the web app:

- **PostgreSQL is the recommended production backend**
- **SQLite remains supported but is not the default recommendation**

Rationale:

- The primary production deployment already runs on PostgreSQL.
- A concurrent web/API process model fits PostgreSQL better than the current TUI-style single-connection SQLite usage.
- SQLite is still useful for evaluation, local demos, and low-concurrency/self-contained installs.

## Why Feature-17 Exists

The TUI already proves the Python domain model is reusable, but it is not itself a stable web API. This feature creates the missing application layer so frontend work can consume explicit JSON endpoints rather than screen-oriented Python calls.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WEB-001 | Framework choice + application structure | Locks the backend shape before route sprawl starts |
| WEB-002 | Canonical JSON models | Prevents TUI-shaped responses from leaking into the web contract |
| WEB-003 | Private auth baseline | Required before exposing meaningful data over Tailscale/internet |
| WEB-004 | DB policy + connection lifecycle | Prevents correctness issues from an unsafe request model |
| WEB-005 | Deployment + observability baseline | Makes the stack operable before feature growth |

## Risk Controls

1. Shared-connection web risk
   Control: use request-safe backend/session acquisition, not a single long-lived TUI-style connection.
2. Contract drift risk
   Control: define JSON models early and test them directly.
3. Overbuilt auth risk
   Control: keep auth optimized for a private single-operator app rather than multi-tenant roles and policies.

## Definition of Done

- Python API service boots cleanly with authenticated and unauthenticated routes separated.
- Core web resources have stable JSON contracts.
- PostgreSQL is documented as primary production backend for web mode.
- SQLite support stance and limitations are explicit.
- Deployment instructions are sufficient for self-hosted bare-metal usage.

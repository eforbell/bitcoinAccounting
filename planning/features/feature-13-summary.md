# Feature-13: Bitcoin Accounting Rebrand and Compatibility Migration

## One Feature or Two?

This should be treated as **two features overall**:

1. **Feature-13 (this doc)**: staged migration with full backward compatibility.
2. **Feature-14 (follow-on)**: remove legacy `crypto*` names after a deprecation window.

Reason: the codebase has broad `cryptoAccounts` import usage across runtime, scripts, and tests. A single hard-cut rename would create avoidable breakage for users and automation.

## Rollout Context

- Repository is currently private.
- There is one additional external user today.
- Repository is expected to become public soon.

This strongly favors a compatibility-first migration before public launch.

## Problem

The repository has already shifted direction to Bitcoin-first behavior and branding, but naming remains mixed:

- Runtime modules and entrypoints still center on `cryptoAccounting` / `cryptoAccounts`
- Many imports and tests instantiate `CryptoAccounts`
- Default local paths use `~/.cryptoaccounting`
- Docs and helper scripts still reference old project naming

This mismatch creates friction for onboarding, branding consistency, and future maintenance.

## Solution

Execute a staged migration that establishes canonical `bitcoin*` names while preserving legacy compatibility.

### Stage Plan

| Stage | Goal | Key Output |
|------|------|------------|
| 1 | Compatibility foundation | `bitcoinAccounts.py`, `bitcoinAccounting.py`, legacy shims kept |
| 2 | Internal adoption | Source/test/script imports moved to canonical names |
| 3 | UX/docs/path migration | Bitcoin-first text, `~/.bitcoinaccounting` defaults, migration guidance |

## Compatibility Contract (Feature-13)

- Keep `cryptoAccounts` and `cryptoAccounting` imports runnable.
- Keep legacy CLI aliases (`crypto-accounting`, `crypto-tui`) as forwarding aliases.
- Keep data continuity when moving default paths by explicit fallback behavior.
- Emit deprecation warnings where practical, but do not fail execution.

## Story Breakdown

| ID | Title | Purpose |
|----|-------|---------|
| BRD-001 | Canonical bitcoin modules + shims | Introduce new names safely |
| BRD-002 | Internal import migration | Reduce future coupling to legacy names |
| BRD-003 | Packaging + entrypoint updates | Align install/run surface with new branding |
| BRD-004 | Path/cache migration with fallback | Avoid data loss confusion |
| BRD-005 | TUI and user-facing text rebrand | Consistent product identity |
| BRD-006 | Documentation + migration guide | Clear user transition path |
| BRD-007 | Planning/governance updates | Keep project metadata current |

## Risks and Controls

1. Import breakage risk
Control: compatibility shims and alias class names.

2. Data path confusion risk
Control: deterministic precedence/fallback and explicit migration docs.

3. Packaging/entrypoint drift risk
Control: update `pyproject.toml` and smoke-test module and CLI launch paths.

## Follow-On Feature (Feature-14)

After one stable release cycle:

- Remove legacy `crypto*` shims
- Remove legacy console script aliases
- Optionally remove old path fallback behavior

This keeps Feature-13 low-risk while still giving a clean long-term end state.

## Release Guidance

1. Ship Feature-13 before opening the repo publicly.
2. Have the existing external user validate their current workflow without changes.
3. Open public with migration docs already published and legacy aliases still active.
4. Schedule Feature-14 only after the first public stabilization window.

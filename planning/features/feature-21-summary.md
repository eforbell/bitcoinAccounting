# Feature-21: Web Import Center and Duplicate Review

## Purpose

Feature-21 adds CSV import onboarding and maintenance workflows to the web app, wrapping the existing Python parser registry and duplicate detection logic in an operator-friendly browser flow.

## Timing

Drafted on **March 24, 2026**.

Recommended earliest execution: **April 7, 2026**.

## Scope

1. File upload, parser detection, and preview.
2. Import configuration and wallet assignment inputs.
3. Duplicate warning and review workflow.
4. Import execution with actionable results.
5. Import history and troubleshooting aids.

## Why Feature-21 Is Day-2

Imports matter, but the app already has TUI and CLI import paths. Shipping tax-first and dashboard/write workflows to the web produces value sooner without blocking the operator from onboarding data.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| WIM-001 | Upload, detect, and parse | Establishes the web import pipeline |
| WIM-002 | Configuration + wallet assignment | Makes parser outputs usable |
| WIM-003 | Duplicate review | Preserves data hygiene before commit |
| WIM-004 | Execute import + result reporting | Completes the browser-side workflow |
| WIM-005 | Import history + troubleshooting | Improves repeatability and operator support |

## Risk Controls

1. Silent data corruption risk
   Control: require preview-before-commit and keep duplicate detection visible.
2. Parser/format variation risk
   Control: reuse the existing importer registry and expose parser help.
3. Browser upload workflow risk
   Control: keep temp-file handling simple and return actionable errors on failure.

## Definition of Done

- Web uploads can be previewed and imported safely.
- Duplicate warnings appear before commit.
- Import results are clear enough to diagnose skips and failures.
- The browser flow stays aligned with the existing CLI/TUI import semantics.

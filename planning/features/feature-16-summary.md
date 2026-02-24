# Feature-16: Treasury Attestation and Monitoring UX

## Purpose

Feature-16 builds operator workflows on top of integrity foundations by adding repeatable monthly attestation artifacts, monitoring dashboards, alert rules, and evidence exports suitable for long-term treasury operations.

## Timing

Drafted on **February 24, 2026**.

Recommended earliest execution: **March 15, 2026** (after Feature-15 stabilization).

## Scope

1. Generate monthly attestation bundles (JSON/CSV baseline).
2. Add optional PDF summary formatting for archival.
3. Extend TUI with monitoring and drill-down views.
4. Add rule-based alerts and finding status transitions.
5. Document operator workflow and complete planning closeout.

## Why Separate Feature-16?

Separating attestation UX from integrity foundations keeps correctness logic and operational surfaces decoupled:

- Feature-15 focuses on validation accuracy and deterministic signals.
- Feature-16 focuses on workflow usability, reporting, and alerting.
- Teams can adopt artifact generation without committing immediately to richer TUI flows.

## Proposed Story Order

| ID | Story | Why this order |
|----|-------|----------------|
| TAM-001 | Monthly attestation generation | Delivers immediate operator value |
| TAM-002 | PDF/report formatting | Adds archival/shareable output |
| TAM-003 | TUI monitoring dashboard | Improves review and triage speed |
| TAM-004 | Alert rules + status lifecycle | Turns reports into active monitoring |
| TAM-005 | Documentation + closeout | Ensures repeatable operations and onboarding |

## Risk Controls

1. Misinterpretation of attestations
   - Control: explicit non-legal/tax-advice disclaimers in exports and docs.
2. Alert fatigue
   - Control: sane defaults, threshold tuning, and finding lifecycle controls.
3. UX regressions in TUI
   - Control: structure tests + targeted navigation smoke checks.

## Definition of Done

- Monthly attestation artifact command is stable and deterministic.
- TUI exposes current health state, trend, and unresolved finding triage.
- Alerts are configurable and tied to explicit state transitions.
- README/Getting Started include monthly operating playbook.
- Planning artifacts updated to record completion learnings.

# Atlas Delivery Phase Plan

This plan translates the 12-month roadmap and delivery milestones into bounded
implementation phases. `PROJECT_STATUS.json` is the current-state authority.

| Phase | Outcome | Entry condition | Exit criteria |
| --- | --- | --- | --- |
| Phase 0 | Validated Atlas foundation | Imported foundation under review | Decimal projection authority, parity fixtures/docs, safe import, isolated service environments, synthetic fixture coverage and CI evidence complete. |
| Phase 1 | Forecast persistence | Phase 0 complete and explicitly authorized | Versioned forecast records, migrations, authorization, audit evidence, tests, and rollback path. |
| Phase 2 | Forecast UI migration | Phase 1 complete and explicitly authorized | UI uses persisted forecasts, preserves explainability, has accessibility and parity coverage. |
| Phase 3 | Goal-linked recommendations | Phase 2 complete and explicitly authorized | Recommendations link goals, evidence, risks, confidence, approvals, and evaluation. |
| Phase 4 | Decision journal | Phase 3 complete and explicitly authorized | Decisions, alternatives, outcomes, permissions, audit history, and recovery are tested. |
| Phase 5 | Market Intelligence Brief | Certified Phase 4 and explicitly authorized | A versioned, source-cited, portfolio-specific market briefing reports portfolio changes, material news, earnings and filings, deterministic actions to review, privacy-safe delivery, and tested failure behavior without paid data or autonomous execution. |
| Phase 6 | Scenario Lab | Phase 5 certified and explicit Slice 1 authorization | Slice 1: authoritative deterministic Decimal-safe owner-scoped scenario backend with immutable history, bounded comparison APIs, migration parity, and no UI. Later UI migration requires a separate authorization. |

No phase starts automatically. Review the active phase, dependencies, and exit
criteria before authorizing the next bounded task.

Project-status consistency is enforced in pull-request CI, not by a blocking
local hook, so agents can record legitimate work in progress without bypasses
or duplicated checks.

## Phase 2 packaging (current)

Phase 2 is the first user-visible Atlas slice and is currently being shipped
as **two cohesive implementation PRs** under the simplified solo-development
governance below, unless a real safety boundary requires otherwise:

1. **Backend recommendation + decision-journal substrate.** Bounded backend
   changes: append-only decision journal, deterministic recommendation
   derivation, bounded read routes gated by Phase 1's read-API flag. No UI
   changes in this PR.
2. **Complete user-visible UI vertical slice using that substrate.** A single
   PR that consumes the substrate and adds the bounded UI surface on the
   existing `/goals` page. Mappers, schemas, routes, tests, and the rest of
   this slice belong in this single PR — do not split into micro-PRs.

Do not create separate PRs for mappers, schemas, routes, tests, or
documentation that belong to the same slice. Both PRs run under the same
governance tier (HIGH — financial correctness + immutable schemas + write
APIs) and apply the new corrected-cycle cap (maximum two correction and
review cycles per PR).

## Current Phase 1 reference

- Tracking issue: #3
- Proposed architecture: `docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md`
- Bounded implementation sequence:
  `docs/superpowers/plans/2026-07-26-atlas-phase1-forecast-persistence.md`

Phase 1 was certified complete at SHA
`08f6f811da7c325da8a3d60adae9f2d9c2d210e8` (annotated tag
`phase-1-complete`). The certification head remains canonical for all
historical Phase 1 evidence; the new tiered workflow applies prospectively.
External multi-user production enablement remains blocked pending the
approved retention + user-deletion policy (`risk-p1-retention-rollout-gate`).

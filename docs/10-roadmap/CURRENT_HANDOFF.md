# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: ui-12 — Cross-route trust certification
- Phase status: in_progress
- Overall status: in_progress
- Objective: Preserve the now-committed UI-10 provider-backed Scout expansion and the certified UI-09/UI-11 boundaries, and remediate the UI-12 /portfolio responsive and certification blockers before the final trust-certification rerun.
- Phase exit criteria: 1/2 complete
- Tracker updated: 2026-09-04T07:00:00Z

## Active work

- work-ui-12-portfolio-remediation-and-certification: Remediate UI-12 responsive and certification blockers [in_progress/medium]
  - Objective: Close repository-scoped responsive defects revealed by the expanded UI-12 matrix without changing investment semantics, then rerun the consolidated certification evidence.
  - Branch: None
  - Paths: ui/components/market-briefs/MarketIntelligenceCenter.tsx,ui/__tests__/e2e/ui12-trust-certification.spec.ts,docs/architecture/ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md

## Blockers

- external-multi-user-retention-deletion-blocker [open]: External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.

## Open risks

- risk-frontend-lint-debt [medium/high]: Repository-wide frontend lint debt remains outside Phase 0 scope.
- risk-monte-carlo-deferred [medium/medium]: Monte Carlo probability model is intentionally deferred.
- risk-transitional-tenancy [high/medium]: User-scoped tenancy remains transitional.
- risk-legacy-product-names [low/high]: Legacy Finance Copilot, WealthIQ, CashFlix, and Finlynq names remain.
- risk-fixture-compatibility-names [low/medium]: Synthetic fixture directories retain compatibility-oriented names.
- risk-service-dependency-separation [high/high]: Rules Service and Finlynq require separate FastAPI-pinned environments.
- risk-p1-legacy-goal-float [high/medium]: The existing Goal.target_amount Float can lose source precision before Phase 1 snapshot normalization.
- risk-p1-dialect-parity [high/medium]: SQLite and PostgreSQL differ in exact numeric storage and concurrency semantics for immutable forecast versions.
- risk-p1-retention-rollout-gate [high/medium]: No approved retention or user-deletion policy exists for immutable forecast history.
- risk-p1-trusted-generation-boundary [high/medium]: An untrusted generation request could forge canonical financial state or provenance if the trusted adapter boundary regresses.
- risk-p1-external-provider-local-config [high/medium]: Ignored local configuration has Market Intelligence read/generation/external-provider flags enabled and provider credentials present; no provider call was made in this task, but the local state is not safe to treat as fully disabled.
- risk-p1-local-backup-recovery [high/low]: WAL-safe local backup, disposable restore, and backup-first personal activation have passed; in-place restore remains intentionally unsupported and requires a future separately authorized recovery task.
- risk-ui11-current-only-scope [medium/high]: UI-11 is intentionally limited to a current-only portfolio baseline, descriptive compatible value/exposure metrics, and an on-demand hypothetical value preview; historical reconstruction and advanced aggregate risk methods are unavailable.

## Recently completed

- work-ui-11-risk-scenario-boundary: UI-11 bounded current-only risk/scenario presentation — commit b9ecce0, PR not recorded
- work-ui-12-cross-route-trust-certification: Audit UI-12 cross-route trust and certification readiness — commit null, PR not recorded
- work-ui-12-coordinated-certification-evidence: Run coordinated UI-12 trust certification evidence — commit ad6bfb8, PR not recorded
- work-ui-10-provider-backed-scout-expansion: Implement and commit bounded provider-backed UI-10 Scout expansion — commit 84259ee, PR not recorded
- work-inv-12-foundation-durable-stores: Land INV-12 durable stores and frozen contracts — commit a8a6016, PR not recorded

## Next bounded task

- work-ui-12-portfolio-remediation-and-certification: Remediate the /portfolio 390px overflow and separate its mutation controls from the UI-12 read-only certification boundary; then rerun the consolidated UI-12 matrix. Current UI-12 evidence remains PARTIAL: ten-route read-only matrix passes, while populated owner-data proof, CPU interaction measurement, INV-12 policy, optional CIO archive decision, and multi-user retention/deletion policy remain open.

Do not begin the next task automatically.

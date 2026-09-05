# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: ui-12 — Cross-route trust certification
- Phase status: complete
- Overall status: complete
- Objective: Investment roadmap complete for the personal single-user boundary: INV-01..12 and UI-08..12 are all certified (INV-12 closed 2026-09-04; UI-12 certified 2026-09-04 after the /portfolio remediation and certification-evidence tranche). The only remaining item is external multi-user production enablement, blocked by the open retention/deletion policy decision.
- Phase exit criteria: 2/2 complete
- Tracker updated: 2026-09-05T01:30:00Z

## Active work

- None

## Blockers

- external-multi-user-retention-deletion-blocker [open]: External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.

## Open risks

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

- work-ui-12-coordinated-certification-evidence: Run coordinated UI-12 trust certification evidence — commit ad6bfb8, PR not recorded
- work-ui-10-provider-backed-scout-expansion: Implement and commit bounded provider-backed UI-10 Scout expansion — commit 84259ee, PR not recorded
- work-inv-12-foundation-durable-stores: Land INV-12 durable stores and frozen contracts — commit a8a6016, PR not recorded
- work-inv-12-evaluation-engine-and-read-api: Wire INV-12 evaluation engine, replay, and read API — commit f782ffd, PR not recorded
- work-ui-12-portfolio-remediation-and-certification: Remediate UI-12 responsive and certification blockers — commit 443ce50, PR not recorded

## Next bounded task

- external-multi-user-retention-deletion-blocker: No remaining bounded investment-roadmap task for the personal single-user boundary: UI-12 is certified (2026-09-04) and every executable gap (GAP-10/11/12/13/14/17/19) is closed. External multi-user production enablement remains the only open item and stays blocked by the retention/deletion policy decision (external-multi-user-retention-deletion-blocker), which is out of scope per AGENTS.md personal-use boundary.

Do not begin the next task automatically.

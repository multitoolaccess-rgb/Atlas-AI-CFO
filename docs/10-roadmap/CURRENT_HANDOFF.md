# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-5 — Market Intelligence Brief
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 5 Market Intelligence Brief planning is authorized after certified Phase 4. Build a zero-dollar, deterministic, portfolio-first briefing with source citations, in-app history, privacy-safe default-off delivery, and no autonomous execution.
- Phase exit criteria: 0/1 complete
- Tracker updated: 2026-08-11T05:09:44Z

## Active work

- work-p5-deterministic-briefing-engine: Phase 5 Slice 2 deterministic portfolio-impact and briefing engine [in_progress/high]
  - Objective: Build Decimal-safe portfolio impact, immutable versioned source-cited briefing records, deterministic action-to-review templates, and strict owner-scoped generation/read behavior without LLMs or execution.
  - Branch: codex/phase-5-deterministic-briefing-engine
  - Paths: services/rules-service/app/market_intelligence, services/rules-service/app/models, services/rules-service/app/forecasts, services/rules-service/app/routes, services/rules-service/alembic/versions, services/rules-service/tests, docs/10-roadmap

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
- risk-p1-account-currency-authority [high/high]: Finlynq active account balances have no authoritative currency attribute; a user preference/default cannot prove balances are USD for atlas-projection-state/v1.

## Recently completed

- work-p3-outcome-evidence-reference-replacement: Phase 3 Slice 1: Privacy-safe outcome-evaluation substrate (evidence reference replacement) — commit 8955e40a74926d76bed7cd93f5fb31a8508d40c9, PR 32
- work-p3-recommendation-linkage-and-approvals: Phase 3: Recommendation linkage and approvals — commit 86ea65fc8c27224ec209249218fb6ccbe74b4178, PR 33
- work-p4-decision-history-substrate: Phase 4 Slice 1 decision-history substrate — commit 13da914cf1db78d02219eb72c9f4f5b0aca9e86f, PR 34
- work-p4-decision-history-ui: Phase 4 Slice 2 decision-history UI — commit a81eee6, PR 35
- work-p5-research-data-foundation: Phase 5 Slice 1 research-data foundation — commit f573ee4d5c43dfb5636c67c6f260b1decd118efe, PR 36

## Next bounded task

- work-p5-deterministic-briefing-engine: Complete the active high-risk Slice 2 deterministic portfolio-impact and briefing-engine PR with required CI and fresh independent review.

Do not begin the next task automatically.

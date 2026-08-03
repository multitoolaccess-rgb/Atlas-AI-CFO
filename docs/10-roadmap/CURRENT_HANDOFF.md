# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-2 — Forecast UI migration
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 2 Slice 1 BACKEND SUBSTRATE COMPLETE. PR #21 (head 642b3d488af16cd737e28ceca63c576a1238d2e1) squash-merged to main at 3ce7fe5706530d0ec68e743fff0882c76b3434cf with code-reviewer-minimax-m3 VERDICT: GREEN against the full 13-item plan §3/§4/§5/§8 matrix, status CI gate passed (9s), and governance-required cross-cut regression coverage (16/16 commit-4 route integration + 238/238 focused + broader regression over commit-1/2/3 + Phase 1 forecast/canonical/hashing/migration/currency-provenance). The backend substrate delivers: deterministic recommendation derivation rules (no LLM, no external market data, no raw transactions), append-only decision journal ORM (mirrors Phase 1 immutable forecast_versions with SQLite + PostgreSQL BEFORE UPDATE/DELETE protection), owned Pydantic schemas (canonical-Decimal, RFC-3339-UTC-Z, sanitized envelopes including the dedicated RecommendationNotFound envelope), the two approved authenticated Phase 2 routes (GET /api/v1/forecasts/{forecast_id}/recommendation; POST /api/v1/recommendations/{recommendation_id}/decisions) gated by aptly scoped default-off server flags (atlas_forecast_read_api_enabled plus the new atlas_recommendation_persistence_enabled and atlas_decision_journal_writes_enabled), full plan-disciplined boundary contracts (ownership-before-disclosure, idempotent replay, stable sanitized 409 on conflicting payload reuse, currency fail-closed on missing/unverified/conflicting evidence), and test_decision_journal_parity.py dialect-parity coverage. Phase 1 cert remains canonical at SHA 08f6f811da7c325da8a3d60adae9f2d9c2d210e8 (annotated tag phase-1-complete). External multi-user production enablement remains BLOCKED pending retention and user-deletion policy (risk-p1-retention-rollout-gate open). Currency uncertainty continues to fail closed (risk-p1-account-currency-authority open). Personal single-user development may continue per the simplified tiered governance. Phase 2 Slice 2 (UI vertical slice) is the next bounded task.
- Phase exit criteria: 0/1 complete
- Tracker updated: 2026-08-02T03:26:08Z

## Active work

- work-p2-repository-health-stabilization: Phase 2 repository-health stabilization [in_progress/medium]
  - Objective: Restore clean-runner lint and stabilize legacy browser verification without changing Phase 2 financial behavior.
  - Branch: codex/repository-health-stabilization
  - Paths: docs/10-roadmap/PHASE2_REPOSITORY_HEALTH_STABILIZATION.md

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

- work-p1-versioned-schemas: Phase 1 Slice C: Decimal-safe versioned API schemas — commit 17632b5, PR 12
- work-p1-versioned-read-routes: Phase 1 Slice D: Authenticated versioned read routes — commit 8b576830edb069f009550b6891750c91e0e8b0bf, PR 13
- work-p1-cert-rollup: Phase 1 PR #20 cert rollup (cycle-1 corrections + cycle-5 scoped test) — commit 02bbd58f62e32c13362680c9a31dc9710c132d1c, PR not recorded
- work-p1-final-cert: Phase 1 final cert + migration downgrade corrective squash-merge to main — commit 08f6f811da7c325da8a3d60adae9f2d9c2d210e8, PR not recorded
- work-p2-decision-journal-substrate: Phase 2 Slice 1: Backend deterministic recommendation + append-only decision journal substrate — commit 3ce7fe5706530d0ec68e743fff0882c76b3434cf, PR 21

## Next bounded task

- work-p2-vertical-slice-ui: Bounded UI-consumption Phase 2 implementation PR 2 of the two-PR vertical slice: surface the latest persisted goal forecast (target, projected value, probability/status, forecast timestamp, freshness indicators) and one explainable recommendation derived from the certified forecast version (reason, expected impact, assumptions, confidence, risks, freshness, provenance); capture accept/reject/defer via the Slice 1 POST /api/v1/recommendations/{recommendation_id}/decisions route; render the decision-journal history required by reload behavior. Reuse the merged Slice 1 envelopes including canonical Decimal strings, ETag, conditional-request, HATEOAS, and sanitized-error envelopes. Default-off flags unchanged (atlas_forecast_read_api_enabled remains the gating surface for both data load and action). Personal single-user scope; no household/advisor tenancy, no autonomous execution, no brokerage/transfer/trade actions. Medium risk under the new simplified tiered governance: one cohesive branch + PR + relevant UI Vitest + npm run typecheck CI + one fresh independent review + maximum two correction-and-review cycles.

Do not begin the next task automatically.

# Atlas System Health Audit

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Scope:** Phases 0–6 implementation and local personal-use readiness only. No application correction was made.
- **Related:** [Personal-Use Readiness Report](./PERSONAL_USE_READINESS_REPORT.md), [Capability Matrix](../10-roadmap/ATLAS_CAPABILITY_MATRIX.md), [Remediation Backlog](../10-roadmap/REMEDIATION_BACKLOG.md), [Personal Mode Proposal](./PERSONAL_MODE_PROPOSAL.md).

## Evidence sources

Repository contracts, ADRs, route/config/model/migration inspection, clean-main Phase 6 certification evidence, isolated synthetic E2E lifecycle, route-mocked browser tests, `start.sh --check`, tracker/status/render/handoff validation, and local test inventories. No external scanner or unpinned tool was used.

## Executive assessment

The certified Phases 0–6 implementation has strong server-authority, immutability, owner-isolation, and default-off safeguards. The principal health risk is not an observed arithmetic regression; it is the gap between a well-tested pre-production substrate and a simple, documented personal-use activation path. The audit therefore recommends activation/readiness work before any broad local enablement.

## Financial correctness

**Confirmed strengths**

- `calculations/projection.py`, `scenarios/engine.py`, canonical forecast contracts, and market briefing contracts use Decimal boundaries for authoritative money and preserve canonical strings at API boundaries.
- Scenario Lab delegates calculations to Rules Service and exposes only supported monthly contribution and dated outflow changes.
- Forecast/scenario freshness, baseline compatibility, currency, hashes, model versions, and calculation versions are represented in server contracts.
- Deterministic bands are explicitly not probabilities or guarantees.

**Risks/gaps**

- `Goal.target_amount` remains a legacy Float field before snapshot normalization (`risk-p1-legacy-goal-float`).
- Finlynq account currency is not authoritative for projection state (`risk-p1-account-currency-authority`).
- Several legacy ingestion/query and presentation modules convert values to float for compatibility/reporting. This is acceptable only when they are not the financial authority; the boundary should remain tested and documented.
- Personal-use acceptance did not exercise a full enabled forecast/scenario journey.

**Disposition:** P1 currency/activation wave; P3 legacy boundary inventory. Do not change calculations in this audit.

## Data integrity

**Confirmed strengths**

- Alembic owns Rules Service schema evolution; Scenario Lab uses additive migration `W6a1b2c3d4e5` with owner constraints, immutable version triggers, archive-preserving lifecycle, and downgrade refusal when records exist.
- Forecast, recommendation, decision, outcome, market brief, and scenario history are designed as immutable or append-only where documented.
- Idempotency hashes and conflict handling are covered by focused suites.
- Isolated E2E harness provisions a temporary SQLite database and removes its database/WAL/SHM files on exit.

**Risks/gaps**

- Rules Service and Finlynq do not have identical migration authority: Rules Service uses Alembic while Finlynq uses `Base.metadata.create_all` at startup. The shared-database transition is documented but remains an architecture risk.
- SQLite WAL snapshots require checkpointing or copying DB/WAL/SHM together; the code comments document this, but no operator backup command is provided.
- No non-destructive personal backup/restore drill was run.
- Retention/deletion policy for immutable history is unresolved for multi-user rollout.

**Disposition:** P1 retention/currency boundaries; P2 backup/recovery runbook; P3 service migration convergence.

## Security and privacy

**Confirmed strengths**

- JWT auth and single-user local identity are explicit; non-development environments reject the known dev secret.
- Owner scoping and ownership-before-disclosure behavior are tested; cross-owner resources are sanitized 404s.
- CORS is bounded to explicit local origins and decision ETag/Location response metadata only.
- Outcome evidence references are hash-only/server-derived; raw rejected values and sensitive payloads are not exposed through the Phase 3/4 contracts.
- Feature flags and provider configuration are server-owned; no client override is present.
- No credentials, personal data, email, trading, brokerage, or money movement were used in this audit.

**Risks/gaps**

- `local_user=alex` and a development JWT default are appropriate only for isolated development; no production rollout is authorized.
- Transitional tenancy and unresolved retention/deletion remain open.
- The repository contains legacy assistant/Ollama surfaces; tests use stubs, but a personal-mode policy should explicitly keep cloud LLM and execution paths disabled.

**Disposition:** Preserve current safeguards; P1 personal-use boundary documentation; no audit-time code change.

## Architecture and configuration

**Confirmed strengths**

- Final IA has one primary owner for each major analytical destination and compatibility middleware for specified legacy bookmarks.
- Rules Service, Finlynq, and UI have explicit local lifecycle and separate Python environments.
- `scripts/classify_change_scope.py` provides path-aware local validation classification; GitHub Actions is disabled by policy.
- `start.sh --check` is non-mutating and documents ports.

**Risks/gaps**

- Legacy names (`Finance Copilot`, `WealthIQ`, `CashFlix`, `Finlynq`) and compatibility layers increase discovery and maintenance cost.
- Finlynq’s shared database and create-all startup path differ from Rules Service’s explicit migration path.
- The route screenshot matrix still enumerates legacy aliases as if they were primary pages, which can drift from the final IA.
- No supported readiness/doctor surface summarizes migration head, service health, flags, or provider configuration.

**Disposition:** P2 readiness/activation; P3 terminology and inventory cleanup.

## Frontend

**Confirmed strengths**

- Shared `PageLayout`, `PageHeader`, `PageTabs`, `AnalyticalContextBar`, and `AnalyticalPageFrame` provide consistent shell behavior.
- Sidebar and typed IA contract expose the final 12 activated destinations across five groups.
- URL state and compatibility redirects preserve query parameters where required.
- Settings provides appearance mode/profile controls; tests cover Indigo, Vermilion, Ion, light/dark, reduced motion, keyboard navigation, overflow, and scoped axe findings.
- Scenario Lab and Market Intelligence use honest disabled, unavailable, stale, empty, warning, and recovery states.

**Risks/gaps**

- Legacy simulation components still exist and contain client-side Number/float calculations. They are quarantined and not rendered from Mission Control, but removal/deprecation is not complete.
- `ui/artifacts/v2.1` and the screenshot test retain compatibility routes; the final acceptance inventory should capture canonical routes directly.
- First run of the combined appearance axe journey saw a transient Next 404; the exact journey passed on rerun. This is runner reliability evidence, not a product correction.
- No full enabled local user journey was proven across all flags.

**Disposition:** P2 final acceptance harness and activation; P3 legacy simulation cleanup.

## Backend

**Confirmed strengths**

- Health endpoints expose service liveness and Rules Service git SHA metadata.
- Typed route contracts cover forecasts, recommendations, decisions/history, market briefs, and scenarios.
- Sanitized exception envelopes, explicit default-off controls, provider readiness and stale-data checks are present.
- Focused and complete local certification suites are green with synthetic data.

**Risks/gaps**

- A healthy process does not by itself prove Alembic head, shared DB parity, provider readiness, or feature availability.
- Some startup hooks seed categories/recommendations and recalculate Finlynq balances; this is operationally consequential and should be surfaced in a readiness report.
- No audit-time provider or enabled scenario mutation was attempted.

**Disposition:** P2 Atlas Doctor/readiness design; P3 startup observability and migration convergence.

## Repository health

**Confirmed strengths**

- Clean synchronized main and preserved phase tags were verified.
- Separate pinned environments and synthetic fixture inventories are documented.
- No credentials, local databases, generated screenshots, or transient test artifacts were committed by this audit.

**Candidates for follow-up**

- Definitely or very likely legacy presentation paths: `ui/components/simulation/WealthSimulationContext.tsx`, `MoneyFlowSimulator.tsx`, `LifeEventSimulator.tsx`, `WealthTimeline.tsx`, `FinancialTwin.tsx`, and related projection utility. Current references are tests/compatibility and historical documentation; removal risk is medium because compatibility coverage still exists.
- Probably stale acceptance inventory: `ui/__tests__/e2e/appearance-screenshot-matrix.spec.ts` includes aliases (`/debts`, `/universe`, `/market-briefs`, `/recommendations`) as capture routes even though they redirect.
- Compatibility code still serving a purpose: `ui/middleware.ts`, `ui/lib/moneyRoutes.ts`, and legacy route pages. Keep until bookmark telemetry or an explicit deprecation decision exists.
- Duplicate/potentially confusing presentation: `ui/app/data-connections/page.tsx` delegates to the legacy Accounts implementation intentionally; it is a single implementation, not a second authority, but the naming should be clarified.
- Float-bearing legacy/query code: `services/finance_query.py`, parsers, and legacy simulation components. Evidence does not show these replacing the certified Phase 0/6 authority; removal or boundary tests belong to a later wave.
- Feature flags: all flags found in `services/rules-service/app/config.py` have route, composer, or test references; no flag is classified definitely unused from this audit.

## Operations

**Confirmed strengths**

- `start.sh` and `stop.sh` own Atlas processes by verified working-directory trees and support port overrides.
- `scripts/test-e2e.sh` provisions a temporary database, migrates it, starts Finlynq/Rules/UI, runs Playwright, and cleans up.
- Health probes and sanitized logs are available.

**Risks/gaps**

- Normal startup still requires two Python environments, Node dependencies, and a shared local DB convention.
- `start.sh` forces the Rules Service database path to `services/rules-service/finance.db`; operators must use the hermetic E2E harness for mutation testing.
- There is no one-command doctor/readiness report or documented personal backup/restore command.
- GitHub is storage/history only; local validation evidence is authoritative and hosted CI is intentionally disabled.

## Overall disposition

No audit finding justifies weakening a financial, ownership, privacy, immutable-history, or feature-flag safeguard. The first remediation should make safe personal activation observable and repeatable, then address currency/backup risks before cleanup or polish.

# Atlas AI CFO + AI Investment Intelligence — Implementation Plan

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Plan date:** 2026-08-30  
**Status:** Planning only — no implementation authorization  
**Product boundary:** Personal, single-user, pre-production. Atlas analyzes and recommends; the user decides. No automatic trading, brokerage orders, transfers, or money movement.

## 1. Purpose and planning authority

This plan turns the completed architecture work into independently testable implementation slices. It is based on:

- `docs/architecture/ATLAS-INVESTMENT-INTELLIGENCE-AUDIT.md`
- `docs/architecture/ATLAS-OPEN-SOURCE-INVESTMENT-STACK.md`
- `docs/architecture/ATLAS-INVESTMENT-INTELLIGENCE-DOMAIN.md`
- `docs/architecture/ATLAS-INVESTMENT-COMMITTEE.md`
- `docs/02-architecture/ATLAS_AGENT_ARCHITECTURE.md`
- `docs/04-ai-agents/AGENT_OVERVIEW.md`
- `docs/09-decisions/ADR-001-SPECIALIZED-AGENTS.md`
- `docs/09-decisions/ADR-002-CANONICAL-FINANCIAL-CORE.md`
- `docs/09-decisions/ADR-004-EVENTED-HISTORY.md`
- `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`
- current project status in `docs/10-roadmap/PROJECT_STATUS.json`

The completed project is currently marked **phase-6 complete**, with the explicit instruction not to begin Phase 7. This document is therefore a proposed future Investment Intelligence roadmap, not a claim that implementation should begin now.

## 2. Non-negotiable principles

1. **Extend Atlas; do not create a parallel finance platform.** Use the Rules Service intelligence, forecast/recommendation, decision-journal, outcome, and assistant boundaries.
2. **Canonical authority stays deterministic.** Portfolio reconstruction, money arithmetic, valuations, risk, scores, policy gates, and recommendation identity are not delegated to an LLM.
3. **Reuse before adaptation before building.** Existing holdings and Market Intelligence contracts are transitional inputs; mature libraries are bounded computation dependencies only after license/data review.
4. **One recommendation lifecycle.** Extend existing `Recommendation`, decision, and outcome semantics rather than introducing a second lifecycle.
5. **Evidence is mandatory.** Every material claim has a source or deterministic calculation reference, timestamp/as-of, version, and quality status.
6. **Fail closed.** Unknown identity, unsupported asset, ambiguous currency, stale/partial portfolio, invalid backtest, missing suitability context, or malformed AI output blocks or downgrades the result.
7. **Immutable history.** New inputs or conclusions create new versions/runs; previous recommendations, decisions, and outcomes are never rewritten.
8. **No execution capability.** No broker credentials, order routes, execution tools, transfer tools, or money movement are part of any phase in this plan.
9. **Every phase is reversible and testable.** Feature flags, additive migrations, synthetic fixtures, focused tests, and compatibility projections are required.
10. **Personal-use scope remains explicit.** The existing retention/deletion blocker and transitional tenancy risk continue to block external multi-user rollout.

## Program phase vocabulary

Investment Intelligence uses independent program phase IDs `INV-01` through `INV-12`. These are not Atlas global project phases; the global roadmap continues to use `phase-*`. Completing an `INV-*` phase does not advance or authorize unrelated Atlas work.

| Program ID | Capability |
|---|---|
| INV-01 | Investment Intelligence Foundation |
| INV-02 | Market & Security Data |
| INV-03 | Portfolio Intelligence |
| INV-04 | Fundamental Research |
| INV-05 | Technical Research |
| INV-06 | Macro Intelligence |
| INV-07 | Quantitative Research |
| INV-08 | AI Investment Committee |
| INV-09 | Investment Recommendations |
| INV-10 | CIO Reporting |
| INV-11 | Recommendation Tracking |
| INV-12 | Evaluation & Backtesting |

## Global Atlas phases versus Investment Intelligence phases

Global Atlas `phase-*` advancement is controlled only by the canonical roadmap, project status, and `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`. `INV-*` advancement is a bounded workstream inside separately authorized scope. An `INV-*` milestone does not advance or authorize global Atlas work.

## Program-level authorization

A separate, explicit user authorization may approve the complete bounded program `INV-01 → INV-12` for autonomous advancement in dependency order. Once active, the agent may proceed through ordinary approved `INV-*` phases without requesting confirmation between them. This authorization never permits automatic trading, broker orders, rebalancing, money movement, credential acquisition, destructive production actions, unauthorized personal-data access, unapproved architecture changes, unrelated product work, global phase advancement, or bypassing validation, ownership, privacy, provenance, recovery, review, or approval gates.

`docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` remains authoritative. Its mandatory stop conditions—including unknown financial facts, unauthorized access or mutation, destructive operations, credentials, external-provider activation, trading/execution, material expansion, failed integrity/recovery preconditions, persistent tool failure, or insufficient resources—pause or end the program. The user may revoke or narrow authorization at any time.

## Program phase gates

Each `INV-*` phase has an entry gate, bounded task sequence, and exit gate. Entry requires dependencies complete, authorization active, required ADRs approved, scope unchanged, blockers clear, and fixtures available. Exit requires acceptance criteria, focused validation evidence, review requirements, rollback understanding, and no mandatory global stop condition. These gates operationalize, but do not replace or strengthen, the canonical policy.

## Human decision boundary

```text
Research → Analysis → Recommendation → User Decision

Never: Research → Analysis → Recommendation → Automatic Execution
```

## Investment Data Authority Invariants

```text
Current Holding ≠ Historical Investment Truth
Unknown ≠ Zero
Missing ≠ No Change
Stale ≠ Current
Estimated ≠ Observed
LLM Claim ≠ Financial Fact
```

A current holding is only a current-state observation and cannot establish historical lots, cost basis, or performance. Unknown must remain distinguishable from zero so exposure is not silently understated. Missing data is not evidence of no change. Stale observations must not be presented as current. Estimates require assumptions and must not be labeled observed facts. LLM claims are interpretations requiring validated evidence and cannot become canonical financial facts. These distinctions are mandatory in contracts, calculations, provenance, API/UI status, and tests.

# 3. Dependency gates before Investment Intelligence program

Before implementation of the first investment slice, the owner must explicitly authorize a new phase and confirm:

- current phase-6 release-candidate status remains intact;
- the dirty worktree is understood and unrelated changes are not overwritten;
- separate Python environments are used for Rules Service and Finlynq;
- exact numeric and currency authority is defined for investment data;
- security identity and unresolved-identity behavior are approved;
- portfolio history completeness and migration limits are understood;
- provider credentials/external calls remain default-off;
- retention/deletion policy remains a multi-user rollout blocker, not silently solved by this work;
- a new ADR is recorded for the canonical investment model and authority boundary;
- phase-level risk classification is applied before high-risk implementation.

No phase may use existing Float holdings as if they were exact historical investment truth, and no phase may claim full cost basis/performance when only current holdings are available.

## 4. Phase ordering

The correct implementation order is:

| Phase | Name | Primary outcome | Depends on |
|---|---|---|---|
| INV-01 | Investment Intelligence foundation | Stable identities, ownership, immutable context/evidence contracts, feature gates | Phase-6 baseline; new domain ADR |
| INV-02 | Market/security data | Validated security master and market observations | INV-01 |
| INV-03 | Portfolio intelligence | Canonical portfolio snapshots and deterministic analytics | INV-01, INV-02 |
| INV-04 | Fundamental research | Filing/fact/statement evidence and deterministic fundamental metrics | INV-01, INV-02; INV-03 for portfolio fit |
| INV-05 | Technical research | Point-in-time technical metrics/signals | INV-02, INV-03 |
| INV-06 | Macro intelligence | Macro observations, regimes, and sector context | INV-02; evidence foundation |
| INV-07 | Quant research | Factors, risk, optimization/backtesting research contracts | INV-02, INV-03, INV-05; leakage controls |
| INV-08 | AI Investment Committee | Typed specialist findings, bull/bear challenge, chair draft | INV-03, INV-04; selected INV-05–G |
| INV-09 | Investment recommendations | Existing lifecycle extension and user-facing recommendation | INV-08 plus all deterministic gates |
| INV-10 | CIO reports | Daily/weekly/monthly evidence-backed reports | INV-09; scheduling/operational approval |
| INV-11 | Recommendation tracking | Supersession, decisions, review, and outcome measurement | INV-09, existing decision/outcome infrastructure |
| INV-12 | Backtesting/evaluation | Historical replay, calibration, and committee evaluation | INV-07, INV-08, INV-09, INV-11 |

The order deliberately puts canonical identity and portfolio state before AI, reports, and recommendation delivery. INV-05 and INV-06 may be developed in parallel after their input contracts stabilize. INV-07 is later because point-in-time datasets and leakage controls are high risk. INV-08 must not begin as a prompt-only feature.

---

# 5. Phase INV-01 — Investment Intelligence foundation

## Objective

Create the shared contracts and authority boundaries needed for investment data, evidence, analysis runs, and portfolio context without yet generating investment recommendations.

## Scope

- Define stable `Security` identity contract and unresolved/unsupported states.
- Define owner/account scope for investment context.
- Define immutable evidence references/packets and analysis-run metadata.
- Define exact Decimal/currency/as-of/freshness/version rules.
- Define read-only investment tool boundary for the existing assistant orchestrator.
- Add default-off flags and sanitized failure classes.
- Record the canonical investment-model ADR.

Out of scope: live provider activation, portfolio migration, AI committee generation, recommendation persistence, trading, and execution.

## Dependencies

Current Rules Service models/routes/configuration; existing Market Intelligence contracts; existing forecast/recommendation schemas; auth and ownership helpers; evented-history rules; project status and migration conventions.

## Exact repository paths

**New files proposed:**

- `docs/09-decisions/ADR-INVESTMENT-001-CANONICAL-INVESTMENT-AUTHORITY.md`
- `services/rules-service/app/investments/__init__.py`
- `services/rules-service/app/investments/contracts.py`
- `services/rules-service/app/investments/errors.py`
- `services/rules-service/app/investments/context.py`
- `services/rules-service/tests/test_investment_foundation_contracts.py`
- `services/rules-service/tests/fixtures/investment_contexts_v1.json`

**Modified files proposed:**

- `services/rules-service/app/config.py`
- `services/rules-service/app/main.py`
- `services/rules-service/app/market_intelligence/contracts.py`
- `services/rules-service/app/services/assistant_orchestrator.py`
- `services/rules-service/app/schemas/__init__.py`
- `services/rules-service/tests/conftest.py` only if shared fixture wiring is necessary
- `docs/07-engineering/API_SPECIFICATION.md`
- `docs/07-engineering/DATABASE_SCHEMA.md`

**Schema changes:** None required for the first contract slice. If run/evidence metadata must persist, use a separately reviewed additive migration after contract tests.

## APIs

Design only initially. Proposed future read-only boundaries:

- `GET /api/v1/investments/context`
- `GET /api/v1/investments/evidence/{evidence_id}`
- `POST /api/v1/investments/analysis-runs` — analysis request only, no client authority over facts

Do not expose these routes until ownership, response minimization, and persistence semantics are tested.

## Tests

Contract tests for Decimal finiteness, USD/currency fail-closed behavior, RFC-3339 UTC timestamps, owner scope, bounded collections, evidence hashes, schema versions, default-off flags, prohibited execution capabilities, and sanitized errors. Add AST/import tests proving no foundation contract imports broker/order modules.

## Acceptance criteria

- Canonical investment context has a versioned, deterministic hash.
- Unresolved identity, unsupported asset, stale data, and ambiguous currency have explicit states.
- Client input cannot forge authoritative portfolio/evidence fields.
- Evidence references are bounded and privacy-safe.
- Existing assistant tool registry remains allowlisted and no execution tool exists.
- Existing tests remain green and no existing feature behavior changes.

## Rollback strategy

Contract-only changes can be disabled by flags and removed without data migration. If persistence is introduced, use additive tables and a row-count-guarded downgrade; preserve existing history.

## Risks

Premature model freezing, confusing source evidence with canonical facts, leakage of sensitive holdings through context, and accidental coupling to provider-specific payloads.

## Security considerations

Authenticate and authorize owner scope before context assembly; keep credentials server-side; do not log raw holdings or provider payloads; treat external text as data; retain no execution capability.

## Agent tasks

### INV-01-01 — Approve canonical investment authority

- **Objective:** Record the exact ownership between Finlynq, Rules Service, deterministic calculations, evidence providers, and AI.
- **Inputs:** Completed audit, domain design, ADR-001/002/004, current service boundaries.
- **Files:** New ADR under `docs/09-decisions/`; update architecture index if one exists.
- **Implementation requirements:** State canonical sources, immutable/versioned records, Float migration limits, currency policy, no-trading boundary, and rollback assumptions.
- **Tests:** Documentation/status validation and link/path checks.
- **Acceptance:** No ambiguous authority remains; ADR does not claim unimplemented models.

### INV-01-02 — Define versioned investment context contracts

- **Objective:** Create provider-neutral, privacy-safe context/evidence/run contracts.
- **Inputs:** Domain object classifications and current Market Intelligence contracts.
- **Files:** `services/rules-service/app/investments/contracts.py`, `context.py`, `errors.py`, focused tests/fixtures.
- **Implementation requirements:** Strict schemas, bounded fields, Decimal-safe values, UTC as-of, source/calculation references, owner scope, explicit omissions, no raw credentials.
- **Tests:** Contract, serialization, hashing, privacy, and fail-closed tests.
- **Acceptance:** Identical canonical inputs hash identically; unauthorized or malformed context is rejected.

### INV-01-03 — Add default-off investment configuration

- **Objective:** Gate future investment data and analysis without activating providers.
- **Inputs:** Existing configuration conventions and provider-safety risks.
- **Files:** `services/rules-service/app/config.py`, `.env.example` only if safe/documentary, config tests.
- **Implementation requirements:** Separate read/generation/external-provider/scheduling flags; safe defaults; no credential values.
- **Tests:** Default-off and explicit-enable tests; environment parsing tests.
- **Acceptance:** Fresh configuration cannot call an external provider or generate a recommendation.

### INV-01-04 — Define read-only assistant boundary

- **Objective:** Establish how the existing assistant may request investment context later.
- **Inputs:** `assistant_orchestrator.py`, `llm_client.py`, existing tool whitelist.
- **Files:** Existing orchestrator/tool-contract files and focused assistant tests.
- **Implementation requirements:** Tools return evidence/calculation references only; model cannot supply authoritative values; no broker/order vocabulary accepted as an action.
- **Tests:** Tool allowlist, malformed model response, prompt-injection, privacy, and offline behavior.
- **Acceptance:** Investment assistant requests cannot mutate canonical state or execute anything.

---

# 6. Phase INV-02 — Market/security data

## Pre-authority evaluation harness

Before `INV-08` or `INV-09` becomes production-authoritative, a lightweight evaluation harness must pass factual accuracy, evidence coverage and correctness, citation correctness, deterministic calculation-reference correctness, structured-output validity, replay consistency, confidence-score reproducibility, stale-data detection, hallucination/invented-number detection, Bull/Bear disagreement preservation, prompt-injection resistance, and ownership isolation. Full historical replay, outcome calibration, and comprehensive backtesting remain in `INV-12`. This is `INV-01-05` and is an exit prerequisite for `INV-08` and `INV-09`.


## Objective

Build a stable instrument identity and immutable, provider-neutral market-observation layer for equities, ETFs, indexes, and explicitly supported instruments.

## Scope

- `Security` identity, aliases, provider identifiers, issuer/company link where available.
- Instrument type and support status.
- Immutable price/volume/benchmark observations with source, currency, timestamp, freshness, and corporate-action basis.
- Provider adapters behind existing Market Intelligence composition, using synthetic fixtures first.
- SEC/Finnhub/other existing adapters reused where contracts fit; no new provider without approval.

## Dependencies

INV-01; current `Holding` routes/models; existing `market_intelligence` contracts, adapters, caching, pacing, and normalized failures.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/securities.py`
- `services/rules-service/app/investments/market_observations.py`
- `services/rules-service/app/market_intelligence/security_adapters.py`
- `services/rules-service/alembic/versions/<id>_add_security_identity.py`
- `services/rules-service/alembic/versions/<id>_add_market_observations.py`
- `services/rules-service/tests/test_security_identity.py`
- `services/rules-service/tests/test_market_observations.py`
- `services/rules-service/tests/fixtures/security_observations_v1.json`

**Modified files proposed:**

- `services/rules-service/app/models/__init__.py`
- `services/rules-service/app/market_intelligence/contracts.py`
- `services/rules-service/app/market_intelligence/adapters.py`
- `services/rules-service/app/market_intelligence/composition.py`
- `services/rules-service/app/routes/holdings.py` only for an additive identity-resolution projection
- `services/rules-service/app/main.py`
- `services/rules-service/tests/test_routes_holdings.py`
- `docs/07-engineering/DATABASE_SCHEMA.md`
- `docs/07-engineering/API_SPECIFICATION.md`

**Schema changes:** Additive `securities`, identifier-mapping, and immutable market-observation structures. Preserve legacy Holding rows and source values. Include unique stable IDs, provider/source metadata, UTC timestamps, currency, version/hash, and explicit unresolved status.

## APIs

- `GET /api/v1/investments/securities/{id}`
- `GET /api/v1/investments/securities/resolve?symbol=...` — owner-safe and ambiguity-aware
- `GET /api/v1/investments/securities/{id}/market-observations`

Generation/provider routes must remain server-owned and default-off.

## Tests

Identity normalization, symbol changes, share classes, ambiguous matches, unsupported instruments, duplicate observations, corporate-action basis, stale quote handling, source URL/token rejection, provider failure normalization, rate limiting/cache, ownership isolation, migration upgrade/downgrade, SQLite/PostgreSQL parity where applicable, and no-network tests.

## Acceptance criteria

- Ticker text is never used as security identity.
- Every supported observation has source, currency, as-of, freshness, and version/hash.
- Ambiguous/unresolved identities cannot feed security-specific recommendations.
- Existing holdings UI/routes remain usable.
- External calls are disabled in tests and by default.

## Rollback strategy

Disable identity/observation reads and retain additive records. Keep the legacy Holding projection operational. Do not delete imported source records or rewrite historical observations.

## Risks

Provider identifier mismatch, delisted/security-corporate-action errors, stale prices mislabeled as live, and accidental unsupported-instrument equity assumptions.

## Security considerations

Provider credentials stay server-side; source URLs are sanitized; identity resolution is owner-aware where user holdings are involved; public security metadata must not expose private ownership annotations.

## Agent tasks

### INV-02-01 — Implement Security identity contract and model

- **Objective:** Introduce stable security identity without replacing `Holding`.
- **Inputs:** INV-01 contracts, current Holding model/routes, provider identifier research.
- **Files:** `app/investments/securities.py`, model exports, additive migration, focused tests.
- **Implementation requirements:** UUID/internal ID, instrument type, issuer/company reference placeholder, effective-dated identifiers, unresolved state, strict ownership rules for private annotations.
- **Tests:** Identity, ambiguity, unsupported asset, migration, and ownership tests.
- **Acceptance:** Existing symbol-based holdings can map to a resolved or explicit unresolved state without silent guessing.

### INV-02-02 — Add immutable market observations

- **Objective:** Store validated point-in-time market data for supported instruments.
- **Inputs:** Market Intelligence contracts/adapters and security identity.
- **Files:** Observation model/service/migration/tests/fixtures.
- **Implementation requirements:** Decimal price/volume where applicable, currency, observed/effective/retrieved times, source, freshness, corporate-action basis, hash, immutable writes.
- **Tests:** Numeric, timestamp, duplicate/idempotency, stale/failure, and immutability tests.
- **Acceptance:** Same source observation is idempotent; corrections create new versions.

### INV-02-03 — Add provider adapter mapping

- **Objective:** Reuse existing normalized provider adapters for security and market data.
- **Inputs:** Existing Finnhub/SEC adapters and open-source research decisions.
- **Files:** `app/market_intelligence/security_adapters.py`, composition/config/tests.
- **Implementation requirements:** No direct provider payload in domain models; safe pacing/cache; normalized failures; no network in unit tests.
- **Tests:** Synthetic transport and provider contract suite.
- **Acceptance:** Provider outage produces an explicit unavailable result and no fabricated observation.

### INV-02-04 — Build legacy Holding compatibility projection

- **Objective:** Make current holdings analyzable without claiming historical completeness.
- **Inputs:** Existing Account/Holding data and unresolved identity rules.
- **Files:** Holdings route/service, migration/projection tests, documentation.
- **Implementation requirements:** Preserve source values/provenance; expose data-quality flags; use exact normalization only where approved; no automatic deletion or rewrite.
- **Tests:** Existing holding regressions plus migrated/resolved/unresolved fixtures.
- **Acceptance:** Legacy portfolio remains functional and the investment layer clearly reports coverage/precision limits.

---

# 7. Phase INV-03 — Portfolio intelligence

## Objective

Create immutable owner-scoped portfolio snapshots and deterministic portfolio analytics that answer allocation, concentration, performance, liquidity, risk, and portfolio-fit questions.

## Scope

- Transaction/position/lot compatibility layer and snapshot reconstruction.
- Cash, positions, unknown/unclassified holdings, valuation basis, currency status, reconciliation status.
- Allocation, issuer/sector/industry/geography/market-cap/factor exposure where data exists.
- Cost basis, realized/unrealized, TWR/MWR, volatility, correlation, drawdown, beta, liquidity, risk contribution.
- Hypothetical portfolio impact for bounded proposed exposure, without mutation or order creation.
- Goal and liquidity context reuse from existing goal/forecast services.

## Dependencies

INV-01, INV-02, existing Accounts/Holdings/Transactions, exact-value authority, goal and forecast context, existing recommendation/decision infrastructure.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/portfolio_snapshots.py`
- `services/rules-service/app/investments/portfolio_analytics.py`
- `services/rules-service/app/investments/portfolio_impact.py`
- `services/rules-service/app/investments/lot_reconstruction.py`
- `services/rules-service/alembic/versions/<id>_add_portfolio_snapshots.py`
- `services/rules-service/tests/test_portfolio_snapshots.py`
- `services/rules-service/tests/test_portfolio_analytics.py`
- `services/rules-service/tests/test_portfolio_impact.py`
- `services/rules-service/tests/fixtures/portfolio_investment_cases_v1.json`

**Modified files proposed:**

- `services/rules-service/app/models/holding.py`
- `services/rules-service/app/models/account.py`
- transaction model/service paths discovered during implementation
- `services/rules-service/app/forecasts/recommendations.py`
- goal/forecast context service paths
- `services/rules-service/app/routes/holdings.py`
- `services/rules-service/app/routes/recommendations_derived.py` only for future references
- `docs/03-domain-model/FINANCIAL_ENTITIES.md`
- `docs/07-engineering/DATABASE_SCHEMA.md`

**Schema changes:** Additive immutable portfolio snapshots, position snapshots, valuation references, reconciliation/data-quality status, and optional lot/transaction-normalization records. Do not mutate legacy history.

## APIs

- `GET /api/v1/investments/portfolio-snapshots`
- `GET /api/v1/investments/portfolio-snapshots/{id}`
- `GET /api/v1/investments/portfolio-analytics`
- `POST /api/v1/investments/portfolio-impact/preview` — deterministic hypothetical calculation only; no persistence or execution

## Tests

Use financial fixtures for Decimal arithmetic, deposits/withdrawals, dividends, fees, splits, partial history, unknown holdings, mixed currency, stale prices, cost-basis gaps, TWR/MWR, allocation/look-through, risk metrics, goal impact, idempotent snapshot hashing, authorization, and SQLite/PostgreSQL parity.

## Acceptance criteria

- Snapshot is immutable, owner-scoped, and hash-bound to exact inputs.
- Legacy Float/incomplete histories are visibly marked and never overclaimed.
- Mixed/unknown currency and unresolved holdings fail closed for affected metrics.
- Portfolio impact compares baseline/hypothetical state without mutation.
- Recommendations cannot use a partial snapshot for portfolio-wide claims.

## Rollback strategy

Feature-gate snapshot reads and retain legacy holding routes. Additive records can be left as unresolved; no destructive migration. Disable analytics generation while preserving snapshots/history.

## Risks

Financial correctness, corporate-action handling, missing lots, cash-flow timing, currency conversion, duplicate calculation engines, and false portfolio coverage.

## Security considerations

Strict owner/account checks before existence-sensitive reads; aggregate context sent to agents; tax-lot detail minimized; no raw account identifiers in prompts/logs; immutable audit trail.

## Agent tasks

### INV-03-01 — Reconstruct positions and portfolio snapshots

- **Objective:** Produce an immutable snapshot from supported canonical inputs and explicit completeness status.
- **Inputs:** Security identity, holdings/transactions, market observations, currency authority.
- **Files:** Snapshot/lot services, model/migration, focused tests/fixtures.
- **Implementation requirements:** Deterministic ordering, Decimal arithmetic, source/provenance, unresolved/omitted positions, canonical hash, idempotency.
- **Tests:** Reconstruction, partial history, ownership, replay, and migration tests.
- **Acceptance:** Same inputs produce the same snapshot; incomplete history is never presented as complete.

### INV-03-02 — Implement allocation and exposure analytics

- **Objective:** Calculate deterministic allocation and concentration metrics.
- **Inputs:** Frozen portfolio snapshot and classifications.
- **Files:** `portfolio_analytics.py`, tests.
- **Implementation requirements:** Explicit denominator/cash/unknown treatment, look-through limitations, versioned formulas, finite Decimal/float boundaries.
- **Tests:** Allocation/concentration/sector/geography fixtures and unknown classification cases.
- **Acceptance:** Every result identifies scope, as-of, formula/version, and omissions.

### INV-03-03 — Implement performance and risk analytics

- **Objective:** Calculate performance and risk metrics without duplicating existing financial engines.
- **Inputs:** Snapshot history, transaction/cash-flow events, market observations.
- **Files:** Existing reusable calculation modules plus investment analytics adapter; new code only for missing metrics.
- **Implementation requirements:** TWR/MWR semantics, fees/dividends, benchmark, volatility/correlation/drawdown/liquidity, deterministic versions.
- **Tests:** Golden numeric fixtures and edge cases.
- **Acceptance:** Calculation authority is documented and no competing formula silently exists.

### INV-03-04 — Implement deterministic portfolio impact

- **Objective:** Compare current and bounded hypothetical exposure for an investment candidate.
- **Inputs:** Frozen snapshot, candidate security/observation, proposed exposure scenario, goals/policy.
- **Files:** `portfolio_impact.py`, goal integration, tests.
- **Implementation requirements:** No order representation; current/proposed weights, concentration/risk/liquidity/goal effects, assumptions and confidence.
- **Tests:** ADD/BUY/REDUCE/SELL hypothetical cases, policy violations, missing data, no mutation.
- **Acceptance:** Impact is reproducible and cannot be used to place or prepare an order.

---

# 8. Phase INV-04 — Fundamental research

## Objective

Create validated company/fundamental evidence and deterministic metrics that an analyst can interpret without inventing facts.

## Scope

- Company identity where issuer data exists.
- SEC filing identity, normalized facts, statements, periods, units, currencies, and as-known-at/vintage metadata.
- Earnings events/results and source-cited research evidence.
- Deterministic ratios, margins, FCF, profitability, balance-sheet, growth, and valuation ranges.
- Primary-source preference and restatement preservation.

## Dependencies

INV-01/B and INV-03 portfolio context. Existing SEC/earnings/Market Intelligence contracts. Open-source EdgarTools may be evaluated in an isolated compatibility/license spike before adoption; it is not assumed to be a dependency.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/fundamentals.py`
- `services/rules-service/app/investments/filings.py`
- `services/rules-service/app/investments/financial_facts.py`
- `services/rules-service/app/investments/valuation.py`
- `services/rules-service/alembic/versions/<id>_add_fundamental_evidence.py`
- `services/rules-service/tests/test_fundamental_facts.py`
- `services/rules-service/tests/test_valuation.py`
- `services/rules-service/tests/fixtures/fundamental_cases_v1.json`

**Modified files proposed:**

- `services/rules-service/app/market_intelligence/contracts.py`
- existing SEC/earnings adapters and composition paths
- `services/rules-service/app/models/market_brief.py` only if shared evidence projection is appropriate
- `services/rules-service/tests/test_market_intelligence_foundation.py`
- `docs/03-domain-model/INVESTMENT_MODEL.md`
- `docs/07-engineering/DATABASE_SCHEMA.md`

**Schema changes:** Additive immutable filing/fact/statement/evidence records; source accession/URL/hash, period, unit, currency, filing/retrieval/as-known-at timestamps, extraction/calculation version, and restatement linkage.

## APIs

- `GET /api/v1/investments/companies/{id}`
- `GET /api/v1/investments/securities/{id}/fundamentals`
- `GET /api/v1/investments/securities/{id}/filings`
- `GET /api/v1/investments/securities/{id}/earnings`

## Tests

SEC identity/form/accession validation, XBRL units, period/vintage, restatement versions, missing facts, ratio/valuation fixtures, currency failure, source URL safety, earnings freshness, provider outage, deduplication, and no-network adapter tests.

## Acceptance criteria

- No fundamental number exists without source/version/unit/currency/as-of metadata.
- Restated data does not rewrite what was previously known.
- Valuation outputs are deterministic ranges with explicit assumptions.
- AI cannot create or modify fundamental facts.
- Missing fundamentals downgrade or block recommendations.

## Rollback strategy

Disable fundamental reads and preserve immutable evidence. Do not delete filings/facts or replace legacy market brief records.

## Risks

XBRL taxonomy inconsistency, restatements, issuer/security mismatch, unlicensed transcript/news data, and false precision in valuation.

## Security considerations

Sanitize filings/news before model exposure; preserve public-source provenance; never expose provider credentials; authorize private portfolio linkage separately from public company facts.

## Agent tasks

### INV-04-01 — Normalize filing and fact evidence

- **Objective:** Build immutable primary-source evidence contracts and adapter mappings.
- **Inputs:** Existing SEC contracts/adapters, provider research, INV-02 Security identity.
- **Files:** Fundamental/filing/fact services, migrations, tests/fixtures.
- **Implementation requirements:** Preserve accession/form/CIK, units, periods, currencies, vintage, source hash, extraction status, and omissions.
- **Tests:** Synthetic SEC filings/XBRL fixtures, restatement and malformed-input tests.
- **Acceptance:** A fact is traceable to a validated source and cannot be silently overwritten.

### INV-04-02 — Implement deterministic fundamental metrics

- **Objective:** Calculate ratios and quality/growth/profitability metrics from validated facts.
- **Inputs:** Immutable facts/statements and market observations.
- **Files:** `fundamentals.py`, tests.
- **Implementation requirements:** Version formulas, reject incompatible periods/units/currencies, expose missing inputs and sensitivity.
- **Tests:** Golden fixtures and fail-closed cases.
- **Acceptance:** AI receives metric references, not responsibility for arithmetic.

### INV-04-03 — Implement valuation range service

- **Objective:** Produce explicit method/version/assumption-bound valuation ranges.
- **Inputs:** Validated facts, price, shares/market data where supported, scenario assumptions.
- **Files:** `valuation.py`, tests/docs.
- **Implementation requirements:** No free-text valuation numbers; finite ranges; sensitivity and uncertainty; no investment action.
- **Tests:** DCF/multiple/scenario fixtures, invalid-input and assumption-sensitivity tests.
- **Acceptance:** Valuation cannot be presented as a guaranteed target or hidden model output.

### INV-04-04 — Evaluate EdgarTools compatibility

- **Objective:** Decide whether EdgarTools reduces custom SEC parsing without compromising licensing/data contracts.
- **Inputs:** Open-source stack research and Atlas SEC requirements.
- **Files:** Compatibility note under `docs/architecture/` or `docs/adr/`; no production dependency in the spike.
- **Implementation requirements:** Test isolated parsing against synthetic/approved fixtures; record license, API, release, data terms, and fallback plan.
- **Tests:** Compatibility fixture suite only.
- **Acceptance:** Adopt, defer, or reject decision is documented before dependency addition.

---

# 9. Phase INV-05 — Technical research

## Objective

Provide deterministic, point-in-time technical metrics for interpretation where they are relevant to the user’s horizon.

## Scope

Trend, momentum, volatility, volume, relative strength, support/resistance references, benchmark-relative behavior, and regime indicators. Technical outputs are signals, not recommendations or guarantees.

## Dependencies

INV-02 market observations and INV-03 portfolio snapshots. No technical AI should run before deterministic metrics exist.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/technicals.py`
- `services/rules-service/tests/test_technicals.py`
- `services/rules-service/tests/fixtures/technical_cases_v1.json`

**Modified files proposed:**

- `services/rules-service/app/market_intelligence/contracts.py` for signal references if needed
- `services/rules-service/app/config.py` only for feature gating
- `docs/03-domain-model/INVESTMENT_MODEL.md`

**Schema changes:** Prefer versioned derived signal records or calculation payload references before adding persistent tables. If persistence is justified, use immutable signal outputs with input-window/hash/version fields.

## APIs

- `GET /api/v1/investments/securities/{id}/technical-signals`
- `GET /api/v1/investments/portfolio-analytics/technical-context`

## Tests

Indicator golden fixtures, insufficient-window behavior, corporate actions, missing volume, timezone/as-of rules, benchmark mismatch, deterministic replay, no-look-ahead, and stale-data handling.

## Acceptance criteria

- Every signal identifies window, formula/version, input snapshot, and limitations.
- No signal claims future certainty.
- Stale/insufficient history returns unavailable rather than fabricated values.
- Technical outputs cannot bypass portfolio/risk gates.

## Rollback strategy

Disable technical signal generation and retain market observations. No recommendation record is mutated.

## Risks/security

Overfitting, look-ahead bias, indicator misuse, stale prices, and excessive personal portfolio detail in model prompts. Use bounded aggregate context and immutable calculation references.

## Agent tasks

### INV-05-01 — Implement technical signal calculators

- **Objective:** Calculate versioned technical metrics from immutable market observations.
- **Inputs:** Point-in-time price/volume windows and benchmark observations.
- **Files:** `technicals.py`, fixtures/tests.
- **Implementation requirements:** Explicit windows, corporate-action basis, finite values, missing-data states.
- **Tests:** Golden numeric and leakage/freshness tests.
- **Acceptance:** Reproducible signals with no network or model dependency.

### INV-05-02 — Expose technical evidence packet

- **Objective:** Make signals available as bounded evidence to later analysts.
- **Inputs:** INV-01 evidence contracts and INV-05 outputs.
- **Files:** Market Intelligence composition/contracts, tests.
- **Implementation requirements:** References/hashes, source/calculation version, omissions, no direct recommendation action.
- **Tests:** Schema/citation/privacy tests.
- **Acceptance:** A model cannot receive an untraceable chart claim.

---

# 10. Phase INV-06 — Macro intelligence

## Objective

Add validated macro observations and deterministic context summaries that analysts may interpret without claiming causal certainty.

## Scope

Rates, inflation, employment, GDP, liquidity, yield curve, monetary policy, market regime, sector rotation, and economic-calendar events where licensed/available. Prefer existing provider-neutral Market Intelligence contracts and FRED-compatible adapters after data-term review.

## Dependencies

INV-01 evidence; INV-02 market observations. Portfolio integration from INV-03 is required for portfolio-impact claims.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/macro.py`
- `services/rules-service/app/investments/regimes.py`
- `services/rules-service/tests/test_macro.py`
- `services/rules-service/tests/fixtures/macro_cases_v1.json`

**Modified files proposed:**

- `services/rules-service/app/market_intelligence/contracts.py`
- existing provider adapters/configuration
- `docs/03-domain-model/INVESTMENT_MODEL.md`

**Schema changes:** Additive immutable macro observations and derived regime outputs only if replay/briefing requirements justify persistence.

## APIs

- `GET /api/v1/investments/macro/observations`
- `GET /api/v1/investments/macro/context`
- `GET /api/v1/investments/portfolios/{id}/macro-impact`

## Tests

Vintage/as-known-at tests, revisions, frequency/unit/currency, yield-curve construction, missing series, provider outage, regime reproducibility, source citation, and ownership-safe portfolio linkage.

## Acceptance criteria

- Macro values carry period, observation date, vintage/retrieval date, source, unit, and revision state.
- Regime outputs are deterministic and explicitly uncertain.
- Macro context cannot override portfolio or policy gates.

## Rollback strategy

Disable macro retrieval/regime projection; retain immutable observations and prior reports.

## Risks/security

Revisions mistaken for historical knowledge, causal overclaiming, provider data terms, and unnecessary private portfolio exposure.

## Agent tasks

### INV-06-01 — Normalize macro observations

- **Objective:** Add provider-neutral macro evidence using approved sources.
- **Inputs:** Existing Market Intelligence adapter patterns and license/data review.
- **Files:** Macro contracts/adapters/tests/fixtures.
- **Implementation requirements:** Vintage, units, frequency, source, revision, freshness, and default-off external access.
- **Tests:** Synthetic vintage/revision/failure suite.
- **Acceptance:** Historical analyses use the correct as-known-at value.

### INV-06-02 — Calculate regime/context summaries

- **Objective:** Produce deterministic summaries for analyst interpretation.
- **Inputs:** Immutable macro and market observations.
- **Files:** `regimes.py`, tests.
- **Implementation requirements:** Version formulas, disclose missing series and uncertainty, no action mapping.
- **Tests:** Reproducibility and missing-data fixtures.
- **Acceptance:** Regime is contextual evidence only, never an automatic action.

---

# 11. Phase INV-07 — Quant research

## Objective

Add validated factor, risk, optimization, and backtesting research capabilities without allowing research output to bypass portfolio, evidence, or policy gates.

## Scope

- Factor signals, expected-return estimates, volatility/correlation, risk-adjusted metrics.
- Optional bounded portfolio optimization using a reviewed library such as Riskfolio-Lib, PyPortfolioOpt, or skfolio.
- Optional backtesting using a reviewed library only after point-in-time data controls.
- Dataset manifests, corporate-action treatment, fees/slippage/turnover, walk-forward/out-of-sample, benchmark/baseline, solver status, and leakage checks.

Initial phase should prefer calculation adapters over adding a large framework. QuantConnect LEAN, vectorbt, Backtrader, and similar projects require separate compatibility/licensing decisions and should not be embedded by default.

## Dependencies

INV-02, INV-03, INV-05, and appropriate INV-04/INV-06 evidence. High-risk data and financial math review. No quant recommendation without portfolio-fit output.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/quant.py`
- `services/rules-service/app/investments/backtests.py`
- `services/rules-service/app/investments/datasets.py`
- `services/rules-service/tests/test_quant.py`
- `services/rules-service/tests/test_backtests.py`
- `services/rules-service/tests/fixtures/quant_cases_v1.json`
- `docs/adr/ADR-INVESTMENT-002-QUANT-RESEARCH-BOUNDARY.md`

**Modified files proposed:**

- `services/rules-service/requirements.txt` only after an approved dependency decision
- `services/rules-service/app/config.py`
- `services/rules-service/app/market_intelligence/contracts.py`
- `docs/architecture/ATLAS-OPEN-SOURCE-INVESTMENT-STACK.md` if research decision changes

**Schema changes:** Prefer immutable dataset manifests, signal results, and backtest-result references. Persistent backtest artifacts require bounded storage, version/hash, source data manifest, and retention review.

## APIs

- `GET /api/v1/investments/securities/{id}/quant-signals`
- `POST /api/v1/investments/backtests` — research-only, no execution
- `GET /api/v1/investments/backtests/{id}`
- `POST /api/v1/investments/portfolio-optimization/preview` — bounded hypothetical output only

## Tests

Leakage/survivorship/look-ahead, corporate actions, fees/slippage, walk-forward, seeded reproducibility, benchmark comparison, solver infeasibility, malformed data, authorization, bounded runtime, and no-execution AST/route tests.

## Acceptance criteria

- Every backtest includes dataset vintage, manifest, model/code version, assumptions, benchmark, costs, and validation status.
- Invalid or leaky results cannot become evidence for actionable recommendations.
- Optimization output is a preview, never an order or rebalance instruction.
- Dependency license and data terms are approved before installation.

## Rollback strategy

Disable quant generation and leave datasets/results immutable. Remove optional dependency only through a reviewed dependency change; do not delete historical result references.

## Risks/security

Data leakage, optimizer instability, false precision, unbounded compute, malicious data, license/data-term violations, and inadvertent execution semantics.

## Agent tasks

### INV-07-01 — Define dataset manifest and leakage contract

- **Objective:** Make point-in-time quantitative research reproducible and auditable.
- **Inputs:** Market/fundamental observation contracts and ADR-004.
- **Files:** Dataset/backtest contracts, ADR, tests.
- **Implementation requirements:** As-known-at, period, corporate-action, universe, survivorship, costs, seed, code/data hashes, validation status.
- **Tests:** Deliberately leaky and valid fixtures.
- **Acceptance:** Leaky inputs are rejected before calculation.

### INV-07-02 — Add factor/risk calculations

- **Objective:** Produce deterministic factor and risk signals without an AI dependency.
- **Inputs:** Approved point-in-time data manifest.
- **Files:** `quant.py`, tests.
- **Implementation requirements:** Formula/version, finite values, missing data, window, benchmark, source references.
- **Tests:** Golden metrics, reproducibility, insufficient data.
- **Acceptance:** Signal is evidence, not action.

### INV-07-03 — Evaluate portfolio optimization library

- **Objective:** Select a mature optimizer only if it reduces custom code and passes technical/license tests.
- **Inputs:** Open-source stack research, portfolio fixtures, constraints.
- **Files:** Compatibility ADR/plan and isolated test harness; requirements only after approval.
- **Implementation requirements:** Compare Riskfolio-Lib, PyPortfolioOpt, skfolio as applicable; evaluate licenses, solver behavior, constraints, reproducibility, and output validation.
- **Tests:** Synthetic portfolio optimization and infeasible-constraint cases.
- **Acceptance:** Adopt/defer/reject decision documented; no dependency added by the research task.

### INV-07-04 — Add bounded backtest runner

- **Objective:** Run research-only backtests with explicit leakage/cost controls.
- **Inputs:** Validated dataset manifest and factor strategy contract.
- **Files:** `backtests.py`, tests, optional dependency adapter.
- **Implementation requirements:** Bounded runtime/rows, seeded execution, no broker/order interfaces, result status on invalidity.
- **Tests:** Walk-forward, leakage, fees/slippage, benchmark, and timeout tests.
- **Acceptance:** Backtest cannot directly produce a recommendation or execute.

---

# 12. Phase INV-08 — AI Investment Committee

## Objective

Add evidence-grounded specialist analysis and Bull/Bear challenge synthesis through Atlas’s existing orchestrator and agent architecture.

## Scope

- Typed `AgentFinding`, `ResearchFinding`, `RiskAssessment`, `InvestmentThesis`, `RecommendationDraft`, and `Abstention` contracts.
- Existing Investment and Risk agents extended with Fundamental, Technical, Macro, Quant, Portfolio, Bull, Bear, and Chair responsibilities.
- Frozen evidence packet per run.
- Deterministic citation/schema/quality validation.
- Challenge workflow linked to original recommendation/run.
- No direct model write to canonical records.

## Dependencies

INV-01 through INV-03, with INV-04 and selected INV-05–INV-07 evidence. Existing `assistant_orchestrator.py`, `llm_client.py`, agent prompts/personas, recommendation engine, decision journal, ownership and safety controls.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/agent_contracts.py`
- `services/rules-service/app/investments/committee_orchestrator.py`
- `services/rules-service/app/investments/evidence_validator.py`
- `services/rules-service/app/investments/confidence.py`
- `services/rules-service/tests/test_investment_agent_contracts.py`
- `services/rules-service/tests/test_committee_orchestrator.py`
- `services/rules-service/tests/test_evidence_validator.py`
- `services/rules-service/tests/fixtures/committee_cases_v1.json`
- `agents/investment-committee/FUNDAMENTAL.md`
- `agents/investment-committee/TECHNICAL.md`
- `agents/investment-committee/MACRO.md`
- `agents/investment-committee/QUANT.md`
- `agents/investment-committee/PORTFOLIO.md`
- `agents/investment-committee/RISK.md`
- `agents/investment-committee/BULL.md`
- `agents/investment-committee/BEAR.md`
- `agents/investment-committee/CHAIR.md`

**Modified files proposed:**

- `services/rules-service/app/services/assistant_orchestrator.py`
- `services/rules-service/app/services/llm_client.py` only if typed/model metadata support is missing
- existing agent route/service paths
- `services/rules-service/app/forecasts/recommendation_schemas.py` for draft/reference reuse
- `services/rules-service/app/forecasts/recommendations.py` only at the persistence handoff
- `services/rules-service/app/routes/assistant.py` for read-only analysis request/challenge entry
- `services/rules-service/tests/test_routes_assistant.py` and related assistant tests
- `docs/04-ai-agents/AGENT_OVERVIEW.md`
- `docs/04-ai-agents/INVESTMENT_AGENT.md`
- `docs/04-ai-agents/RISK_AGENT.md`

**Schema changes:** Additive run/finding/thesis/challenge records only after contract tests. Recommendation drafts must not be persisted as accepted recommendations until INV-09.

## APIs

- `POST /api/v1/investments/analysis-runs`
- `GET /api/v1/investments/analysis-runs/{id}`
- `POST /api/v1/investments/analysis-runs/{id}/challenge`
- `GET /api/v1/investments/analysis-runs/{id}/findings`

The existing assistant route may be the presentation entry point, but investment analysis should use an explicit typed boundary rather than making natural-language chat the financial authority.

## Tests

Golden evidence packets, schema/citation validation, no invented numbers, claim-classification, conflict preservation, abstention, prompt injection, ownership isolation, model offline/malformed output, bounded retries/tokens, deterministic replay, and no execution capability.

## Acceptance criteria

- Every material claim maps to supplied evidence/calculation references.
- Agents distinguish fact, metric, assumption, interpretation, and uncertainty.
- Risk/Bear can block an unsafe draft; Chair cannot bypass deterministic gates.
- Challenge creates an immutable linked run and never mutates the original.
- Existing assistant remains functional and no trade/order capability is present.

## Rollback strategy

Disable committee generation and retain run/evidence records. Existing assistant and deterministic recommendations continue functioning. Never delete prior findings or rewrite recommendation history.

## Risks/security

Hallucination, prompt injection, cross-user leakage, model overconfidence, unbounded cost, citation laundering, and accidental execution drift.

## Agent tasks

### INV-08-01 — Define typed analyst contracts

- **Objective:** Define strict finding, thesis, risk, draft, abstention, and dissent structures.
- **Inputs:** Committee design and domain evidence model.
- **Files:** `agent_contracts.py`, schemas/tests/fixtures.
- **Implementation requirements:** Claim classes, evidence refs, calculation refs, assumptions, limitations, confidence, role/version, bounded text/collections.
- **Tests:** Extra-field, missing-citation, unsupported-action, privacy, and serialization tests.
- **Acceptance:** A draft with unsupported material claims cannot validate.

### INV-08-02 — Implement evidence validator

- **Objective:** Verify claims cite the frozen packet and deterministic outputs.
- **Inputs:** Evidence packet and typed findings.
- **Files:** `evidence_validator.py`, tests.
- **Implementation requirements:** Hash/version/as-of checks, ownership, freshness, coverage, source conflict handling, no credential leakage.
- **Tests:** Valid, stale, conflicting, unauthorized, and missing-evidence cases.
- **Acceptance:** Validation failure yields a safe rejection/abstention, not a repaired claim.

### INV-08-03 — Add bounded specialist orchestration

- **Objective:** Invoke existing agents in tiered profiles through the existing orchestrator.
- **Inputs:** Validated context/evidence/calculations and local LLM boundary.
- **Files:** `committee_orchestrator.py`, existing assistant integration, agent personas.
- **Implementation requirements:** Read-only tools, frozen packet, bounded calls/retries/tokens, role attribution, trace metadata, no direct persistence.
- **Tests:** Normal, partial, offline, malformed, timeout, and replay cases.
- **Acceptance:** Committee returns typed findings/draft or abstention and never mutates canonical facts.

### INV-08-04 — Implement Bull/Bear challenge pass

- **Objective:** Add adversarial review linked to an immutable original run.
- **Inputs:** Original recommendation/draft, frozen original context, current validated evidence.
- **Files:** Committee orchestration/routes/tests/UI contract documentation.
- **Implementation requirements:** Bear first, Bull response, affected specialist reruns, chair reconsideration, original preservation.
- **Tests:** Reaffirmation, changed action, evidence change, and insufficient-data cases.
- **Acceptance:** “Challenge this recommendation” produces a linked immutable result and user-visible dissent/uncertainty.

---

## Deterministic conviction authority

The LLM never chooses, edits, or reports an authoritative conviction score. It provides grounded findings, evidence references, assumptions, and uncertainty. Atlas computes conviction reproducibly from versioned structured inputs: evidence quality, freshness, completeness, signal agreement, fundamental strength, valuation, technical and macro context, quantitative signals, portfolio fit, risk, and uncertainty.

The implementation owner is the Rules Service calculator proposed at `services/rules-service/app/investments/conviction.py`; its typed result belongs in `app/investments/recommendation_contracts.py` or the existing recommendation schema extension. It records components, weights, caps, blockers, drivers, uncertainty, formula version, and input hashes. Missing evidence, invalid identity/currency, stale required inputs, partial portfolio coverage, or blocking risk/policy results cap or block conviction and are never neutral evidence. The model may explain the server-computed result only. Tests belong in `services/rules-service/tests/test_investment_conviction.py` and recommendation-gate suites. Exact weights and thresholds require the implementation ADR before `INV-09` becomes actionable.

## Objective

Extend Atlas’s existing recommendation engine/lifecycle to support BUY, ADD, HOLD, REDUCE, SELL, and WATCH with deterministic gates and user decisions.

## Scope

- Investment extension of existing `Recommendation` rather than parallel lifecycle.
- Deterministic action semantics and score/confidence calculation.
- Evidence, thesis, portfolio impact, risk, goal impact, assumptions, freshness, and review/expiry references.
- Existing decision journal and outcome linkage.
- User-facing portfolio/security recommendation UI.
- No order submission or execution.

## Dependencies

INV-03 portfolio analytics, INV-04 evidence, INV-08 committee draft, existing recommendation/decision/outcome models/routes, auth/ownership, goal context.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/recommendation_contracts.py`
- `services/rules-service/app/investments/recommendation_gates.py`
- `services/rules-service/tests/test_investment_recommendation_gates.py`
- `services/rules-service/tests/fixtures/investment_recommendations_v1.json`
- `ui/components/investments/InvestmentRecommendationCard.tsx`
- `ui/components/investments/RecommendationEvidence.tsx`
- `ui/components/investments/RecommendationChallenge.tsx`
- `ui/app/investments/recommendations/page.tsx` only if existing recommendations page cannot be extended

**Modified files proposed:**

- `services/rules-service/app/models/recommendation.py`
- `services/rules-service/app/forecasts/recommendation_schemas.py`
- `services/rules-service/app/forecasts/recommendations.py`
- `services/rules-service/app/routes/recommendations_derived.py`
- decision journal/history/outcome paths as needed for typed investment references
- `ui/app/recommendations/page.tsx`
- `ui/lib/api.ts`
- relevant UI tests and E2E specs
- `docs/07-engineering/API_SPECIFICATION.md`

**Schema changes:** Additive investment payload/reference fields or an extension table linked to existing recommendations. Preserve immutable identity, owner/goal linkage, input hash, expected impact, confidence, risks, freshness, provenance, decision, and outcome semantics.

## APIs

Prefer existing `/api/v1/recommendations` lifecycle and add typed investment payloads. Potential additive routes:

- `GET /api/v1/recommendations?kind=investment`
- `GET /api/v1/recommendations/{id}`
- `POST /api/v1/recommendations/{id}/challenge`
- existing decision endpoints for accept/reject/defer

Do not create a second acceptance/decision endpoint unless an ADR proves it necessary.

## Tests

Action semantics, portfolio-state consistency, gates, score/confidence reproducibility, evidence coverage, stale/partial/currency failure, ownership isolation, idempotency, supersession, decision lifecycle, outcomes, UI evidence disclosure, challenge flow, no execution/tool access, and route-mocked browser tests.

## Acceptance criteria

- BUY/ADD/REDUCE/SELL require passed deterministic suitability/policy/data gates.
- HOLD/WATCH include review/trigger semantics and uncertainty.
- Every recommendation has portfolio snapshot, evidence, calculation, thesis, risk, and provenance references.
- User decisions are separate immutable records.
- No API, model, or UI path can place or imply an order.

## Rollback strategy

Feature-gate investment recommendation presentation/generation. Existing non-investment recommendations remain unchanged. Preserve any generated investment records and decisions; stop new generation without deleting history.

## Risks/security

Financial harm from overconfident recommendations, stale data, incomplete portfolio, false tax claims, unauthorized cross-user reads, and action semantics drifting into execution.

## Agent tasks

### INV-09-01 — Define investment recommendation extension

- **Objective:** Map investment payload fields onto existing recommendation lifecycle.
- **Inputs:** Domain semantics, existing models/schemas/routes.
- **Files:** Recommendation contract/schema/model docs/tests.
- **Implementation requirements:** One lifecycle, immutable identity, action enum, subject scope, portfolio/evidence/calculation refs, review/expiry, no order fields.
- **Tests:** Schema, immutability, idempotency, and backward-compatibility tests.
- **Acceptance:** Existing recommendation consumers continue working; investment payload is additive and typed.

### INV-09-02 — Implement deterministic recommendation gates and scoring

- **Objective:** Validate committee drafts and compute score/confidence outside the model.
- **Inputs:** Portfolio impact, evidence coverage, risk assessment, goals, policy, thesis draft.
- **Files:** `recommendation_gates.py`, existing recommendation engine/service, tests/fixtures.
- **Implementation requirements:** Fail closed on identity/currency/freshness/coverage/risk/policy; version weights/formulas; preserve dissent.
- **Tests:** Each action and each blocker; replay and boundary tests.
- **Acceptance:** No unsupported draft becomes actionable; WATCH/abstention explains why.

### INV-09-03 — Persist through existing lifecycle

- **Objective:** Create immutable investment recommendations and reuse decision/outcome services.
- **Inputs:** Validated draft and gate result.
- **Files:** Existing recommendation model/service/routes/migration/tests.
- **Implementation requirements:** Owner-before-existence, idempotency, supersession, provenance, decision linkage, no direct AI persistence.
- **Tests:** Migration, ownership, race/idempotency, lifecycle, and outcome linkage.
- **Acceptance:** Recommendation → user decision is complete and no execution path exists.

### INV-09-04 — Add recommendation evidence/challenge UI

- **Objective:** Present thesis, evidence, risks, uncertainty, dissent, and challenge affordance.
- **Inputs:** Typed API contract and existing recommendations UI/design system.
- **Files:** Existing recommendation page/components/API/tests; new components only if necessary.
- **Implementation requirements:** Accessible, responsive, clear action semantics, stale/partial states, no “buy now” execution language.
- **Tests:** Vitest, typecheck, route-mocked Playwright, axe, ownership/error states.
- **Acceptance:** User can inspect and challenge, then separately accept/reject/defer; no trade action is rendered.

---

# 14. Phase INV-10 — Daily/weekly/monthly CIO reports

## Objective

Generate evidence-backed periodic portfolio/intelligence reports using immutable snapshots and recommendations, without silently activating external delivery or background execution.

## Scope

- Daily, weekly, monthly report templates and period/as-of semantics.
- Portfolio changes, market/fundamental/macro context, recommendation changes, risks, watchlist, catalysts, and open challenges.
- Existing Market Brief archive/delivery patterns reused.
- Local preview first; scheduling/email remain separately gated and default-off.

## Dependencies

INV-09 recommendations, INV-03 portfolio snapshots, INV-04–INV-07 evidence as available, existing Market Brief models/routes/UI/delivery flags.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/cio_reports.py`
- `services/rules-service/tests/test_cio_reports.py`
- `services/rules-service/tests/fixtures/cio_reports_v1.json`
- `ui/components/investments/CioReportView.tsx` only if existing Market Brief components cannot be extended

**Modified files proposed:**

- `services/rules-service/app/market_intelligence/briefing.py`
- existing market brief models/routes/delivery adapters
- `ui/app/market-briefs/page.tsx`
- relevant API/UI tests
- docs API/operational runbooks

**Schema changes:** Prefer a report subtype/reference on existing immutable Market Brief records. Any new table must be additive, versioned, source-linked, and retention-reviewed.

## APIs

- `GET /api/v1/investments/cio-reports`
- `GET /api/v1/investments/cio-reports/{id}`
- `POST /api/v1/investments/cio-reports/preview` — local/explicit generation only

Reuse existing archive/delivery controls. No default scheduler activation.

## Tests

Period boundaries, source/evidence coverage, stale/partial portfolio, recommendation supersession, deterministic report composition, idempotency, privacy, delivery-off defaults, UI archive/detail, accessibility, and no-network tests.

## Acceptance criteria

- Reports state as-of/freshness/coverage and omit unsupported claims.
- Same frozen inputs produce the same report identity/content.
- Existing Market Brief functionality is preserved.
- Email/scheduling remains default-off and cannot execute trades.

## Rollback strategy

Disable report generation/presentation while retaining prior Market Briefs and recommendations. Do not delete immutable reports.

## Risks/security

Periodic stale data, report leakage, accidental external delivery, and confusing narrative summaries with current canonical state.

## Agent task

### INV-10-01 — Extend Market Brief into CIO report profiles

- **Objective:** Reuse existing briefing archive and delivery boundaries for investment reports.
- **Inputs:** Recommendation/evidence/portfolio contracts and Market Brief infrastructure.
- **Files:** `cio_reports.py`, existing briefing paths, tests/UI docs.
- **Implementation requirements:** Daily/weekly/monthly period semantics, evidence references, omissions, idempotency, default-off delivery.
- **Tests:** Period, privacy, delivery, and UI regression suite.
- **Acceptance:** A report is an immutable evidence-backed view, not an execution instruction.

---

# 15. Phase INV-11 — Recommendation tracking

## Objective

Track recommendation lifecycle, user decisions, review triggers, supersession, and measurable outcomes using existing append-only infrastructure.

## Scope

- Recommendation status/review/expiry/supersession.
- Challenge/reconsideration linkage.
- User accept/reject/defer and rationale through existing decision journal.
- Outcome evaluation against stated horizon/expectation, with no hindsight rewrite.
- Calibration inputs and correction feedback.

## Dependencies

INV-09 and existing recommendation/decision-history/outcome services from phases 2–4.

## Exact repository paths

**New files proposed:**

- `services/rules-service/app/investments/recommendation_tracking.py`
- `services/rules-service/tests/test_investment_tracking.py`
- `ui/components/investments/RecommendationTimeline.tsx`

**Modified files proposed:**

- `services/rules-service/app/forecasts/decision_journal_service.py`
- existing decision history/outcome routes/models
- `ui/app/recommendations/page.tsx`
- `ui/app/activity/page.tsx` if investment events belong in the existing activity view
- relevant tests/docs

**Schema changes:** Additive investment linkage/reference fields on existing append-only decision/outcome records, or a separately justified extension table. No mutable rewrite of historical recommendations.

## APIs

Prefer existing decision and outcome APIs. Add only typed investment filters/links:

- `GET /api/v1/recommendations/{id}/timeline`
- `GET /api/v1/recommendations/{id}/outcomes`
- existing decision endpoints for user action

## Tests

Status transitions, review/expiry, supersession, challenge linkage, accepted/rejected/deferred decisions, outcome windows, ownership isolation, idempotent replay, and no causal overclaiming.

## Acceptance criteria

- Historical recommendation displays what was known then.
- User decision and outcome are separate records.
- Outcome measurement uses the declared horizon and assumptions.
- Calibration data does not mutate source history.

## Rollback strategy

Disable tracking UI/filtering while preserving existing journal/outcome records and APIs.

## Risks/security

Outcome leakage across owners, hindsight bias, immutable-history violations, and treating user acceptance as execution.

## Agent task

### INV-11-01 — Extend existing decision/outcome timeline for investments

- **Objective:** Link investment recommendation, challenge, decision, and outcome records.
- **Inputs:** Existing decision-history/outcome contracts and INV-09 recommendation identity.
- **Files:** Existing services/routes/models/tests plus tracking projection/UI.
- **Implementation requirements:** Append-only, owner-scoped, hash-linked, stated horizon, pending outcomes, no execution status.
- **Tests:** Lifecycle and privacy/authorization suite.
- **Acceptance:** User can see and decide on a recommendation without Atlas claiming a trade or result that did not occur.

---

# 16. Phase INV-12 — Backtesting/evaluation

## Objective

Measure deterministic analytics, agent grounding, committee quality, confidence calibration, and recommendation outcomes without turning historical results into guarantees.

## Scope

- Golden fixtures and historical replay with as-known-at data.
- Deterministic calculation regression and property tests.
- Agent/committee evaluation: citation fidelity, no invented facts, abstention, risk coverage, challenge effectiveness, calibration.
- Recommendation evaluation by action/horizon, false positives/negatives, and user comprehension.
- Quant backtest integrity and outcome measurement.

## Dependencies

INV-03 through INV-11; approved datasets and evaluation labels; no production execution.

## Exact repository paths

**New files proposed:**

- `services/rules-service/tests/investment_evaluations/`
- `services/rules-service/tests/fixtures/investment_replay_cases_v1.json`
- `services/rules-service/app/investments/evaluation.py`
- `docs/07-engineering/INVESTMENT_EVALUATION_PROTOCOL.md`
- `docs/adr/ADR-INVESTMENT-003-EVALUATION-AND-CALIBRATION.md`
- `ui/app/investments/evaluations/page.tsx` only if an internal personal-use view is needed

**Modified files proposed:**

- existing recommendation/outcome test suites
- `docs/08-security/AI_SAFETY_AND_MODEL_RISK.md`
- `docs/07-engineering/DEVELOPMENT_GUIDELINES.md`

**Schema changes:** Prefer test/evaluation artifacts outside production tables. Persist only bounded calibration metadata if justified and retention-reviewed.

## APIs

Internal/read-only evaluation interfaces only if needed:

- `POST /api/v1/investments/evaluations/replay`
- `GET /api/v1/investments/evaluations/{id}`

No public execution or trading API.

## Tests

Replay determinism, point-in-time correctness, leakage/survivorship, citation and privacy evaluations, calibration, abstention, challenge, action semantics, full focused regression, and bounded runtime/resource tests.

## Acceptance criteria

- Evaluation distinguishes analysis quality from realized market performance.
- Historical runs use only information available at the decision time.
- Confidence calibration and user corrections are versioned.
- Failed evaluation gates block rollout of affected capabilities.

## Rollback strategy

Disable evaluation jobs/views without modifying production recommendation history. Preserve artifacts according to approved retention policy.

## Risks/security

Data leakage, evaluation contamination, sensitive portfolio exposure, misleading performance claims, and unbounded replay cost.

## Agent tasks

### INV-12-01 — Establish deterministic replay suite

- **Objective:** Prove canonical calculations and recommendation gates are reproducible.
- **Inputs:** Immutable snapshots/evidence/recommendations and fixture protocol.
- **Files:** Evaluation fixtures/tests and protocol doc.
- **Implementation requirements:** Exact as-known-at inputs, hashes, versions, no future data, expected abstentions.
- **Tests:** Replay and mutation/supersession tests.
- **Acceptance:** Same inputs reproduce same result; changed inputs create a new result.

### INV-12-02 — Establish committee grounding evaluation

- **Objective:** Measure analyst/chair behavior against golden evidence packets.
- **Inputs:** Committee contracts and model/provider test harness.
- **Files:** Evaluation suite, fixtures, AI safety docs.
- **Implementation requirements:** Citation fidelity, fact grounding, no numbers invented, risk/bear coverage, prompt-injection resistance, confidence calibration.
- **Tests:** Golden, adversarial, malformed, and privacy cases.
- **Acceptance:** No committee rollout without passing evidence-grounding thresholds.

### INV-12-03 — Establish outcome/calibration reporting

- **Objective:** Compare stated expectations with later measured outcomes without rewriting history.
- **Inputs:** Existing outcomes and recommendation horizons.
- **Files:** Evaluation service/docs/tests.
- **Implementation requirements:** Pending windows, accepted/rejected/deferred distinction, no causal claims, versioned calibration outputs.
- **Tests:** Window, missing outcome, and selection-bias cases.
- **Acceptance:** Reports state limitations and never imply that an unaccepted recommendation was followed.

---

# 17. Cross-phase API and schema rules

## API rules

- All investment APIs are authenticated and owner/account scoped.
- Ownership is checked before existence-sensitive disclosure.
- Read responses include schema version, as-of, freshness, coverage, currency, and provenance references.
- Generation requests cannot supply authoritative portfolio values, prices, evidence, or recommendation identity.
- Material writes require idempotency keys and append-only semantics.
- Errors distinguish authorization, validation, stale/unavailable data, policy rejection, and provider failure without leaking sensitive details.
- No route accepts broker credentials, broker destinations, order types, execution requests, transfers, or money movement.
- Large evidence and raw provider payloads are bounded or referenced by opaque hashes.

## Schema rules

- Prefer additive migrations and compatibility projections.
- Preserve source records and historical versions.
- Use exact numeric types for authoritative money; any legacy Float boundary is explicit and tested.
- Store period and as-known-at/vintage separately.
- Include source/provider/library/model/calculation/policy versions.
- Use canonical hashes for immutable replay and idempotency.
- Downgrades are row-count guarded and tested on disposable SQLite; PostgreSQL parity is required for relevant behavior.

## Test rules

Every high-risk phase requires focused contract, numeric, ownership, privacy, migration, and failure tests. UI-only route-mocked tests do not replace genuine backend integration tests. External providers are synthetic/default-off in tests. Full repository validation is selected according to the canonical policy and scope; it is not automatically required for every documentation or isolated contract change.

## 18. Dependency adoption policy

Initial implementation should use the existing Atlas code and provider-neutral contracts. Open-source projects are optional bounded dependencies, not architecture owners.

**Potentially adopt after compatibility/license spikes:**

- EdgarTools or direct SEC/XBRL libraries for filing/fact normalization.
- A single portfolio optimizer such as Riskfolio-Lib, PyPortfolioOpt, or skfolio, only if it materially reduces custom code and its license/data/solver behavior is approved.
- QuantLib only for bounded financial mathematics not already safely covered by Atlas.
- Existing numerical Python stack already present in the selected environment.

**Defer initially:** OpenBB, FinceptTerminal, FinRobot, full terminal platforms, large agent frameworks, vector databases, general backtesting platforms, broker integrations, and autonomous execution systems. They add scope, licensing/data dependencies, or duplicate Atlas boundaries before the canonical model is proven.

Every dependency task must document GitHub/source URL, license, version, maintenance, API fit, data terms, security posture, installation impact, fallback, and removal strategy. Do not install a library based only on popularity or stars.

## 19. Roadmap/status handling

This plan does not update `docs/10-roadmap/PROJECT_STATUS.json` or generated `PROJECT_STATUS.md` because the current canonical status explicitly says phase-6 is complete, active work is empty, and the next bounded task is local release-candidate operations—not Phase 7. Beginning Investment Intelligence requires explicit program authorization and a status update at start time; this plan does not itself authorize the program.

When authorized later, status should be updated once for the material start, each approved phase milestone, blockers/significant risks, and completion. Do not record this planning document as implementation completion, and do not create tracker evidence for unstarted phases.

## 20. Explicit non-goals

This plan does **not** authorize:

- automatic trading or brokerage order execution;
- broker integrations or broker credentials;
- transfers, withdrawals, deposits, settlement, or money movement;
- leverage, margin, options execution, shorting, or derivatives execution;
- autonomous rebalancing;
- regulated-advice claims or guaranteed returns;
- multi-user/household/advisor tenancy expansion;
- deletion/retention policy invention;
- replacement of the canonical financial core with an LLM or external platform;
- direct model writes to financial facts, holdings, portfolio snapshots, recommendations, decisions, or outcomes;
- a second recommendation lifecycle;
- blind adoption of FinceptTerminal, OpenBB, FinRobot, LangGraph, PydanticAI, Qdrant, Weaviate, OpenSearch, vectorbt, Backtrader, LEAN, or any other project without a current compatibility/license decision;
- a production scheduler or email delivery activation without separate safety review;
- treating sentiment, analyst consensus, technical signals, or backtests as sufficient evidence by themselves.

## 21. Final implementation recommendation

**Proceed After X:** proceed only after explicit authorization of the Investment Intelligence program, a canonical investment authority ADR, and completion of the INV-01 foundation gate. Then implement INV-02 and INV-03 before any AI committee or actionable recommendation work.

The minimum safe vertical slice is:

```text
INV-01 contracts/authority
  → INV-02 security + market observations
  → INV-03 immutable portfolio snapshot + deterministic impact
  → limited INV-04 evidence
  → INV-08 Portfolio/Risk + Fundamental + Bear/Bull typed analysis
  → INV-09 existing recommendation lifecycle
  → user decision
```

No phase is complete until its acceptance criteria, focused tests, rollback path, provenance, ownership, and no-execution checks pass without regressing existing Atlas functionality.

# Atlas Investment Intelligence — Repository Architecture Audit

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Audit date:** 2026-08-30  
**Scope:** Read-only architecture audit; no implementation, schema, dependency, API, or configuration changes were made.

> **Evidence standard.** This audit distinguishes repository-verified implementation from documentation intent. A documented capability is not treated as implemented unless corresponding code, persistence, route, or tests were found.

## 1. Executive summary

### Investment Data Authority Invariants

```text
Current Holding ≠ Historical Investment Truth
Unknown ≠ Zero
Missing ≠ No Change
Stale ≠ Current
Estimated ≠ Observed
LLM Claim ≠ Financial Fact
```

These invariants govern all Investment Intelligence work. External/open-source projects remain bounded adapters, data sources, analytical engines, or research tools; Atlas remains the canonical financial model, portfolio state, provenance, recommendation authority, and decision record.

Atlas is a working personal, single-user, pre-production financial application with a Next.js frontend, two separate FastAPI services, SQLAlchemy/Alembic persistence, server-owned deterministic financial calculations, authenticated routes, immutable forecast/recommendation/decision-history substrates, and a substantial Market Intelligence foundation. The repository already contains a viable extension seam for Investment Intelligence; a parallel investment platform should not be created.

The strongest existing foundation is:

- `services/rules-service/app/models/holding.py` and `app/routes/holdings.py` for imported/manual portfolio positions.
- `services/rules-service/app/market_intelligence/` for provider-neutral contracts, Finnhub/SEC adapters, rate limiting, bounded caching, provenance, freshness, normalized failures, and deterministic briefing composition.
- `services/rules-service/app/forecasts/` for immutable, server-owned recommendations, decision journal linkage, outcome evaluation, and deterministic identity/idempotency.
- `services/finlynq/app/projection_state/` plus `rules-service/app/forecast_provider/` for trusted canonical projection-state exchange.
- Existing goal, forecast, scenario, recommendation, decision-history, and UI surfaces.

The portfolio model is not yet investment-grade. It is an import/manual-entry position snapshot model, not a canonical security master or immutable transaction/lot ledger. `Holding` uses SQLAlchemy `Float` for quantity, price, value, and cost basis; holdings are replaced on account re-import; there are no verified `Security`, `Lot`, `PositionSnapshot`, dividend, split, tax-lot, transaction-to-position, or valuation-history models; and live-price refresh returns enriched response data without persisting a valuation event. Portfolio performance, allocation, factor exposure, tax-lot analysis, risk modeling, and true portfolio-fit calculations are not implemented as a coherent backend domain.

The recommendation substrate is materially ahead of the portfolio substrate: it is immutable, owner-scoped, evidence-linked, idempotent, and user-controlled, but current recommendation derivation is largely goal/financial-state oriented and the Market Brief deterministic templates are explicitly review-oriented rather than BUY/ADD/HOLD/REDUCE/SELL security recommendations. The existing `/api/analyst-ratings` route and UI provide sell-side consensus and price targets, but these are not an Atlas suitability decision engine.

### Recommendation

**Proceed After X** — proceed with a bounded architecture/design phase and data-quality remediation, but do not implement security recommendations yet. First resolve the investment-domain authority gaps: establish a canonical security/holding/transaction/valuation model, exact numeric policy, historical immutability, source provenance, corporate-action handling, portfolio performance definitions, suitability/risk-profile contracts, and a recommendation-specific evidence and calibration contract. Keep all providers, AI calls, and execution disabled by default while those foundations are established.

## 2. Current architecture

### 2.1 Frontend

The frontend is a Next.js/React application under `ui/` with client-side pages and reusable components. Verified investment/intelligence surfaces include:

- `ui/app/portfolio/page.tsx` — portfolio page; loads dashboard summary, accounts, holdings, and profile; imports Fidelity CSV/Robinhood PDF through the API; supports manual add, edit, delete, price refresh, auto-refresh preference, concentration display, and analyst-coverage batch UI.
- `ui/app/recommendations/page.tsx` — recommendation page; currently contains static personalized recommendation cards plus an analyst-ratings lookup section.
- `ui/app/market-intelligence/page.tsx` and `ui/app/market-briefs/page.tsx` — Market Intelligence/brief archive surfaces.
- `ui/app/decisions/page.tsx`, `ui/app/goals/page.tsx`, `ui/app/scenario-lab/page.tsx` — decision, goal, and scenario workflows.
- `ui/app/assistant/page.tsx`, `ui/components/assistant/`, and `ui/components/copilot/` — assistant/Copilot experience.
- `ui/components/portfolio/AnalystCoverageStatus.tsx` — analyst coverage state component.
- `ui/components/universe/FinancialUniverse.tsx` — financial-universe UI surface; repository inspection confirms the route/component exists, but not a complete investment-universe backend.
- `ui/lib/api.ts` — typed HTTP client and resource interfaces.
- `ui/lib/errors.ts`, `ui/lib/format.ts`, `ui/lib/dataRefresh.ts`, and related preference/context modules — client support infrastructure.

The frontend generally consumes server results. However, the portfolio page derives display aggregates such as grand total, concentration percentages, top movers, and account grouping in the browser. These are acceptable presentation calculations only if clearly treated as display values; they must not become authoritative financial values.

### 2.2 Backend and services

#### Rules Service

`services/rules-service/app/` is the primary API and financial-intelligence service:

- `main.py` wires FastAPI routers and application startup.
- `auth.py` implements JWT/local-user authentication dependencies.
- `config.py` owns settings and feature/provider flags.
- `database.py` owns SQLAlchemy engine/session setup.
- `models/` contains SQLAlchemy persistence models.
- `routes/` exposes authenticated APIs.
- `calculations/projection.py` contains deterministic projection logic.
- `forecasts/` contains canonical state, mapper, generation service, immutable forecast repository, recommendation engine/repository, decision journal, decision history, outcome evaluation, codecs, observability, and schemas.
- `market_intelligence/` contains normalized research contracts, provider adapters, provider controls, deterministic briefing, composition, persistence/delivery support, and CLI/operational wiring.
- `services/` contains assistant orchestration, LLM client, import/OCR/categorization/query utilities.

Relevant routers include `routes/holdings.py`, `routes/analyst_ratings.py`, `routes/market_briefs.py`, `routes/recommendations.py`, `routes/recommendations_derived.py`, `routes/decision_history.py`, `routes/forecasts_generation.py`, `routes/scenarios.py`, `routes/assistant.py`, `routes/accounts.py`, `routes/transactions.py`, `routes/goals.py`, `routes/dashboard.py`, and `routes/plaid.py`.

#### Finlynq

`services/finlynq/app/` is a separate FastAPI service and canonical source/projection provider for the existing financial state boundary. It contains account, transaction, goal, category, balance-evidence, currency-evidence, import, OCR, categorization, and `projection_state/` modules. Rules Service calls it through `app/forecast_provider/finlynq.py` for trusted forecast generation and related canonical projection state.

The two services intentionally use separate Python environments and manifests. The repository also contains a shared SQLite Compose wiring in `docker-compose.yml`, with Finlynq health dependency and Rules Service forwarding behavior.

### 2.3 Database and persistence

- SQLAlchemy models: `services/rules-service/app/models/` and `services/finlynq/app/models/`.
- Alembic migrations: `services/rules-service/alembic/versions/`.
- The repository uses SQLite locally and documents PostgreSQL considerations.
- Existing immutable/versioned persistence includes forecasts, recommendations, outcome evaluations, decision journal entries, decision history/audit events, market briefs, and scenario history.
- Existing portfolio persistence is `accounts` + `holdings` + `import_batches`; the holding model is not append-only.
- `docs/07-engineering/DATABASE_SCHEMA.md` describes a broader target model including securities, assets, policies, approvals, executions, and audit events, but the audit found no corresponding complete investment implementation for those target entities.

### 2.4 Canonical financial model

The currently implemented canonical financial authority is strongest for account-level projection state:

1. Finlynq owns source financial records and approved balance/currency evidence.
2. `services/finlynq/app/projection_state/provider.py` builds a bounded `atlas-projection-state/v1` representation.
3. `services/rules-service/app/forecast_provider/finlynq.py` is the sanctioned adapter.
4. `services/rules-service/app/forecasts/canonical_state.py`, `mappers.py`, and `service.py` validate and generate immutable forecasts.
5. Decimal-safe, USD/freshness/currency gates and hash-bound versions prevent arbitrary client values from becoming forecast authority.

This canonical boundary does **not** yet provide equivalent authority for investment positions. Holdings are currently read from Rules Service SQLAlchemy tables and are not integrated into a transaction/lot/valuation canonical ledger.

### 2.5 Existing intelligence and recommendation layers

- Deterministic calculations: `app/calculations/projection.py`, `app/scenarios/engine.py`, and `app/market_intelligence/briefing.py`.
- Forecasting: `app/forecasts/` and Finlynq projection-state adapter.
- Recommendations: `app/forecasts/recommendation_engine.py`, `recommendations.py`, `recommendation_repository.py`, schemas, and derived routes.
- Decision journal/outcomes: `decision_journal_service.py`, `decision_history_service.py`, `outcome_evaluation_service.py`, and corresponding models/routes/migrations.
- Market research: `app/market_intelligence/contracts.py`, `adapters.py`, `controls.py`, `composition.py`, `briefing.py`, `pulse.py`, repositories, and routes.
- Analyst data: `routes/analyst_ratings.py` provides Finnhub analyst recommendation trends and price targets; `market_intelligence/adapters.py` also normalizes analyst recommendations and targets for the newer research foundation.
- AI assistant: `app/services/assistant_orchestrator.py`, `app/services/llm_client.py`, `routes/assistant.py`, and frontend assistant/Copilot components.

The repository has the architectural rule that deterministic systems calculate and validate, models propose reasoning, policies authorize, and the user remains in control. That rule should be preserved for Investment Intelligence.

### 2.6 Agent framework

The repository contains agent architecture documentation and UI/orchestration support, including:

- `docs/04-ai-agents/AGENT_OVERVIEW.md`
- `docs/04-ai-agents/INVESTMENT_AGENT.md`
- `docs/04-ai-agents/WEALTH_AGENT.md`
- `docs/04-ai-agents/RISK_AGENT.md`
- `docs/04-ai-agents/TAX_AGENT.md`
- `docs/04-ai-agents/OPPORTUNITY_AGENT.md`
- `docs/04-ai-agents/LIFE_AGENT.md`
- `docs/04-ai-agents/AGENT_OVERVIEW.md`
- `docs/02-architecture/ATLAS_AGENT_ARCHITECTURE.md`
- `services/rules-service/app/services/assistant_orchestrator.py`
- `services/rules-service/app/services/llm_client.py`
- `ui/components/assistant/` and `ui/components/copilot/`

The audit did not find a separate production multi-agent runtime with independently deployed specialist workers, tool-permission manifests, model gateway abstraction, agent evaluation harness, or durable agent run ledger. The documented specialist architecture is a valid extension point, not evidence that all specialists are implemented.

### 2.7 Authentication, authorization, configuration, and CI

- Authentication is implemented through `app/auth.py`, JWT settings, and `require_user` dependencies.
- Routes generally resolve the local user and filter resources by owner. Several immutable recommendation/decision/history migrations include database-level owner-consistency triggers.
- Configuration is in `app/config.py`, service `.env.example` files, root `.env.example`, and Compose environment wiring.
- Market Intelligence providers and generation are feature-gated/default-off in checked-in configuration. The current handoff records a safety risk because ignored local configuration has provider/generation flags and credentials present; no provider call was made during this audit.
- `.github/workflows/test.yml` and `.github/workflows/project-governance.yml` exist historically, but repository policy states GitHub Actions is intentionally disabled as a completion gate. Local validation is authoritative.
- Tests exist across Rules Service, Finlynq, root cross-service tests, UI Vitest, and Playwright. Relevant inventory is listed below.

## 3. Existing investment functionality

### 3.1 Holdings and portfolio import

**Path:** `services/rules-service/app/models/holding.py`  
**Purpose:** One row per imported/manual position in an account. Fields include `account_id`, `symbol`, `description`, `quantity`, `last_price`, `current_value`, `cost_basis_total`, `type`, and timestamps.  
**Public interface:** SQLAlchemy model; consumed by holdings routes, market-intelligence composition, and tests.  
**Dependencies:** SQLAlchemy `Base`, `Account`, optional `ImportBatch`.  
**Maturity:** Early-to-mid feature maturity as a portfolio snapshot/import feature; not a canonical investment ledger.  
**Tests:** `services/rules-service/tests/test_routes_holdings.py` and related route/test fixtures.  
**Reuse:** **Yes, as an input compatibility layer; not as the final canonical investment model.**

Important verified limitations:

- Monetary and quantity columns are SQLAlchemy `Float`.
- No security foreign key; `symbol` is free text and may be null.
- No currency per holding; account currency is separate and can be unknown.
- No lot identity, acquisition date, realized/unrealized split, transaction linkage, corporate actions, or valuation observation history.
- Re-import deletes all existing holdings for an account before inserting the new snapshot.
- Manual edit/delete are hard mutable operations.
- `current_balance` on `Account` is recomputed from the current holding rows.

**Path:** `services/rules-service/app/routes/holdings.py`  
**Interfaces:**

- `POST /api/holdings/import` — Fidelity positions CSV or Robinhood holdings PDF.
- `GET /api/holdings/` — current-user holdings.
- `POST /api/holdings/refresh-prices` — live quote enrichment through Finnhub.
- `POST /api/holdings/` — manual holding creation.
- `PUT /api/holdings/{holding_id}` — partial mutable update.
- `DELETE /api/holdings/{holding_id}` — hard delete.

**Dependencies:** FastAPI, `pdfplumber`, Python CSV parsing, SQLAlchemy, Finnhub HTTP calls, `Account`, `Holding`, `ImportBatch`, auth and schemas.  
**Maturity:** Functional ingestion/UI feature with extensive parser regression coverage.  
**Reuse:** **Reuse the route boundary only as a migration-compatible façade; move authoritative writes behind an investment ingestion/application service.**

### 3.2 Securities/instruments

No complete implemented `Security`/instrument master model was verified in `services/rules-service/app/models/`. Symbols are stored directly on `Holding` and normalized in Market Intelligence contracts with a bounded grammar. Finnhub company profile can resolve a bounded profile and CIK, but that is provider-derived research metadata, not a persistent Atlas security master.

**Classification:** **NEW**, with migration adapters from holding symbols. Do not treat a ticker string as a security identity.

### 3.3 Analyst ratings

**Paths:** `services/rules-service/app/routes/analyst_ratings.py`; `services/rules-service/tests/test_routes_analyst_ratings.py`; `test_routes_analyst_ratings_batch.py`; frontend portions of `ui/app/recommendations/page.tsx` and `ui/app/portfolio/page.tsx`.  
**Purpose:** Fetch and display Finnhub sell-side recommendation trends and price targets, with cache/batch behavior.  
**Public interfaces:** GET ticker ratings and POST batch ratings under `/api/analyst-ratings`.  
**Dependencies:** Finnhub, `httpx`, `cachetools`, auth, frontend API client.  
**Maturity:** Working bounded external-data feature.  
**Reuse:** **REUSE as one evidence source only.** It must never be equated with Atlas’s personalized BUY/SELL decision.

### 3.4 Market Intelligence research foundation

**Paths:** `services/rules-service/app/market_intelligence/contracts.py`, `adapters.py`, `controls.py`, `composition.py`, `briefing.py`, `pulse.py`, `market_calendar.py`, `fakes.py`, repositories, routes, and tests.  
**Purpose:** Provider-neutral normalized market evidence and deterministic Market Brief generation.  
**Public interfaces:** Pydantic contracts such as `PortfolioHolding`, `PortfolioUniverse`, `MarketQuoteSnapshot`, `CompanyProfile`, `CompanyNewsItem`, `EarningsEvent`, `EarningsResult`, `AnalystRecommendation`, `PriceTarget`, `DividendEvent`, `SecFilingEvent`, `HoldingEvidence`, `CoverageSummary`, `ProviderResult`, and normalized failures.  
**Dependencies:** Finnhub and SEC adapters, `httpx`, SQLAlchemy repositories, standard library, synthetic transports.  
**Maturity:** Strong foundation; provider calls are guarded and testable, but the output is a research brief rather than an investment recommendation.  
**Tests:** `test_market_intelligence_foundation.py`, `test_market_briefing.py`, `test_market_brief_coverage.py`, `test_market_pulse.py`, `test_market_brief_generation_reliability.py`, `test_market_brief_operational_wiring.py`, `test_market_delivery.py`, and related suites.  
**Reuse:** **REUSE heavily.** Extend contracts and composition rather than creating another provider layer.

Verified strengths include:

- Strict Pydantic models with `extra="forbid"` and frozen contracts.
- Bounded symbols, text, collections, and source URLs.
- Credential-free source URL validation.
- Decimal strings for market prices/targets.
- Provider result exactly-one-outcome semantics.
- Rate pacing, bounded cache, retry limits, usage ledger, synthetic transport, and normalized failure classes.
- Freshness and market-session-aware quote basis.
- Per-holding coverage omissions and truthful partial coverage.
- Hashable portfolio/universe inputs and source metadata.
- SEC CIK/form normalization and identifying User-Agent validation.

### 3.5 Existing recommendation engine

**Paths:** `services/rules-service/app/forecasts/recommendation_engine.py`, `recommendations.py`, `recommendation_repository.py`, `recommendation_schemas.py`, `routes/recommendations.py`, `routes/recommendations_derived.py`, models `recommendation.py` and `recommendation_log.py`.  
**Purpose:** Deterministic derivation/persistence of owner-scoped recommendations and linkage to goals/evidence/decisions.  
**Maturity:** Strong persistence and governance substrate; investment-specific semantics incomplete.  
**Tests:** `test_recommendation_engine.py`, `test_recommendation_repository.py`, `test_recommendation_schemas.py`, `test_routes_recommendations_derived.py`, decision/history/outcome suites.  
**Reuse:** **REUSE and EXTEND.** Add an investment recommendation kind and schema version only after the investment evidence and suitability contracts exist.

The current substrate supports immutable identities, strict schemas, goal links, evidence references/hashes, risks, confidence, approvals/decisions, idempotency, and outcomes. It does not by itself prove that a security action is suitable, tax-aware, quantitatively valid, or based on complete portfolio data.

### 3.6 Performance, allocation, risk, and cost basis

The repository contains UI-level aggregation and documentation of intended portfolio dimensions, but no verified coherent backend domain service for:

- Time-weighted return or money-weighted return.
- Realized/unrealized gain/loss by lot.
- Dividend/cash-flow-adjusted return.
- Benchmark-relative performance.
- Historical allocation snapshots.
- Sector/geography/factor exposure from a canonical security master.
- Tax-lot selection or tax-aware rebalance impact.
- Volatility, drawdown, beta, tracking error, VaR/CVaR, or stress testing.
- Portfolio-level covariance or factor model.
- Rebalance optimizer.
- Security suitability/policy constraints.

`Holding.cost_basis_total` exists as an imported field and is displayed/returned, but it is not a transaction-backed cost-basis ledger.

### 3.7 Forecasting, goals, simulation, wealth

**Paths:** `services/rules-service/app/forecasts/`, `app/scenarios/`, `app/calculations/projection.py`, `app/models/goal.py`, `app/models/forecast.py`, `app/models/scenario.py`, Finlynq projection state, and `ui/components/simulation/`.  
**Purpose:** Goal-linked financial projection and bounded what-if scenarios.  
**Maturity:** Implemented for current financial projection and Scenario Lab; investment-specific stochastic modeling is not complete.  
**Tests:** Forecast, scenario, canonical-state, migration, and UI simulation suites.  
**Reuse:** **REUSE for goal/wealth context; EXTEND only through explicit investment projection inputs.**

The roadmap records Monte Carlo probability modeling as intentionally deferred. Investment Intelligence must not imply probability-calibrated portfolio forecasts until that gap is addressed.

### 3.8 Decision journal and outcome learning

**Paths:** `app/models/decision_journal_entry.py`, `decision_history.py`, `outcome_evaluation.py`, `app/forecasts/decision_journal_service.py`, `decision_history_service.py`, `outcome_evaluation_service.py`, associated routes and migrations.  
**Purpose:** Append-only decision and audit history, evidence-linked recommendations, and outcome evaluation.  
**Maturity:** Strong for current recommendation/decision lifecycle.  
**Tests:** decision journal, history, outcome, parity, privacy, ownership, idempotency, and route suites.  
**Reuse:** **REUSE unchanged as the decision/user-control substrate.** Add investment-specific outcome fields through versioned contracts, never by mutating history.

### 3.9 AI Copilot and model gateway

**Paths:** `app/services/assistant_orchestrator.py`, `app/services/llm_client.py`, `routes/assistant.py`, `ui/components/assistant/`, `ui/components/copilot/`, `ui/app/assistant/page.tsx`.  
**Purpose:** Tool-assisted conversational finance assistant with local Ollama-oriented client behavior and graceful fallback.  
**Maturity:** Implemented assistant flow; not a verified model gateway for investment agents.  
**Reuse:** **REUSE the user experience and bounded tool pattern; EXTEND with an explicit investment-analysis tool contract.**

Do not let the Copilot calculate authoritative returns, invent missing data, call providers directly, submit orders, or write canonical investment state.

### 3.10 Background jobs

No production background job framework or durable scheduler was verified. The repository contains launchd template/CLI support for Market Brief preview and documentation referring to scheduling, but current policy and readiness evidence explicitly state that scheduler, email, LLM, provider activation, trading, brokerage, execution, and money movement remained disabled. Continuous analysis therefore does not yet exist as a safe operational job system.

**Classification:** **NEW**, after idempotency, leases, retry/reconciliation, provider safety, and retention policy are defined.

## 4. Data-flow map

### 4.1 Current implemented flow

```text
User/browser
  │
  ├─ auth/session cookie/JWT
  ├─ import CSV/PDF or manual holding entry
  ├─ dashboard/goals/scenario/recommendation interactions
  │
  ▼
Next.js UI (`ui/app`, `ui/components`, `ui/lib/api.ts`)
  │
  ▼
Rules Service authenticated FastAPI routes
  │
  ├─ accounts / transactions / goals / holdings / imports
  ├─ dashboard and read APIs
  ├─ recommendations / decisions / scenarios
  ├─ market briefs / analyst ratings
  └─ assistant
  │
  ├──────────────► SQLAlchemy/Alembic local database
  │                 accounts, transactions, holdings, goals,
  │                 forecasts, recommendations, journals,
  │                 market briefs, scenarios, etc.
  │
  ├──────────────► Finlynq trusted projection-state provider
  │                 (forecast canonical boundary)
  │
  ├──────────────► Finnhub / SEC adapters
  │                 normalized, bounded, cached, paced evidence
  │
  └──────────────► deterministic calculators/composers
                    forecasts, scenarios, market briefs,
                    recommendation persistence and decision history
```

### 4.2 Current canonical forecast flow

```text
Finlynq source records and approved evidence
  → `finlynq/app/projection_state/provider.py`
  → `rules-service/app/forecast_provider/finlynq.py`
  → `forecasts/canonical_state.py` + mapper validation
  → `forecasts/service.py`
  → immutable forecast repository/models/migration
  → forecast read routes
  → goal/dashboard/scenario UI
```

The boundary is trusted-adapter-only: client requests select bounded controls; they do not supply authoritative balances, forecast state, provenance, or hashes.

### 4.3 Current Market Intelligence flow

```text
Owned active holdings (`Account` + mutable `Holding` rows)
  → `market_intelligence/composition.py`
  → `PortfolioHolding` / `PortfolioUniverse`
  → provider adapters (`FinnhubAdapter`, `SecAdapter`)
  → bounded source-cited records and normalized failures
  → quote/freshness/currency/coverage validation
  → deterministic `TrustedMarketBriefComposer` / briefing templates
  → immutable `market_briefs` records and archive/read routes
  → Market Intelligence UI / portfolio context
```

This flow is research/briefing, not a recommendation authority. Provider failures may produce truthful omissions or fail closed when no usable coverage remains.

### 4.4 Current recommendation/decision flow

```text
Validated financial state + goals + derived findings
  → deterministic recommendation derivation (`forecasts/recommendation_engine.py`)
  → immutable recommendation repository/model
  → owner-scoped recommendation routes/UI
  → user accept/reject/defer decision journal
  → immutable decision history/audit event
  → optional outcome evaluation
  → calibration/evidence for future analysis
```

The repository does not yet verify a complete security-level path from canonical holdings through portfolio analytics, investment-agent findings, investment suitability checks, and BUY/ADD/HOLD/REDUCE/SELL recommendation persistence.

### 4.5 Target extension flow

```text
Canonical accounts + investment transactions + lots + security master
  → immutable position/valuation snapshots
  → deterministic performance, allocation, risk, tax, and portfolio-fit analytics
  → normalized market/fundamental/technical/macro evidence
  → specialist investment/risk/tax/wealth analysis
  → candidate action generation
  → deterministic suitability, confidence, freshness, policy, and coverage gates
  → immutable investment recommendation
  → user review and explicit decision
  → decision journal and measured outcome
```

## 5. Relevant repository paths

| Area | Verified paths |
|---|---|
| Product/spec | `docs/00-product-vision/ATLAS_MASTER_PRODUCT_SPEC.md`, `ATLAS_AI_CFO_PRD.md` |
| System architecture | `docs/02-architecture/SYSTEM_ARCHITECTURE.md`, `DATA_ARCHITECTURE.md`, `AI_DECISION_ENGINE.md`, `ATLAS_AGENT_ARCHITECTURE.md` |
| Investment domain intent | `docs/03-domain-model/INVESTMENT_MODEL.md`, `FINANCIAL_ENTITIES.md` |
| Intelligence intent | `docs/05-intelligence/RECOMMENDATION_ENGINE.md`, `SCORING_ENGINE.md`, `FORECASTING_ENGINE.md`, `SIMULATION_ENGINE.md`, `EXPLANATION_ENGINE.md` |
| Agent intent | `docs/04-ai-agents/AGENT_OVERVIEW.md`, `INVESTMENT_AGENT.md`, `RISK_AGENT.md`, `TAX_AGENT.md`, `WEALTH_AGENT.md`, `OPPORTUNITY_AGENT.md` |
| Security/governance | `docs/08-security/AI_SAFETY_AND_MODEL_RISK.md`, `PRIVACY_MODEL.md`, `PERMISSIONS_AND_AUTONOMY.md`, `AUDIT_LOGGING.md` |
| Current roadmap/status | `docs/10-roadmap/PROJECT_STATUS.json`, `PROJECT_STATUS.md`, `CURRENT_HANDOFF.md`, `RISK_REGISTER.md`, `ATLAS_CAPABILITY_MATRIX.md` |
| Portfolio model | `services/rules-service/app/models/holding.py`, `account.py`, `import_batch.py` |
| Portfolio API | `services/rules-service/app/routes/holdings.py`, `schemas/__init__.py` |
| Analyst API | `services/rules-service/app/routes/analyst_ratings.py` |
| Market Intelligence | `services/rules-service/app/market_intelligence/*.py` |
| Forecast/recommendations | `services/rules-service/app/forecasts/*.py` |
| Scenarios | `services/rules-service/app/scenarios/*.py` |
| Assistant | `services/rules-service/app/services/assistant_orchestrator.py`, `llm_client.py`, `routes/assistant.py` |
| Finlynq canonical provider | `services/finlynq/app/projection_state/*.py`, `services/rules-service/app/forecast_provider/finlynq.py` |
| Persistence | `services/rules-service/app/models/*.py`, `services/rules-service/alembic/versions/*.py` |
| Portfolio UI | `ui/app/portfolio/page.tsx`, `ui/components/portfolio/AnalystCoverageStatus.tsx` |
| Recommendation UI | `ui/app/recommendations/page.tsx`, `ui/components/dashboard/RecommendationCard.tsx` |
| Brief UI | `ui/app/market-intelligence/page.tsx`, `ui/app/market-briefs/page.tsx`, `ui/components/market-briefs/` |
| Assistant UI | `ui/app/assistant/page.tsx`, `ui/components/assistant/`, `ui/components/copilot/` |
| Portfolio tests | `services/rules-service/tests/test_routes_holdings.py`, related holding fixtures |
| Market tests | `test_market_intelligence_foundation.py`, `test_market_briefing.py`, `test_market_brief_coverage.py`, `test_market_pulse.py`, `test_market_brief_generation_reliability.py`, `test_market_brief_operational_wiring.py` |
| Recommendation tests | `test_recommendation_engine.py`, `test_recommendation_repository.py`, `test_recommendation_schemas.py`, `test_routes_recommendations_derived.py` |
| UI tests | `ui/app/recommendations/__tests__/recommendations.test.tsx`, `ui/components/portfolio/__tests__/AnalystCoverageStatus.test.tsx`, market/universe/simulation/dashboard suites |
| CI/local validation | `.github/workflows/test.yml`, `.github/workflows/project-governance.yml`, `scripts/test.sh`, `docs/07-engineering/LOCAL_PYTHON_ENVIRONMENTS.md` |

## 6. KEEP / EXTEND / REUSE / REPLACE / NEW matrix

| Component | Classification | Decision and rationale |
|---|---|---|
| Finlynq source/projection boundary | 🟢 KEEP | Preserve server-owned canonical financial authority and trusted adapter rules. Investment state must not bypass it casually. |
| Rules Service/FastAPI | 🟢 KEEP | Existing authenticated API and domain-service home is the right host for investment intelligence. |
| Next.js UI shell and API client | 🟢 KEEP | Extend existing Portfolio, Market Intelligence, Recommendations, Goals, Decisions, and Copilot surfaces. |
| `Account` | 🟡 EXTEND | Add explicit investment-account semantics, currency/readiness/provenance links as needed; do not overload `current_balance` as a full portfolio valuation ledger. |
| `Holding` | 🟡 EXTEND temporarily | Preserve imports/manual UX, but introduce an adapter into a new canonical position/lot model. Do not make current mutable Float rows the long-term authority. |
| Raw holding symbol strings | 🔴 REPLACE as identity | Replace with a security/instrument identity plus symbol history and venue/exchange metadata. Keep symbol as a display/provider lookup attribute. |
| Portfolio import route | 🟡 EXTEND | Retain CSV/PDF compatibility; move parsing and persistence behind idempotent ingestion, reconciliation, and immutable observation services. |
| `refresh-prices` route | 🔴 REPLACE as authority | Replace direct response-only quote enrichment with persisted, timestamped valuation observations and safe stale handling. Keep a compatibility endpoint if needed. |
| Finnhub adapter/contracts | 🔵 REUSE | Already has pacing, caching, normalization, freshness, failure, provenance, and synthetic tests. Add only justified endpoints/contracts. |
| SEC adapter/contracts | 🔵 REUSE | Reuse filings/facts provenance and bounded normalization. Do not let raw SEC payloads enter agents. |
| Market Brief composer | 🔵 REUSE | Reuse coverage, evidence ranking, source citations, freshness, and deterministic composition. Separate brief generation from action recommendation. |
| Analyst ratings route | 🔵 REUSE | Treat sell-side consensus as one evidence category, never as Atlas suitability or truth. |
| Forecast service/repository | 🔵 REUSE | Reuse immutable versioning, canonical hashes, read APIs, and trusted-generation boundary for investment scenario baselines where semantically appropriate. |
| Recommendation repository/schema | 🟡 EXTEND | Add investment recommendation kinds, evidence packets, action semantics, horizon, suitability, and review/expiry contracts without weakening existing invariants. |
| Decision journal/history/outcome | 🟢 KEEP | Existing append-only user-control and calibration substrate is directly relevant. |
| Goals/scenarios/wealth calculations | 🔵 REUSE | Supply portfolio-fit context and scenario requests; do not silently reinterpret current account projection math as investment performance math. |
| Static UI recommendations | 🔴 REPLACE | Current `ui/app/recommendations/page.tsx` contains hard-coded copy and console-log approval handlers; it cannot be the production investment recommendation surface. |
| Copilot/assistant orchestrator | 🟡 EXTEND | Add read-only investment analysis tools and evidence rendering; keep calculations/policy outside the model. |
| `llm_client.py` | 🟡 EXTEND | Add a model-gateway interface only if multiple models/providers, traceability, structured output validation, and privacy controls are defined. Do not make it the financial authority. |
| Documentation agent architecture | 🔵 REUSE | Use existing specialist boundaries and explicit user-control principles. |
| Production multi-agent runtime | ⚪ NEW | Needed only after bounded tool contracts, run ledger, permissions, evaluation, and observability are specified. |
| Security master | ⚪ NEW | Required for durable security identity, classification, exchange, currency, CIK/FIGI/ISIN mapping, and symbol changes. |
| Transaction/lot ledger | ⚪ NEW | Required for exact cost basis, realized gains, dividends, splits, transfers, and performance. |
| Position/valuation history | ⚪ NEW | Required for as-of analytics, historical recommendations, stale-data handling, and outcome measurement. |
| Portfolio analytics service | ⚪ NEW | Required for performance, allocation, risk, tax, factor, benchmark, and fit calculations. |
| Investment suitability/policy service | ⚪ NEW | Required to gate action recommendations based on risk capacity, horizon, liquidity, concentration, tax, and constraints. |
| Background job system | ⚪ NEW | Continuous monitoring requires durable scheduling, leases, retries, idempotency, reconciliation, and safe shutdown. |
| Execution/broker integration | 🔴 REPLACE/OUT OF SCOPE | Do not build in this phase; user explicitly requires no trading/order execution. |

## 7. Proposed Investment Intelligence architecture

### 7.1 Ownership boundary

```text
ATLAS — canonical financial and decision platform

  Finlynq / Rules Service
    ├─ accounts, ownership, permissions, goals, cash flow, liabilities
    ├─ canonical investment ingestion and reconciliation (new)
    ├─ security master and instrument identity (new)
    ├─ transaction/lot ledger and immutable position observations (new)
    ├─ deterministic portfolio analytics (new)
    ├─ investment policy/suitability gates (new)
    ├─ normalized market evidence and provenance (existing + extended)
    ├─ specialist agent orchestration (existing boundary + new runtime pieces)
    ├─ recommendation repository and decision journal (existing + extended)
    └─ user-facing Portfolio / Market Intelligence / Recommendations / Decisions

EXTERNAL DEPENDENCIES — data and computation inputs only

  Market/fundamental providers
    ├─ quotes, candles, corporate actions, dividends
    ├─ company profiles, filings, XBRL facts
    ├─ earnings, analyst consensus, news
    └─ macro/economic series where licensed and configured

  Open-source numerical libraries
    ├─ statistics/optimization/time-series primitives
    └─ optional technical-indicator calculations after validation

  AI model providers/local models
    └─ bounded explanation, synthesis, classification, and question answering
       — never canonical calculation, policy authorization, or execution
```

### 7.2 Investment Intelligence pipeline

1. **Ingest and identify** — parse broker exports/connectors into source-scoped records; resolve instruments through a versioned security master; retain raw-source provenance under the approved retention policy.
2. **Reconcile** — compare transactions, holdings, cash, dividends, and provider snapshots; expose conflicts instead of silently choosing values.
3. **Canonicalize** — create exact numeric, currency-aware, timestamped investment records and immutable observations.
4. **Analyze deterministically** — calculate positions, cost basis, performance, allocation, concentration, risk, liquidity, fees, tax context, goal fit, and scenario impact.
5. **Collect external evidence** — use the existing provider-neutral Market Intelligence contracts and bounded adapters. Each evidence packet carries provider, source URL, retrieval/publication/observation time, freshness, and failure/coverage state.
6. **Specialist analysis** — Investment, Risk, Tax, Wealth, and Macro/Research specialists produce structured findings, assumptions, conflicts, confidence, and requested calculations. Agents cannot write canonical state.
7. **Candidate actions** — produce candidates among BUY / ADD / HOLD / REDUCE / SELL / WATCH. Candidate generation must be policy/versioned and distinguish informational observation from an actionable recommendation.
8. **Suitability and quality gate** — block or downgrade when currency is uncertain, holdings are stale, coverage is insufficient, tax impact is unknown where material, risk profile is absent, or evidence conflicts.
9. **Rank and persist** — reuse immutable recommendation identity/idempotency and link to goal(s), portfolio snapshot hash, evidence hash(es), analytics version, policy version, risks, expected impact, confidence, alternatives, horizon, expiration, and review date.
10. **Present and decide** — user sees evidence and uncertainty, then accepts/rejects/defers/watchlists through the existing decision journal. No order is sent.
11. **Evaluate** — compare prediction and realized outcome later without rewriting the original recommendation.

### 7.3 Agent boundaries

Recommended bounded specialists:

- **Portfolio Analyst:** holdings, performance, allocation, concentration, benchmark, fees.
- **Security Research Analyst:** fundamentals, filings, earnings, news, analyst evidence.
- **Quantitative Analyst:** technical/quant signals and backtests, with model/version metadata.
- **Macro/Risk Analyst:** rates, inflation, labor, regimes, stress and downside context.
- **Tax Analyst:** account/tax-lot implications, explicitly jurisdictional and non-filing advice.
- **Wealth/Goal Analyst:** portfolio fit, liquidity, goal probability, contribution/withdrawal trade-offs.
- **Recommendation Synthesizer:** combines structured findings into a candidate explanation; cannot override deterministic gates.

The existing `INVESTMENT_AGENT.md`, `RISK_AGENT.md`, `TAX_AGENT.md`, and `WEALTH_AGENT.md` documents provide conceptual boundaries. The missing implementation is a structured runtime contract and evaluation harness.

## 8. Open-source integration candidates

These are candidates for evaluation, not approved dependencies or recommendations. No new dependency was installed.

| Capability | Candidate class | Possible role | Constraints |
|---|---|---|---|
| Numerical analysis | NumPy/SciPy/pandas-style ecosystem | vectorized analytics, statistics, covariance, optimization primitives | Must preserve Decimal/accounting authority at boundaries; dependency approval and reproducibility required. |
| Technical indicators | TA-Lib or pure-Python indicator library | RSI, moving averages, ATR, MACD, and other bounded descriptive signals | Indicators are not evidence of future return; license/build portability and exact definitions must be reviewed. |
| Portfolio analytics | PyPortfolioOpt-like optimizer ecosystem | efficient-frontier/rebalance candidate calculations | Do not use as an unvalidated black box; deterministic inputs, constraints, turnover/tax costs, and fixture results required. |
| Backtesting | vectorbt/backtrader-like research tooling | offline research/evaluation only | Must never run user-facing recommendations without leakage controls, survivorship-bias controls, and versioned datasets. |
| Time-series/econometrics | statsmodels-like ecosystem | interpretable regression/forecast diagnostics | Forecasts require calibration, backtesting, missing-data policy, and explicit uncertainty. |
| Financial calendars | exchange-calendar ecosystem | trading sessions and holiday rules | Existing `market_calendar.py` is already a standard-library abstraction; extend before adding a dependency. |
| XBRL/SEC parsing | SEC/XBRL libraries | bounded filing/fact ingestion | Existing SEC adapter already normalizes required data; avoid exposing raw payloads. |
| Data validation | Existing Pydantic contracts | strict external and recommendation schemas | Prefer existing project dependency/conventions before adding another validation framework. |
| Job execution | Existing launchd/CLI only today | local preview/operations | A durable scheduler/worker is a separate architecture decision, not a casual package install. |

Selection criteria: license, maintenance, Python 3.12 compatibility, deterministic behavior, numerical semantics, security posture, data leakage risk, testability without network, and ability to explain outputs. Provider selection must be researched and authorized separately; the current repository already uses Finnhub and SEC adapters and should not gain an additional provider merely to increase breadth.

## 9. Data model gaps

### Critical gaps before implementation

1. **Security identity:** no durable `Security`/instrument master; ticker strings are not stable identity.
2. **Instrument taxonomy:** no authoritative asset class, share class, exchange, domicile, sector, geography, currency, fund/ETF metadata, derivative/crypto classification, or identifier crosswalk.
3. **Transactions and lots:** current transaction model is general cashflow-oriented and holdings are not linked to buys/sells/lots. Cost basis cannot be reliably recomputed or audited.
4. **Immutable history:** holding imports replace rows; manual PUT/DELETE mutate/delete history; no as-of position snapshot or valuation observation ledger.
5. **Corporate actions:** no verified split, merger, symbol change, spin-off, dividend reinvestment, or distribution model.
6. **Valuations:** no persisted quote/valuation observation with source, timestamp, price basis, currency, market session, and stale status tied to a position snapshot.
7. **Performance semantics:** no canonical TWR/MWR definitions, cash-flow treatment, benchmark, fee, dividend, tax, or period-boundary policy.
8. **Portfolio analytics:** no server-owned allocation/concentration/factor/risk/fee/liquidity calculations over a canonical portfolio state.
9. **Tax context:** `cost_basis_total` alone is insufficient for tax-lot or realized-gain reasoning.
10. **Suitability profile:** risk tolerance/capacity, horizon, liquidity needs, restrictions, prohibited assets, and tax jurisdiction are not verified as a complete enforced investment policy model.
11. **Evidence linkage:** Market Intelligence has evidence contracts, but an investment recommendation needs a snapshot hash linking exact portfolio state and analytics versions to each recommendation.
12. **Data quality/reconciliation:** no investment-specific reconciliation status, confidence, conflict record, or provider freshness policy.
13. **Currency:** account currency evidence exists and fails closed in some projection paths, but holding/security/quote currency conversion and mixed-currency portfolio policy are not a complete investment contract.
14. **Retention/deletion:** immutable history retention and user-deletion policy remains an open rollout blocker.
15. **Model/version metadata:** recommendation persistence needs explicit analytics formula, dataset, provider, agent, prompt/model, and policy versions.

### Suggested bounded entities

- `Security` / `Instrument` and `SecurityIdentifier`.
- `SecurityClassification` and effective-dated metadata.
- `InvestmentAccountPolicy` / suitability profile.
- `InvestmentTransaction` with source event identity and immutable raw/normalized references.
- `TaxLot` and lot events.
- `PositionSnapshot` / `PositionComponent`.
- `ValuationObservation` / `QuoteObservation`.
- `CorporateAction`.
- `PortfolioSnapshot` with canonical hash, coverage, currency, freshness, and reconciliation state.
- `PortfolioMetricSnapshot` for performance/allocation/risk with formula/calculation versions.
- `InvestmentEvidencePacket` or extension of `HoldingEvidence`.
- `InvestmentRecommendation` as a versioned recommendation kind, not a mutable row.

These are architectural candidates only; no schema should be created until domain contracts and migration authority are approved.

## 10. Agent architecture gaps

- No verified production specialist-agent runtime matching the documented multi-agent architecture.
- No structured agent input/output protocol covering portfolio snapshot hash, evidence IDs, assumptions, confidence, conflicts, and requested calculations.
- No tool permission registry that limits an agent to read-only evidence and calculation tools.
- No durable agent-run record with model/provider/version, prompt template version, tool calls, latency, failures, and output hash.
- No explicit separation between research synthesis, portfolio suitability, and recommendation authorization in executable code.
- No conflict-resolution policy when fundamental, technical, macro, tax, and goal analyses disagree.
- No investment-specific golden evaluations for factual grounding, citation fidelity, abstention, calibration, stale evidence, prompt injection, and recommendation consistency.
- No clear local/cloud model gateway contract; `llm_client.py` is a local Ollama-oriented client, not a general governed model gateway.
- No policy that prevents model-generated security symbols, prices, returns, or portfolio weights from becoming canonical facts.
- No agent memory contract tying preferences and prior decisions to effective dates and ownership while preserving canonical data precedence.

## 11. Recommendation-engine gaps

The existing recommendation substrate solves persistence/governance better than it solves investment semantics. Gaps include:

1. No explicit BUY/ADD/HOLD/REDUCE/SELL/WATCH enum and semantics verified in the production investment path.
2. No distinction between a security action, a portfolio action, a research watch item, and a non-actionable observation.
3. No action quantity/range, target weight, maximum size, expected turnover, or account-selection contract.
4. No required portfolio snapshot, valuation timestamp, evidence coverage, analytics version, or policy version fields specific to investment recommendations.
5. No deterministic suitability gate for risk capacity, horizon, liquidity, concentration, tax, restrictions, or prohibited securities.
6. No required benchmark/relative-performance context or explicit expected-impact calculation.
7. No calibrated confidence model tied to historical recommendation outcomes.
8. No recommendation expiration/review behavior verified for security-level recommendations.
9. No complete alternative/“if ignored” scenario calculation for an investment action.
10. No deduplication policy for repeated provider/news/agent findings at security and portfolio levels.
11. No clear abstention contract when data is stale, conflicting, unsupported, or incomplete beyond Market Brief coverage rules.
12. Existing frontend recommendation cards include static content and `console.log` approval handlers; they are not a server-owned investment recommendation workflow.
13. No execution is present, which is correct for the requested phase and must remain so.

## 12. Portfolio-analysis gaps

### Performance

Need explicit TWR/MWR definitions, cash-flow inclusion, valuation timing, partial periods, deposits/withdrawals, dividends, fees, splits, missing valuations, benchmark comparison, and exact rounding. Current holdings import fields cannot provide this reliably.

### Allocation

Need canonical classification and effective-dated look-through for funds/ETFs, sector/geography/issuer concentration, account/tax-location views, cash treatment, and unknown-class handling. Current UI concentration is a simple holding-value percentage and may double-count or misclassify without a canonical security taxonomy.

### Risk

Need risk-factor definitions, volatility/drawdown windows, correlation/covariance policy, concentration thresholds tied to policy, liquidity, gap/market risk, currency risk, credit/duration risk, and stress scenarios. The existing UI threshold constants are presentation heuristics, not a server risk policy.

### Fundamentals

The Market Intelligence foundation can retrieve bounded profile, filings, XBRL facts, earnings, dividends, analyst recommendations, and news. It does not yet provide normalized financial-statement history, restatement handling, derived ratios, peer groups, accounting-quality checks, or fundamental signal versioning.

### Technicals and quantitative signals

No verified backend technical-indicator or quant-signal engine was found. Any addition must define price history, corporate-action adjustment, look-ahead prevention, missing-data behavior, signal windows, backtesting, and calibration before user recommendations.

### Macro

No complete macro data provider/engine was verified. Market-wide news and index proxy contracts exist, but rates, inflation, labor, credit, currency, and regime data are not a coherent canonical macro context.

### Portfolio fit

Goal/scenario infrastructure exists, but no verified investment-specific fit calculation maps security/portfolio changes to goal probability, liquidity, risk capacity, tax location, and time horizon. This is the central Atlas differentiator and should be built as deterministic portfolio-fit analytics, not delegated to an LLM.

## 13. Risks and technical debt

### Financial correctness

- `Holding` and `Account.current_balance` use `Float`, conflicting with the project’s Decimal financial-correctness policy.
- Imported `current_value` is accepted as a snapshot fact without a durable quote/valuation provenance record.
- Quantity × price, cost-basis, and account-total arithmetic are currently performed with floating-point values in the holdings route/UI.
- No canonical period/date convention exists for investment performance.
- No corporate-action or cash-flow reconciliation means naïve return calculations would be wrong.
- The existing `Goal.target_amount` Float risk is recorded in project status and is relevant when linking recommendations to goals.

### Mutable history and provenance

- Portfolio re-import deletes prior holdings.
- Holding DELETE is hard deletion.
- Manual holding updates mutate the current row.
- Import provenance is primarily account description/import context, not an immutable position-observation event.
- Market evidence itself is substantially better governed than portfolio state; the asymmetry is a blocker for trustworthy recommendations.

### Data quality

- Symbols may be null, provider-unsupported, malformed, or ambiguously classified.
- Fidelity `Type` normalization is necessarily heuristic for some rows.
- Cash/sweep positions and unknown asset classes require explicit policy.
- Currency can be unknown/mixed/stale; the repository correctly fails closed in some paths, but investment analytics need equivalent enforcement.
- Provider coverage can be partial; recommendation quality must expose omitted holdings and not silently infer them.

### Security/privacy

- Current status records an open risk for ignored local Market Intelligence configuration containing enabled flags/provider credentials. No provider call was made in this audit; operators must not treat local configuration as safely disabled.
- External content is untrusted and must remain sanitized/isolated before model use.
- Cross-user ownership must be enforced before existence disclosure and before agent retrieval.
- Investment evidence can reveal sensitive holdings; evidence minimization and retention must be explicit.
- Existing retention/deletion policy for immutable history is unresolved for broader rollout.

### API and architecture

- Holdings API and newer versioned `/api/v1` forecast/scenario/recommendation contracts are inconsistent in maturity and semantics.
- Direct network logic remains in the legacy holdings price-refresh route while newer Market Intelligence uses adapters/controls.
- No durable job API/status model exists for continuous analysis.
- The assistant and Copilot are not a governed investment model gateway.
- Static frontend recommendations can create a misleading impression of live personalized intelligence.

### Testing

Strong focused coverage exists for holdings parser behavior, Market Intelligence normalization/provider safety, recommendation persistence, immutable history, ownership, and UI journeys. Missing or insufficient investment-specific evidence includes:

- Exact Decimal portfolio-performance fixtures.
- Transaction/lot/corporate-action reconciliation fixtures.
- Historical valuation and as-of consistency tests.
- Benchmark and cash-flow return golden tests.
- Security-master identifier resolution and symbol-change tests.
- Portfolio-level risk/factor/sector look-through fixtures.
- Suitability/policy boundary tests.
- Recommendation calibration/backtesting/evaluation tests.
- Agent groundedness, citation, abstention, prompt-injection, conflict, and model-version tests for investment tasks.
- Durable job idempotency/retry/recovery tests.

## 14. Phase 1 blockers that must be resolved before implementation

For this proposed Investment Intelligence initiative, the following are implementation blockers, even though the repository’s current Phase 6 release candidate is complete for its existing personal scope:

1. **Investment authority decision:** approve whether canonical investment records live in Rules Service, Finlynq, or a formally defined split; do not create a second competing source of truth.
2. **Security master contract:** define stable identity, identifiers, symbol/exchange changes, asset taxonomy, currency, issuer, fund look-through policy, and provenance.
3. **Exact numeric contract:** replace Float authority for quantity/price/value/cost basis with Decimal-safe canonical strings/NUMERIC policy, including rounding and serialization.
4. **Immutable investment history:** define append-only source events, transaction/lot records, position snapshots, valuations, corrections, import replacement semantics, retention, and recovery.
5. **Performance policy:** approve TWR/MWR, dividends, fees, deposits/withdrawals, benchmark, dates, time zones, missing data, and corporate-action treatment.
6. **Risk/suitability policy:** define risk capacity/tolerance, horizon, liquidity, concentration, tax, restrictions, prohibited assets, and fail-closed conditions.
7. **Recommendation contract:** define action enum, evidence/assumptions, impact, confidence, horizon, alternatives, expiry, review cadence, and user decision semantics.
8. **Provider policy:** approve external data sources, licensing/terms, cost ceilings, quotas, freshness, provenance, and default-off configuration. Do not activate existing local credentials implicitly.
9. **Agent boundary:** define structured read-only tools, model gateway, run ledger, prompt/model versioning, evaluation, and no-write/no-execution rules.
10. **Retention/deletion policy:** resolve the existing immutable-history rollout blocker before designing durable investment history.
11. **Continuous-analysis operations:** decide whether “continuously” means on-demand, local scheduled refresh, or durable background jobs; define retries, idempotency, stale state, and operator controls.
12. **Scope boundary:** explicitly keep brokerage connectivity, trading, order submission, autonomous execution, and money movement out of this phase.

## Human decision boundary

```text
Research → Analysis → Recommendation → User Decision

Never: Research → Analysis → Recommendation → Automatic Execution
```

## 15. Recommended implementation sequence

### Stage 0 — Contract and ADRs (documentation only)

- Record the investment authority decision and canonical dependency graph.
- Approve security, suitability, recommendation, evidence, freshness, retention, and exact-number contracts.
- Define the first bounded vertical slice: read-only portfolio snapshot + one evidence-backed WATCH/HOLD-style review, not trading.

### Stage 1 — Canonical investment data foundation

- Add security identity and identifier resolution behind adapters.
- Add immutable investment source events/import batches with idempotency and reconciliation status.
- Add investment transactions/lots and position/valuation observations.
- Preserve current import/manual UI through compatibility adapters.
- Add Decimal-safe fixtures and SQLite/PostgreSQL parity tests.

### Stage 2 — Deterministic portfolio analytics

- Implement as-of portfolio snapshots and exact market-value aggregation.
- Implement performance, allocation, concentration, liquidity, fee, and basic risk metrics with versioned formulas.
- Add benchmark and cash-flow policy.
- Add portfolio-fit inputs from goals, horizon, risk, and tax context.
- Fail closed for unknown currency, stale valuation, unsupported security, unresolved reconciliation, and insufficient coverage.

### Stage 3 — Evidence expansion

- Extend existing Market Intelligence contracts/adapters only where required.
- Add normalized fundamentals, technical history/signals, macro context, and corporate actions behind provider-neutral interfaces.
- Persist source metadata/evidence hashes and coverage omissions.
- Keep synthetic transports and no-network tests as the default validation mode.

### Stage 4 — Investment recommendation substrate

- Extend existing recommendation schemas/repository with versioned investment action kinds.
- Link each recommendation to portfolio snapshot hash, analytics versions, evidence packet, goal(s), risks, confidence, horizon, alternatives, review/expiry, and required approval.
- Implement deterministic suitability and quality gates before any model synthesis.

### Stage 5 — Specialist analysis and Copilot integration

- Introduce structured read-only Investment/Research/Quant/Macro/Risk/Tax/Wealth agent tools.
- Add model gateway/run trace/evaluation contracts.
- Use models only for bounded synthesis/explanation and abstention-aware reasoning.
- Add investment golden evaluations and adversarial tests.

### Stage 6 — User experience and decision loop

- Replace static recommendation cards with server-owned recommendation data.
- Add recommendation detail with evidence, assumptions, confidence, risk, expected impact, time horizon, data freshness, and “why not” alternatives.
- Reuse decision journal and outcome evaluation; preserve append-only history.
- Add watchlist/review cadence without execution.

### Stage 7 — Operational monitoring, only if separately authorized

- Add local/durable background jobs, provider health, stale-data monitoring, retry/reconciliation, and bounded notifications.
- Keep all email, external delivery, brokerage, trading, execution, and money movement disabled unless separately approved by a later phase.

## 16. Explicit list of things we should NOT build ourselves

1. Brokerage connectivity, order routing, trade execution, settlement, custody, or money movement in this phase.
2. A second database/source of truth separate from the existing Atlas/Finlynq authority.
3. A proprietary market-data exchange, quote plant, or global historical price database.
4. A proprietary SEC/XBRL parser when the existing bounded SEC adapter or maintained library is sufficient.
5. A custom password/authentication/credential-vault system; use the existing auth boundary and approved secret-management infrastructure.
6. A custom database engine, queue, scheduler, distributed lock service, or cache when an approved maintained component is appropriate.
7. A custom general-purpose statistics, linear algebra, optimization, or technical-indicator implementation without first proving an existing maintained library is inadequate.
8. A black-box “AI predicts the stock price” model presented as fact or certainty.
9. An LLM-based calculator for balances, returns, tax lots, prices, allocations, risk, or goal probability.
10. A proprietary broker tax-lot accounting system without authoritative broker/source data and explicit tax policy.
11. A proprietary news search/crawling ecosystem; use licensed/provider data behind normalized contracts.
12. A hidden autonomous multi-agent loop that can write canonical financial state or trigger actions.
13. A parallel recommendation/history/audit system; extend the existing immutable recommendation, decision journal, outcome, and audit substrates.
14. A duplicate frontend portfolio/recommendation architecture; extend existing routes/components and replace only misleading static behavior.
15. A universal macro regime oracle or unsupported causal claim from sparse data.
16. A backtesting system whose results ignore look-ahead bias, survivorship bias, corporate actions, transaction costs, taxes, slippage, or dataset versioning.
17. A “continuous” scheduler that silently calls providers, sends email, or changes flags without explicit operator authorization.
18. Any feature that turns analyst consensus into Atlas’s personalized suitability decision without deterministic portfolio-fit and policy checks.

## Human decision boundary

```text
Research → Analysis → Recommendation → User Decision

Never: Research → Analysis → Recommendation → Automatic Execution
```

## Final recommendation

**Proceed After X.** The repository already provides the correct Atlas extension seams: server-owned financial authority, bounded Market Intelligence adapters, immutable recommendation/decision history, goals/scenarios, authenticated APIs, and existing portfolio/UI surfaces. However, the current `Holding` snapshot/import model is not sufficient to support trustworthy security recommendations. Resolve the investment data authority, exact-number/history, security-master, valuation/performance, suitability, evidence, agent, and retention contracts first; then implement a single read-only vertical slice by extending the existing architecture. Do not activate providers, add continuous jobs, introduce LLM recommendation authority, or build any brokerage/trading/execution capability as part of that initial implementation.

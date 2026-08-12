# Phase 6 Scenario Lab: Capability Audit and Proposed Plan

> **Status:** Planning only. Phase 6 implementation is **not authorized**.
>
> **Audit date:** 2026-08-11
>
> **Evidence baseline:** clean `main` at `ecaeaa2`, certified Phase 5 tag
> `phase-5-complete`; no production code, API, schema, migration, dependency,
> test, or UI change was made for this audit.

> **Operational sequencing update:**
> `PHASE5_OPERATIONAL_READINESS_AUDIT.md` identifies an undiscoverable archive
> and test-only brief composer. A bounded Phase 5 operationalization correction
> must be authorized and completed before Phase 6 implementation.

## Audit method and runtime boundary

This is an evidence-based code and runtime-wiring audit, not a filename
inventory. Each entry below was traced from user surface through client/API,
calculation, persistence, and tests where they exist.

The documented lifecycle command `start.sh --check` confirms Atlas ports UI
`3333`, Rules Service `8888`, and Finlynq `8889`. A live interactive startup
was intentionally not run: normal `start.sh` targets the local `finance.db`
and its Rules Service startup hooks may seed demo recommendations. That would
alter local data, contrary to this audit's no-data-mutation boundary. The
canonical clean-main test lifecycle did exercise an isolated browser stack
with synthetic data during Phase 5 certification (hosted run `31505665961`:
Playwright 86 passed, 1 skipped). Thus runtime reachability below is based on
the registered UI/router wiring plus that synthetic browser evidence; it does
not claim a live personal-data walkthrough.

## Capability matrix

| Capability | Current implementation | Runtime status | Evidence | Quality / risk | Recommended disposition |
| --- | --- | --- | --- | --- | --- |
| Canonical financial / projection state | Finlynq builds a goal-specific canonical projection envelope; Rules Service accepts only the sanctioned adapter boundary. | Production-wired but feature-gated for forecast use. | `services/finlynq/app/routes/projection_state.py:get_goal_projection_state` → `projection_state.provider:build_projection_state`; `rules-service/app/forecast_provider/finlynq.py:HttpFinlynqProjectionStateAdapter`; tests `test_projection_state_provider.py`, `test_finlynq_projection_provider.py`, `test_canonical_projection_state.py`. | User-scoped, persistent source records; deterministic envelope; currency/freshness fail closed. Transitional tenancy and currency-authority risks remain. | Keep unchanged |
| Authoritative goal forecast | Immutable Rules Service forecast generation uses `Decimal`, canonical hashes, scenario bands, and version snapshots. | Production-wired but default-off. | `routes/forecasts_generation.py:generate_forecast_for_goal` → `forecasts/service.py:ForecastGenerationService.generate` → `calculations/projection.py:project_scenarios` → `models/forecast.py`; migration `R6f1g2h3i4j5`; tests `test_atlas_projection.py`, `test_forecast_service.py`, `test_forecast_repository.py`, `test_routes_forecast_generation.py`. | Persistent, deterministic, user-scoped, auditable, Decimal-safe; one goal / USD-only and legacy `Goal.target_amount` Float conversion are explicit constraints. | Keep unchanged |
| Goals / goal modeling | Goals UI manages current goal records; persisted forecasts, derived recommendations, and journal/history components are mounted beneath it. | Production-wired; forecast-derived panels are default-off. | `ui/app/goals/page.tsx`; `routes/goals.py`; `models/goal.py`; `LatestForecastSection.tsx`, `DecisionHistorySection.tsx`; tests `test_routes_goals.py`, `ui/__tests__/goals.test.tsx`, `goals-phase2-slice.spec.ts`. | Goal CRUD is persistent and user-scoped; UI has older visual-only what-if logic and float-facing values alongside authoritative forecast APIs. | Extend |
| Dashboard “Wealth Simulation” suite | Shared React context connects timeline, sliders, four preset life events, Financial DNA, and Financial Twin. It calls client projection math only. | Production-wired and reachable on dashboard when `summary` is ready; not a saved Scenario Lab. | `ui/app/page.tsx:WealthSimulationProvider`; `components/simulation/{WealthSimulationContext,MoneyFlowSimulator,LifeEventSimulator,WealthTimeline,FinancialTwin,FinancialDNA}.tsx`; tests `SimulationComponents.test.tsx`, `WealthSimulationContext.test.tsx`. | Ephemeral, deterministic but **Number/float-based**, unaudited, user presentation state only; no API, DB model, migration, goal/recommendation/decision linkage, or feature flag. Preset scenario values are hard-coded. | Refactor |
| Client projection utility | Formula utility supports FV and inflation-adjusted dashboard trajectory. | Used by dashboard simulation suite and dashboard presentation. | `ui/lib/math/projection.ts:calculateFutureValue`, `projectDashboardTrajectory`; tests `ui/lib/math/__tests__/projection.test.ts`, `atlasProjectionParity.test.ts`. | Pure/deterministic but JS Number; not the financial authority for persisted outcomes. | Replace |
| Financial Digital Twin | Three deterministic narrative cards project values at ages 50/60/65 from React context. | Production-wired on dashboard; visible only with dashboard summary. | `components/simulation/FinancialTwin.tsx` ← `useSimulation`; mounted in `ui/app/page.tsx`; `SimulationComponents.test.tsx`. | Ephemeral, float-based, no profile-age persistence beyond default age `35`; narrative template is not audited or linked to a decision. | Expose existing capability |
| Money-flow visualization | Four-stage Sankey aggregates imported transactions into income, groups, categories, retained/overspend. | Production-wired and reachable on dashboard. | `ui/app/page.tsx` → `rulesService.getDashboardFlows` → `routes/dashboard.py:get_dashboard_flows` → `SankeyHero.tsx` → `charts/SankeyFlow.tsx`; route tests include dashboard coverage. | Persistent transaction inputs, deterministic/user-scoped aggregation; visualization only, uses API numeric values and carries no scenario mutation or persistence. | Keep unchanged |
| Cash-flow forecasting | Current dashboard trends/breakdown and money-flow aggregation are historical/reporting, not a forecast engine. | Production-wired for actuals; future cash-flow forecast is missing. | `routes/dashboard.py` `/flows`, trends/breakdown; dashboard data fetching in `ui/app/page.tsx`. | Connected to imported transaction data, but no future recurrence/seasonality/tax/cash-balance forecast, confidence, or backtest record. | Build new |
| What-if contributions / savings changes | Slider contribution changes and preset life-event deltas recompute dashboard projections. | Production-wired but incomplete. | `MoneyFlowSimulator.tsx`; `LifeEventSimulator.tsx`; `WealthSimulationContext.tsx:computeProjection`. | Ephemeral float math, bounded only by UI sliders, not goal-aware, not persistent/auditable, and not safe to present as an authoritative financial forecast. | Refactor |
| Large-purchase / retirement / income scenarios | Only hard-coded `buy-house`, `early-retirement`, `job-change`, and `new-child` presentation presets exist. | Production-wired demo-like UI behavior; no saved or authoritative scenario. | `WealthSimulationContext.tsx:SCENARIOS`; `LifeEventSimulator.tsx`. | No purchase amount/down-payment/debt model; retirement only stops contributions; income scenario is a fixed delta. No business model. | Consolidate |
| Portfolio analysis | Holdings, live-price refresh, portfolio UI, analyst ratings, Phase 5 deterministic attribution/exposure and briefing provide different slices. | Production-wired but mixed maturity; market briefing flags default off. | `routes/holdings.py`, `ui/app/portfolio/page.tsx`, `routes/analyst_ratings.py`; `market_intelligence/{composition,briefing}.py`; tests `test_routes_holdings.py`, `test_market_briefing.py`, `test_market_intelligence_foundation.py`. | Holdings are persistent but legacy float; Phase 5 analysis is Decimal-safe and source-cited but default-off. No scenario allocation optimizer or joint goal impact. | Extend |
| Recommendations | Phase 3 deterministic derived recommendation contract plus legacy seeded/smart recommendation paths coexist. | Derived path is feature-gated; legacy screen is production-wired with static/demo-looking content. | `forecasts/recommendation_engine.py`, `recommendation_repository.py`, `routes/recommendations_derived.py`; `routes/recommendations.py`; `ui/app/recommendations/page.tsx`; tests `test_recommendation_engine.py`, `test_routes_recommendations_derived.py`. | Persistent/auditable derived records are goal/forecast-linked; legacy startup seed (`app/main.py:_seed_default_recommendations`) and static UI copy are duplicate concepts. | Consolidate |
| Decisions and outcomes | Append-only decision history/audit events and outcome evaluation link decisions to forecasts/recommendations. | Production-wired but read/history flags default off. | `models/{decision_history,decision_journal_entry,outcome_evaluation}.py`; migrations `T8`, `U9`, `V0`; `forecasts/{decision_journal_service,decision_history_service,outcome_evaluation_service}.py`; routes and tests named `test_decision_*`, `test_outcome_evaluation_*`. | Persistent, user-scoped, auditable; correctly distinguishes acceptance from execution/outcome. | Keep unchanged |
| Market intelligence inputs | Finnhub/SEC normalized contracts and trusted owner-holdings composer produce immutable source-cited briefs. | Implemented but default-off; no real provider activation during certification. | `market_intelligence/{contracts,adapters,controls,composition,briefing,brief_repository}.py`; `routes/market_briefs.py`; migrations `M5`, `N5`; tests `test_market_intelligence_foundation.py`, `test_market_briefing.py`, `test_market_delivery.py`. | Persistent briefing archive; deterministic Decimal-safe impact; external text untrusted; zero-dollar/feature-flag boundaries. It is a contextual input, not a simulation engine. | Keep unchanged |
| Saved scenarios / plans | No scenario identity, immutable scenario version, scenario API, migration, or saved-plan UI exists. | Missing. | No caller from `WealthSimulationContext` to any API; no scenario model/migration found; only forecast/brief/decision persistence models exist. | Existing UI state is discarded on reload and cannot be reproduced, audited, compared, or attached to a decision. | Build new |
| Probability, tax, business, and multi-goal planning | Product/intelligence documents describe broad planning capabilities, but no runtime engine or reachable surface implements them. | Documentation-only / missing. | `docs/05-intelligence/{SIMULATION_ENGINE,FORECASTING_ENGINE,GOAL_ENGINE}.md`; ADR-005 defers Monte Carlo; no corresponding engine, model, route, migration, or UI caller was found. | Product narrative must not be represented as shipped financial functionality. | Build new (deferred) |

## End-to-end traces and classifications

### 1. Dashboard simulation is real UI, but presentation-only

`ui/app/page.tsx` loads dashboard summary and mounts
`WealthSimulationProvider` only when summary data is ready. The provider holds
slider values and `activeScenario` in React state; it calls
`ui/lib/math/projection.ts` and passes derived numbers to the timeline and
twin. No fetch, route, service, database model, migration, feature flag, or
persistence call exists in this path. Its component tests prove local
interaction, not financial-authority or persistence behavior.

Classification: **production-wired and usable as exploratory UI; ephemeral,
deterministic, user-visible, float-based, unaudited, and disconnected from
goal/recommendation/decision persistence.** The “Financial Twin” is a
dashboard visualization, not a canonical Digital Twin.

### 2. Authoritative forecasting is already a different vertical slice

`POST /api/v1/goals/{goal_id}/forecasts` authorizes the goal before calling
the narrowly scoped Finlynq provider. `ForecastGenerationService` validates
fresh, reconciled USD state, constructs a `ProjectionRequest`, invokes the
Rules Service Decimal calculation, and persists an immutable forecast version.
The client reads through `LatestForecastSection` and can derive a
recommendation and append a decision journal entry. Feature flags
`atlas_forecast_persistence_enabled`, `atlas_forecast_read_api_enabled`, and
`atlas_decision_history_api_enabled` are server-owned defaults-off.

Classification: **implemented, persistent, deterministic, user-scoped,
Decimal-safe, and auditable; production-wired but incomplete/default-off.**
It is the only current calculation authority for persisted goal outcomes.

### 3. Money flow is actual-data visualization, not scenario flow

The dashboard fetches `/dashboard/flows`, and Rules Service derives Sankey
nodes/links from user transactions. `SankeyHero` and `SankeyFlow` make it
interactive and accessible, but clicking changes local selection only. It
does not alter a forecast nor persist a scenario.

Classification: **production-wired, persistent-source, deterministic,
user-scoped visualization; not a forecasting/simulation model.**

### 4. Recommendation and decision systems are reuse targets, not replacements

The immutable forecast/recommendation/decision/outcome chain provides the
existing approval and audit substrate. A Scenario Lab must create an explicit
reviewable comparison artifact and may create a recommendation candidate; it
must not substitute static dashboard recommendation cards, seed demo
recommendations, or make a scenario itself a decision/execution.

## Reuse, conflicts, and documented/runtime gaps

1. **Do not duplicate calculation authority.** `app.calculations.projection`
   and the canonical Finlynq projection-state envelope are authoritative for
   persisted goal forecasts. The client `ui/lib/math/projection.ts` is useful
   only for immediate visual preview and must never be the source of a saved
   result, recommendation, or decision.
2. **Scenario Lab seed UI already exists.** Reuse the dashboard provider's
   slider controls, preset cards, timeline, Financial Twin cards, and Sankey
   styling. Move their state/labels behind a server-issued Scenario Lab
   contract rather than cloning components.
3. **Consolidate duplicate recommendation concepts.** Retain deterministic
   forecast-derived recommendations and decision history. Treat static
   recommendations and startup demo seeding as legacy presentation paths;
   do not build a new recommendation type for scenarios.
4. **Do not duplicate persistence or audit models.** Forecast versions,
   decision history/audit events, and outcome evaluations remain their current
   owners. A new scenario identity/version is needed only after the proposal
   defines reproducibility, ownership, retention, and decision linkage.
5. **Float boundary is material.** Client simulator numbers, holdings values,
   and legacy goal target values are float-based. Scenario persistence must
   use canonical Decimal strings and an explicit currency/freshness contract;
   it must fail closed on ambiguous/mixed currency.
6. **Document/runtime mismatch.** Product documents describe probability,
   Monte Carlo, taxes, business forecasts, full cash-flow forecasting, goal
   conflicts, and a Simulation Lab. Current runtime has deterministic
   scenario bands and dashboard sliders only; no probability engine, taxes,
   scenario persistence, business scenario, or joint-goal optimizer exists.
7. **Hidden/default-off capability.** Forecast/derived recommendation/
   decision-history and market-brief APIs are present but disabled by checked
   in defaults. A Phase 6 plan must not promise they are generally enabled.

## Smallest sensible proposed Phase 6 — Scenario Lab foundation

**Decision:** Phase 6 should **expose and complete the existing simulation
experience by extending the authoritative forecast vertical slice**, not build
a second simulator, allocation optimizer, or probabilistic Digital Twin.

### Proposed objective

Offer an authenticated, goal-scoped Scenario Lab where a user can compare a
small number of explicitly bounded contribution and life-event assumptions
against the current immutable forecast, save a reproducible scenario version,
and optionally create an existing review-only recommendation/decision follow
up. It remains read/analyze/recommend only: no brokerage execution, money
movement, cloud LLM, external multi-user rollout, tax advice, Monte Carlo, or
business forecasting.

### Required invariants

- Reuse `CanonicalProjectionState`, `ProjectionRequest`, and Rules Service
  Decimal calculation; no browser result becomes authoritative.
- One owned goal and explicit USD-only currency per first release; reject
  stale, unreconciled, missing, mixed, or unsupported state.
- Persist immutable, versioned scenario inputs/results with canonical Decimal
  strings, model/calculation version, source freshness, scenario hash, and
  deterministic idempotency.
- Model only bounded deltas initially: monthly contribution change, a dated
  contribution start/stop, and one explicit one-time outflow. Do not reuse the
  four current hard-coded UI presets as financial facts.
- Maintain approval boundaries: a scenario is not a trade, execution, or
  decision. Existing decision journal linkage is explicit and optional.
- Client-visible preview is clearly labelled as local/indicative until the
  server returns a saved/authoritative scenario result.

### Suggested cohesive delivery slices (authorization required before any work)

1. **Scenario contract and authoritative engine (high risk).** Define the
   scenario domain/ADR, pure Decimal scenario transformation around the
   existing projection engine, canonical hash/version/freshness contracts,
   and comprehensive fixtures. No UI or persistence yet.
2. **Immutable saved scenario and comparison API (high risk).** Add one
   owner-scoped identity/version history, idempotent generate/read/compare
   routes, and optional non-executing recommendation/decision references.
   Reuse forecast repository/audit conventions rather than copy them.
3. **Scenario Lab UI migration (high risk).** Refactor—not duplicate—the
   dashboard simulation controls/timeline/twin into an accessible goal-scoped
   lab. Keep local preview clearly separated, add saved comparison/history,
   source/freshness warnings, and browser/a11y coverage.

### Explicit deferrals

- Probability / Monte Carlo, tax models, withdrawals, irregular cash flows,
  business income/valuation, multi-goal optimization, portfolio optimizer,
  financial-plan execution, household tenancy, advisor sharing, and real
  external provider activation.
- A decision to retire the legacy dashboard simulation visuals entirely;
  retain them while a governed Scenario Lab reaches parity.

## Planning exit criteria (not implementation authorization)

Before Phase 6 implementation can be authorized, approve a scenario ADR and
contract covering Decimal/currency/freshness, one-time outflow semantics,
scenario-to-forecast/recommendation/decision linkage, immutable retention,
and client-preview labelling. Confirm the existing default-off flags and
Phase 5 external-data boundaries remain unchanged. First complete the bounded
Phase 5 operationalization correction documented in
`PHASE5_OPERATIONAL_READINESS_AUDIT.md`. No active tracker item or Phase 6
implementation branch is created by this audit.

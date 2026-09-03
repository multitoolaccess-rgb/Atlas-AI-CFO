# Atlas UI-11 Risk and Scenario Readiness Audit

**Status:** `IMPLEMENTED: BOUNDED CURRENT-ONLY SLICE`
**Audit date:** 2026-09-03
**Scope:** UI-11 risk/scenario methodology and trusted portfolio baseline contract
**Decision boundary:** Read-only analysis and explicitly hypothetical projections; no portfolio mutation or execution
**Authority:** Current repository implementation, INV-01 through INV-HARDEN-01 contracts, Scenario Lab contract/ADR, UI roadmap, security model, and focused tests

## Executive Verdict

UI-11's first slice is implemented and validated as a bounded current-only portfolio baseline plus an on-demand descriptive hypothetical preview. It is not a certification of historical portfolio risk or advanced risk methodology.

The repository contains useful adjacent capabilities:

- owner-scoped `Account` and `Holding` records;
- a deterministic in-memory `PortfolioSnapshot` projection;
- canonical investment security, observation, committee, recommendation, and outcome contracts;
- a server-owned, immutable, deterministic **goal-scoped** Scenario Lab; and
- existing portfolio and chart presentation surfaces.

Those capabilities do not establish authority for historical portfolio risk or advanced metrics. The accepted first slice therefore defines a separate current-only baseline and bounded descriptive preview in `docs/adr/ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`. Existing Scenario Lab results remain goal projections and are not relabeled as portfolio risk.

This document originally served as the UI-11 readiness gate. The approved first slice is now implemented; the remaining sections distinguish delivered guarantees from deferred historical and advanced-risk expansion. The delivered boundary does not modify `InvestmentRecommendation`, `CommitteeFinding`, `HumanDecisionRecord`, `RecommendationOutcome`, or the goal Scenario Lab semantics.

## 1. Current Phase and Scope Status

| Area | Current status | UI-11 disposition |
|---|---|---|
| INV-01 security identity | Domain contract exists | Reuse only after a canonical universe/security source is identified; do not derive authority from ticker text |
| INV-02 market observations | Typed point-in-time contracts and research helpers exist | Reuse only with a server-owned observation repository/adapter and compatible series |
| INV-03 portfolio intelligence | Deterministic in-memory snapshot over accounts/holdings exists | Useful starting projection; insufficient as a historical, currency-aware risk baseline |
| INV-04 through INV-07 research | Typed domain contracts/helpers exist | Optional future inputs; no UI-11 metric is approved merely because a helper exists |
| INV-08 committee | Typed evidence-linked context/findings exist | Read-only context may be linked later; not a risk methodology |
| INV-09 recommendation | Trusted persisted recommendation boundary exists | Optional display context only; discovery/risk must not become recommendation authority |
| INV-10 CIO reporting | Bounded in-memory report projection exists | Not required for UI-11; archive remains deferred |
| INV-11 decision/outcome | Durable decision/outcome boundary exists | History may be linked as context later; UI-11 must not create decisions or outcomes |
| INV-HARDEN-01 | Temporal, provenance, hash, ownership, and fail-closed rules exist | Must be inherited by every new risk/scenario projection |
| Scenario Lab | Implemented and tested | Reuse calculation/persistence conventions only; it remains goal-scoped |
| UI-08 through UI-10 | Certified | Preserve contracts; no regressions or semantic reuse shortcuts |
| UI-09 | Complete for its approved bounded discovery modes | A discovery candidate is not a portfolio-risk result or recommendation |
| UI-11 | Bounded first slice implemented | Current-only baseline and on-demand descriptive preview are validated; historical and advanced risk remain unavailable |
| INV-12 | Not started | Independent evaluation/replay/retention gate; not a substitute for UI-11 methodology |
| UI-12 | Not started | Must follow stable UI-11 and INV-12 decisions |

## 2. Authoritative Data Source Inventory

The table below classifies actual runtime sources rather than file names alone.

| Source | Runtime location | Owner-scoped? | Canonical? | Persistent? | Point-in-time? | UI-11 suitability |
|---|---|---:|---:|---:|---:|---|
| Security identity primitives | `app/investments/securities.py`, `app/investments/contracts.py` | Usually context-scoped | Yes as contracts | No general security-master persistence found | Contract has `as_of`; available source records are not established | **Yellow**: reusable contract, but a trusted source/adapter and identity reconciliation are still required |
| Imported accounts | `app.models.Account`, `/api/accounts/` | Yes by `user_id` | Source record, not risk authority | Yes | `last_sync`/timestamps exist, but no immutable valuation snapshot | **Yellow** for ownership context; insufficient as a risk baseline alone |
| Imported holdings | `app.models.Holding`, `/api/holdings/` | Indirectly through owned account | Source record, legacy float values | Yes, but imports replace account holdings | Current import row; no canonical historical observation identity | **Yellow** for current portfolio composition; unsafe for historical risk without a snapshot adapter |
| Portfolio snapshot projection | `app.investments.portfolio_intelligence.build_portfolio_snapshot` | Yes; filters accounts by owner | Typed `PortfolioSnapshot` projection | No | Caller supplies `as_of`; position data is not independently observed at that time | **Yellow**: safe as a deterministic current projection after hardening, not yet a durable baseline |
| Portfolio position identity | `portfolio_intelligence._identity` | Inherits owner scope | Not fully canonical; derives from symbol/type | No | Uses epoch `1970-01-01` for generated security identity | **Orange** for UI-11: cannot be the final canonical security/observation authority |
| Market observations | `app.investments.market_observations.MarketObservation` | Contract can be scoped; source adapter not established in the inspected UI-11 path | Yes as a contract | No portfolio observation repository identified | Yes: `observation_time`, `as_of`, `retrieved_at`, hash, adjustment basis | **Yellow** if connected through a trusted server adapter with series completeness |
| Technical research | `app.investments.technicals` | Contract-scoped | Yes as a calculation contract | No dedicated portfolio read model | Yes when input points carry timestamps/hashes | **Yellow** for approved per-security metrics only |
| Quant research | `app.investments.quant` | Contract-scoped | Yes as a calculation contract | No dedicated portfolio risk aggregate | Yes when aligned input series exist | **Yellow** for bounded descriptive metrics; no portfolio methodology is defined |
| Committee context/findings | `app.investments.committee_contracts` and persistence boundary | Yes | Yes for INV-08 | Yes for persisted investment records | `analysis_as_of`, packet hashes, input hashes | **Green** as optional explanatory context, not as the risk engine |
| Investment recommendations | Investment persistence repository/routes | Yes | Yes for INV-09 | Yes, immutable | Yes, recommendation/evidence/portfolio hash fields | **Green** as optional existing-recommendation context; **not** a discovery or risk source |
| Goal forecast baseline | `Forecast`, `ForecastVersion`, `ScenarioService` | Yes by goal owner | Yes for goal projection | Yes, immutable versions | Baseline freshness/state hash exists | **Green** only for goal scenarios; **redirection prohibited** for portfolio-risk semantics |
| Scenario Lab | `app.scenarios.*`, `/api/v1/goals/{goal_id}/scenarios`, `/api/v1/scenarios/*` | Yes by goal owner | Yes for goal-scoped what-if | Yes, immutable versions | Baseline and source freshness are preserved | **Green** for goal scenario presentation; **not UI-11 portfolio risk authority** |
| Portfolio UI aggregation | `ui/app/portfolio/page.tsx`, `ui/app/portfolio/intelligence/page.tsx` | API is owner-scoped | No; presentation projection | No separate snapshot | Uses current API payloads and browser `Date`/`Number` formatting | **Red** as authority; may remain a presentation consumer |
| Market Brief | `app.market_intelligence.*`, `/api/v1/market-briefs/*` | Owner-scoped | Canonical brief projection for its purpose | Yes for brief records | Brief contracts preserve source context | **Yellow** as contextual evidence only; not a portfolio-risk baseline |
| Recommendations/goal model | `app.models.recommendation`, forecast recommendation services | Owner-scoped | Canonical for legacy goal/forecast workflow | Yes | Forecast-linked, not portfolio-risk history | **Red** as the source of UI-11 discovery/risk semantics |
| Synthetic fixtures | `services/rules-service/tests`, `tests/synthetic_fixtures` | Test-scoped | Test authority only | Test-only | Deterministic fixture timestamps | **Green** for tests; never production authority |

## 3. Data Pipeline Trace

### 3.1 Current holdings path

```text
CSV/PDF import or manual holding input
  -> Account/Holding rows
  -> /api/holdings/
  -> Portfolio and Portfolio Intelligence React pages
  -> browser aggregation, sorting, and labels
```

This path is useful for current owner-scoped display. It does not create a versioned valuation snapshot, preserve a source observation hash for each price, or establish a historical baseline that can be replayed. `Holding` values are legacy floating-point fields. A portfolio position's currency is currently left unknown by `build_portfolio_snapshot`, and the generated security identity is derived from the imported symbol/type.

**Conclusion:** current holdings can seed a future trusted baseline adapter, but the UI-11 implementation must not treat the current route payload as the risk authority.

### 3.2 Existing portfolio projection path

```text
Account/Holding ORM rows
  -> build_portfolio_snapshot(owner_id, accounts, holdings, as_of)
  -> typed PortfolioSnapshot
  -> deterministic total/exposure/completeness/hash
```

The projection correctly filters holdings through accounts owned by the requested owner, preserves unknown values, avoids treating missing values as zero for totals, and produces a deterministic hash. However, `as_of` is supplied by the caller and is not tied to a persisted observation set. `available_cash` is not populated, currency is not inferred, and there is no durable snapshot ID or reload API.

**Conclusion:** this is the correct shape for a baseline projection seam, but not a complete UI-11 baseline contract.

### 3.3 Existing Scenario Lab path

```text
Authenticated goal
  -> trusted Finlynq CanonicalProjectionState
  -> immutable goal ForecastVersion
  -> unchanged Decimal projection engine
  -> immutable ScenarioVersion
  -> Scenario Lab API/UI
```

Scenario Lab is server-authoritative and well tested. Its controls are contribution deltas, dated contribution boundaries, and one-time outflow against an owned goal forecast. Its output is a goal projection with deterministic conservative/base/optimistic assumptions. It does not model holdings, security returns, concentration, correlation, drawdown, liquidity, portfolio weights, or a proposed investment exposure.

**Conclusion:** reuse its immutability, hash, freshness, idempotency, and presentation patterns. Do not reuse goal IDs, forecast IDs, scenario bands, or contribution semantics as portfolio-risk identity.

### 3.4 Existing UI portfolio path

The portfolio pages fetch dashboard summary, accounts, and holdings. They calculate display totals, coverage percentages, sorting, and concentration presentation in React. That is acceptable for legacy presentation only where the backend values are already authoritative, but it cannot support UI-11's requirement that hypothetical results, risk metrics, data states, and temporal compatibility be server-owned.

**Conclusion:** UI-11 must consume a dedicated typed API projection and must not extend browser calculations into risk or scenario authority.

## 4. Security Universe and Identity Question

### What securities can currently be considered?

The repository does not expose a verified canonical market-wide security universe for UI-11. UI-09 added bounded, explicit current-only discovery modes, including a separate S&P 500 mode, but that discovery projection is not a general security master or historical market-data authority.

The current portfolio source contains only securities represented in imported/manual holdings. This is sufficient for a current portfolio exposure view, but it is not sufficient for general opportunity or portfolio stress scenarios involving a security not currently held.

Market Brief and recommendation records may contain securities, but using either as the portfolio universe would invert the architecture:

```text
Correct: security source / owned holdings
      -> trusted portfolio baseline
      -> risk/scenario projection

Incorrect: recommendation or presentation brief
      -> inferred portfolio universe
      -> risk result
```

Tickers are display aliases. The UI-11 prerequisite must either connect holdings to the canonical INV-01 security identity source or represent unresolved/unsupported identity explicitly and exclude it from metrics that require resolved identity.

### Identity defects relevant to UI-11

Two related contract families currently exist: `app.investments.contracts.SecurityIdentity` and `app.investments.securities.SecurityIdentity`. The portfolio projection uses the latter and derives IDs from `symbol` plus inferred type. This is a real integration risk, but correcting it would reopen a completed identity boundary. The UI-11 prerequisite should use the already-approved canonical identity contract at its server boundary and record this reconciliation as an adapter requirement, not introduce a third identity model.

## 5. Discovery, Analysis, Recommendation, and Risk Separation

UI-11 is not an extension of UI-09 discovery and is not an extension of INV-09 recommendation.

| Concept | Question answered | Allowed UI-11 relationship |
|---|---|---|
| Discovery | Which securities satisfy an explicit universe/filter? | Optional selector input only |
| Analysis | What do canonical observations and calculations show? | Source of descriptive metrics |
| Portfolio baseline | What owner-scoped positions existed at a declared time? | Required input |
| Risk | What descriptive exposure/risk properties follow from supported data? | New methodology contract required |
| Hypothetical scenario | What changes under explicit bounded assumptions? | New server-owned projection required |
| Recommendation | What action does the intelligence system recommend? | Optional display context only |
| Decision | What did the human record? | Read-only history context only |
| Outcome | What happened after a recommendation/decision? | Not an input to an unapproved hypothetical projection |

No current contract approves a portfolio risk score, VaR, probability, optimizer, target allocation, or “best” security. None should be invented to make the page appear complete.

## 6. Methodology Audit

### Defined and reusable now

The following calculation semantics exist and can be reused only within their declared scopes:

- exact Decimal handling in the Scenario Lab/forecast engine;
- deterministic portfolio total/exposure aggregation over supplied holdings;
- market observation timestamps, hashes, currency, quality, freshness, and adjustment basis;
- technical metrics such as rolling volatility where sufficiently long compatible series exist;
- quant metrics including cumulative return, volatility, maximum drawdown, and optional benchmark calculations;
- explicit zero-price and insufficient-history fail-closed behavior in outcome/quant paths;
- server-owned hashes and methodology/version metadata.

### Not defined for UI-11

The repository does not define an approved method for:

- portfolio volatility or covariance aggregation;
- portfolio drawdown history;
- concentration thresholds as a canonical risk policy;
- liquidity risk or liquidation assumptions;
- currency conversion for mixed-currency positions;
- sector/geography/issuer classification authority;
- stress scenarios or shock magnitudes;
- proposed exposure semantics;
- risk score, risk bands, VaR, expected shortfall, probability, optimizer, or target allocations;
- treatment of stale, partial, unresolved, or unsupported positions in an aggregate;
- portfolio baseline retention and historical replay.

The existing `RiskAssessment` and committee risk role are structured narrative/evidence handoffs, not deterministic portfolio-risk methodology. The existing portfolio page's concentration thresholds are UI presentation rules, not a canonical risk policy.

### Recommended initial methodology posture

Until a product/architecture decision approves more, the first UI-11 slice should be:

- descriptive current-baseline exposure and data-quality presentation;
- deterministic, explicitly bounded hypothetical deltas over a trusted baseline;
- stable ordering and explicit omissions;
- no score, probability, optimizer, target allocation, or execution instruction;
- explicit `available`, `unavailable`, `insufficient_history`, `unsupported`, `stale`, and `incompatible` states.

If portfolio volatility, drawdown, correlation, or stress is required, each must be approved as a separate method with inputs, formula, units, period, data basis, missing-data behavior, version, and fixtures before implementation.

## 7. Metric Availability and Compatibility Matrix

| Metric or view | Existing source | Canonical semantics | Units/basis | Time/known-at | Safe for UI-11 now? |
|---|---|---|---|---|---|
| Position quantity | `Holding.quantity`, `PortfolioPosition.quantity` | Quantity as imported; legacy source | Decimal string in projection, source Float | Import/current row; no immutable observation time | **Current display only** |
| Position market value | `Holding.current_value`, `PortfolioPosition.market_value` | Imported/current value | Currency currently unknown in portfolio projection | Import/current row; no source observation hash | **Current display only; not historical risk authority** |
| Portfolio total value | `build_portfolio_snapshot` | Sum of complete observed values | Currency not established | Caller-supplied `as_of` | **Only as a provisional baseline candidate after adapter hardening** |
| Exposure percentage | `ExposureBucket` | Position value / complete total | Percentage | Same limitations as values | **Provisional descriptive view only** |
| Cost basis | `Holding.cost_basis_total`, cost state | Imported cost basis | Currency not established | No immutable observation timestamp | **Display as explicit state; not risk metric** |
| Price | `MarketObservation` | Observed value with source/hash | Currency plus adjustment basis | `as_of`, `retrieved_at`, `observation_time` | **Yes only with trusted observation source and compatible series** |
| Cumulative return | `quant.calculate_quant_research` | Return over aligned price points | Ratio | Point timestamps/hashes | **Yes for a single security with valid series; portfolio aggregation not defined** |
| Volatility | `technicals` / `quant` | Series-derived volatility | Ratio | Lookback and point hashes | **Single-security descriptive metric only until portfolio method approved** |
| Maximum drawdown | `quant` | Series-derived peak-to-trough metric | Ratio | Aligned point series | **Single-security descriptive metric only until portfolio method approved** |
| Sharpe ratio | `quant` | Return/risk ratio with explicit risk-free input | Ratio | Input series and risk-free basis | **Only when risk-free source and alignment are approved** |
| Benchmark return/beta | `quant`, `outcome_tracking` | Explicit benchmark identity and aligned series | Ratio | Baseline/evaluation or point series | **Potentially reusable with exact compatibility checks** |
| Sector/geography | No verified canonical source in audited path | Undefined | Undefined | Undefined | **Unavailable** |
| Currency-normalized exposure | No authoritative FX adapter identified | Undefined | Mixed currency | Undefined | **Unavailable; fail closed** |
| Liquidity | No canonical liquidity/volume contract in audited path | Undefined | Undefined | Undefined | **Unavailable** |
| Portfolio covariance/correlation | No portfolio aggregation method | Undefined | Ratio/matrix | Undefined | **Unavailable** |
| Portfolio drawdown | No historical portfolio valuation series | Undefined | Ratio | Undefined | **Unavailable** |
| Scenario impact | Goal Scenario Lab only | Goal contribution/outflow, not portfolio exposure | USD monthly projection | Goal forecast baseline | **Unavailable as portfolio impact** |
| Risk score/VaR/optimizer | No approved implementation | Undefined | Undefined | Undefined | **Forbidden until separately approved** |

### Compatibility rules required by the prerequisite

The server must reject or mark unavailable any aggregate that combines:

- different currencies without an authoritative conversion and timestamp;
- incompatible adjustment bases;
- observation periods that do not align;
- observations known after the requested baseline/scenario context;
- stale or invalid source data as if it were current;
- unresolved or unsupported identities where identity-dependent grouping is required;
- quantities and prices from unrelated observation times;
- metrics from different methodology versions when comparability is not guaranteed.

The browser must never decide that incompatible values are comparable.

## 8. Temporal and Provenance Audit

### What is safe

A future risk/scenario contract can preserve the established model:

- `baseline_as_of` for the portfolio snapshot;
- `as_known_at` for information availability;
- `retrieved_at` for source retrieval;
- source/observation IDs and hashes;
- adjustment basis and currency;
- calculation/methodology version;
- input and output hashes;
- freshness/data state;
- explicit evaluation/scenario timestamp.

### Current limitations

The holdings table is a current imported source, not an immutable sequence of portfolio states. The portfolio projection accepts an `as_of` argument but does not prove that each holding was known at that time. Therefore historical portfolio-risk reconstruction is not currently safe.

The implemented baseline can be classified as:

- **Current-only:** imported holdings and current portfolio page values;
- **Point-in-time capable but not connected:** `MarketObservation`, technical, quant, and outcome contracts;
- **Point-in-time capable for a different domain:** forecast/Scenario Lab;
- **Unsafe for historical UI-11 claims:** browser-calculated portfolio history and current values relabeled with past dates;
- **Unknown:** historical portfolio valuation, sector classification, FX, liquidity, and aggregate risk series.

### Required temporal rule

For any UI-11 projection at context time `T`:

```text
source.as_of <= T
source.as_known_at <= T
source.retrieved_at >= source.as_known_at
```

For a historical baseline, every contributing holding valuation and classification must satisfy the same context boundary. If that cannot be proven, return an explicit unavailable/insufficient state rather than substituting current data.

## 9. Ownership and Privacy Audit

### Global data

Potentially global/public inputs include:

- canonical security identity;
- public market observations;
- public fundamental, technical, macro, and quant evidence.

Even public inputs need source, timestamp, freshness, identity, and compatibility validation.

### Owner-specific data

Private inputs include:

- accounts and holdings;
- position quantities, market values, cost basis, and account relationships;
- portfolio baseline and snapshot hash;
- portfolio exposure, concentration, liquidity, and any hypothetical impact;
- personal screening preferences or watch state if added later;
- recommendation/decision/outcome linkage where owner-specific.

The server must resolve owner scope from authentication before lookup and before returning any private context. Cross-owner IDs must return the established non-enumerating not-found/denial behavior. Public security detail must not include account IDs, cost basis, or portfolio weights unless the authenticated owner is authorized for that context.

### Current security posture

Accounts and holdings routes apply owner filters through the local authenticated user. `build_portfolio_snapshot` filters accounts by `user_id` and holdings by those account IDs. The current implementation exposes real HTTP owner-isolation tests for the baseline and on-demand scenario preview; persisted comparison/detail resources are intentionally out of scope.

## 10. Minimum Required Architecture

The smallest safe architecture is:

```text
Canonical security identity + owner holdings
             + trusted point-in-time observations
             + approved classifications/assumptions
                              |
                              v
                 InvestmentPortfolioBaseline/v1
                              |
                              v
             InvestmentRiskScenario/v1 projection
                              |
                              v
                 typed owner-scoped API
                              |
                              v
                  UI-11 read-only presentation
```

### 10.1 Trusted baseline contract

The delivered first slice defines `InvestmentPortfolioBaseline/v1` with the following minimum fields and guarantees:

- stable baseline ID and schema version;
- authenticated owner scope;
- baseline `as_of` and `as_known_at`;
- owner-scoped account/position references;
- canonical security identities and identity states;
- quantity and value with currency and data state;
- source holding/observation IDs and hashes;
- cost-basis state without forcing unknown into zero;
- completeness and omission reasons;
- calculation/methodology version;
- deterministic baseline hash;
- explicit current-only versus historical-capable status;
- provenance closure and freshness;
- no broker/order/execution fields.

A database snapshot table is not automatically required. First determine whether a server-owned, immutable, hash-bound projection can be rebuilt deterministically from the existing source records. If it cannot, authorize additive baseline persistence rather than passing a caller-supplied `as_of` over current holdings.

### 10.2 Risk/scenario contract

The delivered first slice defines a separate `InvestmentRiskScenario/v1` (name subject to ADR approval) containing:

- scenario identity and schema version;
- owner scope and baseline ID/hash;
- selected security or portfolio scope;
- explicit bounded hypothetical inputs;
- input, result, baseline, and source hashes;
- methodology/calculation version;
- metric values only for approved methods;
- unit, currency, period, adjustment basis, and compatibility metadata;
- data states and omission/limitation reasons;
- `as_of`, `as_known_at`, and evaluation timestamp semantics;
- explicit `hypothetical: true` and `predictive: false` markers;
- deterministic result hash;
- no recommendation action, target allocation, order, trade, transfer, or mutation fields.

The delivered first slice is on-demand. Persistence of scenario results remains a separate decision; if added, it must be immutable/versioned and must not be confused with the existing goal Scenario Lab tables.

### 10.3 Application interfaces

At minimum, define interfaces equivalent to:

```text
get_portfolio_baseline(owner_id, as_of_mode/current_context)
get_portfolio_risk(owner_id, baseline_id or current context)
preview_investment_risk_scenario(owner_id, baseline_id, bounded_inputs)
compare_risk_scenarios(owner_id, scenario_ids)   # only if persistence is approved
```

Each method must:

- enforce owner scope before resource disclosure;
- load data through trusted repositories/adapters;
- validate identity, temporal compatibility, currency, adjustment basis, completeness, and hashes;
- return typed read models or sanitized typed failures;
- never accept canonical facts, owner IDs, market values, observations, scores, or result values from the browser.

## 11. API and UI Contract Gate

### API requirements

Possible endpoint shape, pending ADR approval:

- `GET /api/v1/investments/portfolio-risk/baseline`
- `POST /api/v1/investments/portfolio-risk/scenarios/preview`
- `GET /api/v1/investments/portfolio-risk/scenarios/{scenario_id}` only if saved scenarios are authorized

The exact paths must follow repository conventions. Responses must be explicit Pydantic envelopes, never ORM objects or arbitrary JSON. Request bodies may contain only bounded user intent such as selected scope and hypothetical deltas; server-owned baseline, values, hashes, timestamps, and provenance are derived.

### UI requirements after the backend gate

The UI-11 surface should present:

- baseline as-of and current-only/historical capability;
- exposure and data quality;
- approved risk metrics with units and methodology;
- explicit unavailable/insufficient/stale/unsupported states;
- bounded hypothetical input controls;
- prominent `Hypothetical analysis only` and `Not a prediction or execution` labels;
- assumptions, limitations, source/freshness, and table fallback;
- no buy/sell/order/execute/rebalance controls;
- no browser-side financial calculations.

Future UI-11 expansion must not begin from a page mock that invents missing metrics. Any historical or advanced risk contract must be stable first.

## 12. Required Test Plan

### Domain and contract tests

- baseline owner filtering excludes another owner's accounts/holdings;
- canonical security identity and unresolved/unsupported states are preserved;
- missing value, cost basis, currency, and classification remain explicit;
- baseline hash is deterministic and changes when an authoritative input changes;
- current-only baseline cannot be represented as historical without explicit capability state;
- unknown/stale/invalid input fails closed;
- unsupported metrics return typed unavailable states;
- hypothetical input bounds and schema strictness reject unknown fields;
- scenario result is deterministic and marked hypothetical/non-predictive;
- result hash includes baseline hash, inputs, methodology, and source hashes;
- no output contains execution or mutation semantics.

### HTTP/API security tests

- unauthenticated baseline and scenario requests return the established 401;
- owner A cannot read owner B baseline or scenario by ID;
- ID enumeration returns indistinguishable not-found behavior;
- owner A cannot submit a request containing owner B references or client-supplied financial authority;
- malformed/unknown fields are rejected;
- stale baseline hash is rejected;
- future `as_of`/`as_known_at` source is rejected;
- mixed currency and adjustment basis are rejected or explicitly unavailable;
- unresolved identity is excluded from identity-dependent metrics;
- no raw ORM/provider payload or internal exception leaks;
- repeated identical preview requests produce the same result/hash;
- if persistence is approved, unique/idempotency/race behavior is tested;
- scenario preview does not modify Account, Holding, Forecast, Recommendation, Decision, Outcome, or Scenario Lab rows.

### UI/browser tests after API completion

- loading, unavailable, partial, empty, stale, and error states;
- 390, 768, 1024, 1440, and 1728 pixel widths;
- no unintended horizontal overflow;
- keyboard-only access and visible focus;
- Axe serious/critical findings at zero;
- reduced motion and 200% zoom behavior;
- accessible table fallback for every meaningful chart;
- privacy checks that account identifiers/cost basis are not shown in public contexts;
- explicit hypothetical/non-predictive/no-execution copy;
- no broker/order/trade/transfer/rebalance requests or controls.

## 13. Gap Classification

### GREEN — Existing capability

- Owner filtering patterns for accounts/holdings.
- Typed investment contracts and fail-closed data states.
- Point-in-time market observation, technical, quant, outcome, and evidence primitives.
- Deterministic Decimal Scenario Lab engine and immutable-version conventions.
- Existing chart/table/accessibility primitives.
- Existing no-execution and sanitized-error conventions.

### YELLOW — Existing capability requiring a bounded adapter

- Convert owner holdings/accounts into a server-owned baseline projection — **delivered for the current-only slice**.
- Reconcile portfolio position identity with the canonical INV-01 identity boundary — **identity remains explicitly unresolved when no security-master reference exists**.
- Connect market observation series to positions through trusted server adapters for any future historical/advanced metrics.
- Reuse Scenario Lab immutability/hash/freshness conventions without its goal semantics.
- The delivered typed portfolio-risk routes cover the approved current-only scope; future routes require their own contract review.

### ORANGE — Deferred expansion gaps

The following capabilities remain intentionally outside the delivered first slice:

- Approved advanced portfolio-risk methodology;
- historical valuation/replay source;
- covariance/correlation/drawdown/stress semantics;
- classification, FX, and liquidity sources; and
- any decision to persist scenarios.

### RED — Architectural conflicts

- Relabeling goal Scenario Lab results as portfolio risk.
- Computing authoritative risk, stress, exposure impact, or scenario results in React.
- Deriving a security universe from recommendations or Market Brief presentation records.
- Treating ticker symbols as canonical identity.
- Treating missing/stale/unknown values as zero or current values as historical.
- Adding recommendation actions, target allocations, or execution controls to UI-11.
- Reusing goal/forecast `Scenario` identity as investment portfolio-risk identity.

## 14. First-Slice Delivery and Deferred Expansion

The approved first-slice package is complete. Its delivered decisions and artifacts are:

1. Approved methodology: descriptive current-only portfolio baseline plus bounded hypothetical preview.
2. Approved metrics: position count, observed/total value where compatible, per-position exposure where a nonzero compatible total exists, and explicit data-quality states; advanced risk metrics remain unavailable.
3. `InvestmentPortfolioBaseline/v1` is owner-scoped, hash-bound, provenance-bearing, and explicitly current-only.
4. `InvestmentRiskScenario/v1` accepts bounded intent, preserves baseline/source hashes, and marks results hypothetical and non-predictive.
5. Historical portfolio observation/replay is not provided; current holdings are never relabeled as historical.
6. The architecture is recorded in `ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`.
7. Server baseline/preview services, typed APIs, domain/HTTP tests, and browser certification are complete for this scope.

This does not authorize redesigning completed INV phases or expanding unsupported risk semantics.

## 15. Impact on Other Remaining Phases

### INV-12

UI-11 should emit source, methodology, baseline, and result hashes that a future evaluation/replay system can consume. UI-11 does not implement calibration, success claims, replay storage, or retention policy. INV-12 still requires its own evaluation artifact contract and retention/deletion decision.

### UI-12

UI-12 must wait until UI-11 is either implemented and certified or explicitly excluded from the final surface inventory. Its cross-route matrix must include baseline privacy, hypothetical labels, unsupported metrics, no-execution checks, and performance budgets.

### INV-10

No dependency is created by this audit. Durable CIO report archive remains optional and should be implemented only for a concrete consumer.

### UI-09

UI-09 discovery output may be an optional selector source, but UI-11 must remain independent of recommendation authority and must not add risk fields to discovery or recommendation contracts for convenience.

### UI-10

UI-10 may later consume a trusted UI-11 baseline/scenario context only through a separately versioned read-only selector. No UI-10 change is required by this audit.

## 16. Future Expansion Sequence

The delivered current-only slice is complete. Any future UI-11 expansion must proceed as a separately approved contract sequence:

1. Define and approve the additional metric methodology and supported source set.
2. Add or connect historical portfolio observations only where holdings, valuations, identity, currency, and known-at semantics are reconstructable.
3. Add typed server projections and focused temporal, provenance, compatibility, ownership, and no-mutation tests.
4. Add UI only after the expanded backend contract is stable and unsupported states remain explicit.
5. Re-run browser accessibility, privacy, responsiveness, and no-execution certification.

Do not infer historical or advanced risk semantics from the current-only implementation.

## 17. Final Design Verdict

### BOUNDED FIRST SLICE IMPLEMENTED

The accepted UI-11 slice is a current-only, owner-scoped portfolio baseline with descriptive exposure/data-quality metrics and an on-demand bounded hypothetical position-value preview. It deliberately does not claim historical portfolio reconstruction or advanced risk semantics. Unsupported methods remain typed unavailable states. A future expansion requires a separate methodology and source decision.

## Worktree and Safety

The follow-on UI-11 implementation is additive: no schema migration, provider, dependency, or completed investment-phase redesign was introduced. The pre-existing unrelated dirty work remains outside scope and must not be reset, cleaned, staged, or committed.

No broker, order, trade, transfer, rebalancing, portfolio mutation, money movement, autonomous execution, background execution, or browser-side financial authority was introduced.

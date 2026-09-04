# Atlas Investment Intelligence
## Remaining Phases Readiness Audit and Execution Plan**Status:** UI-10 is certified for its original contextual slice plus the approved bounded provider-backed Scout expansion; the bounded UI-11 current-only risk/scenario slice is certified; UI-12 and INV-12 remain gated
 by documented prerequisites
**Audit date:** 2026-09-02
**Scope:** INV-10 extensions, INV-12, UI-10, UI-11, UI-12, and cross-phase prerequisites
**Authority:** Canonical investment contracts, current roadmap/status tracker, ADRs, existing tests, and the repository implementation

## Executive verdict

The repository is ready for a **gated sequence of bounded prerequisite and implementation slices**, but it is not ready to execute every remaining phase as one uninterrupted implementation. UI-10 has now passed its bounded certification gate. The safe remaining order is:

1. preserve the certified UI-09 and UI-10 boundaries;
2. preserve the certified UI-11 current-only baseline and descriptive hypothetical preview; defer historical and advanced portfolio-risk methodology to a separately approved slice;
3. define the INV-12 evaluation/replay artifact and retention boundary;
4. implement INV-12 evaluation, calibration, replay, and retention only after its prerequisite decisions are approved;
5. certify UI-12 across the completed surfaces and approved contracts;
6. add INV-10 archive only if a concrete consumer requires durable CIO reports.

**Do not begin UI-11, UI-12, or INV-12 without completing the phase-specific contract gates below.** The current code contains useful adjacent capabilities, but several required boundaries do not yet exist.

This document is the authoritative audit and execution plan. UI-10 implementation evidence is recorded below; provider-backed research is limited to the separately bounded server-owned Scout path and existing Finnhub/SEC adapters. No broker, execution, or financial-data behavior was added outside those explicit read-only boundaries.

---

## 1. Current status snapshot

| Area | Current status | Audit conclusion |
|---|---|---|
| INV-01–INV-09 | Domain foundations complete | Preserve contracts; use as inputs only |
| INV-HARDEN-01 | Complete | Preserve fail-closed identity, provenance, temporal, and benchmark rules |
| INV-PERSIST-03 | Committed/validated | Trusted persistence boundary is reusable |
| INV-10 | Bounded in-memory CIO projection complete | Archive/delivery/scheduling are not implemented and are not required yet |
| INV-11 | Durable decision/outcome boundary complete | Historical evaluation extensions remain open |
| UI-01–UI-08 | Complete/certified | Do not reopen without a concrete regression |
| UI-09 | Complete for approved bounded scope | Separate current-only portfolio and bounded S&P 500 discovery modes are committed and validated. |
| UI-10 | Complete/certified for bounded read-only Scout scope | Typed context/tool/query boundary, model response citation validation, prompt-injection fencing, refusal/offline handling, HTTP tests, and responsive/accessibility browser evidence are complete. |
| UI-11 | Complete for bounded current-only slice | Server-owned baseline, descriptive metrics, on-demand hypothetical preview, typed API, and browser safeguards are validated; advanced/historical risk remains deferred |
| UI-12 | Not started | Depends on stable UI/API surfaces plus evaluation/retention decisions |
| INV-12 | Not started | Requires an evaluation artifact contract, observation policy, and retention decision |
| INV-10 archive | Not implemented | Keep deferred unless a concrete report/archive consumer requires it |

### Existing tracker/documentation drift

The live tracker and generated handoff must remain aligned with the committed UI-09 and UI-10 evidence. UI-09 is complete for the approved bounded modes, and UI-10 is complete for the bounded read-only contextual Scout scope. Remaining tracker work is governance reconciliation and selection of the next gated UI-11 task.

The worktree contains unrelated dirty backend/UI changes and an untracked historical PERSIST-01 document. They are outside this audit and must remain untouched.

---

## 2. Authoritative existing capabilities and limitations

### 2.1 Canonical investment domain

Existing typed contracts provide:

- canonical security identity and identity states;
- market observations with `observed_at`/`as_known_at` and zero-price safeguards;
- bounded INV-08 committee context, findings, dissent, uncertainty, and evidence;
- INV-09 recommendations with lifecycle, hash, committee linkage, risks, invalidation, and portfolio snapshot linkage;
- INV-11 append-only human decisions;
- optional explicit recommendation-outcome decision linkage;
- immutable persistence projections and owner-scoped retrieval.

These are suitable inputs to later surfaces. Browser state, raw ORM records, provider payloads, legacy goal/forecast models, and Market Brief presentation payloads are not canonical replacements.

### 2.2 Assistant infrastructure

The existing general assistant retains authenticated chat, conversation persistence, streaming, local model selection, and its general financial tool/orchestrator path. UI-10 adds an isolated investment path that does not change general assistant behavior:

- `/api/v1/investments/assistant/{context,tool,query}` accepts typed selectors and bounded questions only;
- `InvestmentRepository` resolves owner-scoped persisted recommendation and committee context;
- `get_investment_context` is the only investment tool and is read-only;
- model output is parsed into `InvestmentAssistantResponse/v1` and citations must match server-resolved hashes;
- context data is explicitly fenced as untrusted data for the model;
- execution intent is refused and unavailable/offline responses are sanitized;
- assistant output cannot create or mutate recommendations, decisions, outcomes, portfolio state, or execution state.

### 2.3 Scenario Lab

Scenario Lab is a strong server-owned, Decimal-safe, goal-scoped hypothetical projection vertical slice. It has:

- trusted Finlynq projection-state loading;
- immutable versioned scenarios;
- owner scope;
- explicit baseline forecast linkage;
- deterministic bands rather than probabilities;
- idempotency and comparison rules;
- no execution behavior.

It does **not** by itself provide:

- portfolio-level risk measures;
- security-level or portfolio-level stress semantics;
- concentration/liquidity/drawdown projection contract for arbitrary investment scenarios;
- a UI-11-specific baseline snapshot and hypothetical-impact contract;
- a portfolio risk methodology or scenario taxonomy.

Therefore UI-11 may reuse Scenario Lab infrastructure and shared presentation primitives, but must not label existing goal projections as portfolio risk or silently derive investment impacts in React.

### 2.4 CIO reporting

`CIOReport/v1` is a deterministic, structured, in-memory projection. It already preserves report identity, period, as-of, portfolio snapshot hash, committee summaries, recommendation summaries, evidence, quality, methodology, input hash, and report hash. It intentionally has no persistence, route, scheduler, delivery, or narrative LLM boundary.

This is sufficient for consumers that can generate reports on demand. Durable archive is a separate additive decision and must not be introduced merely because UI-12 mentions archive.

### 2.5 Outcome and observation infrastructure

INV-11 outcome tracking supports frozen observations, explicit observation hashes, benchmark identities, point-in-time filtering, zero-price fail-closed behavior, and recommendation-level evaluation without a human decision. It does not yet constitute a full INV-12 calibration/replay/retention product contract.

---

## 3. Cross-phase invariants

Every remaining phase must preserve these rules:

1. **Server authority:** the browser supplies intent and bounded selectors only; it never supplies canonical investment facts, hashes, owners, provenance, observations, scores, outcomes, or recommendation payloads.
2. **Owner isolation:** owner scope is resolved from authentication before existence checks or disclosure. Public/global data and private portfolio/recommendation context remain separate.
3. **Canonical identity:** security IDs, recommendation IDs, committee IDs, decision IDs, outcome IDs, report IDs, and evaluation IDs are stable typed identities. Tickers are aliases/display values only.
4. **Point-in-time integrity:** every observation-bearing projection preserves `as_of`, `as_known_at`, retrieval time, freshness, revision/methodology metadata, and adjustment basis where applicable.
5. **Fail closed:** unknown, stale, unsupported, insufficient, invalid, incompatible, zero-price, and missing values are explicit states, never fake zeros or current-time substitutions.
6. **Immutability:** historical reports, recommendations, decisions, outcomes, evidence, and evaluation artifacts are append-only/versioned. Corrections create new records.
7. **Separation of concepts:** discovery, analysis, committee, recommendation, decision, outcome, assistant explanation, scenario projection, and evaluation remain distinct.
8. **No execution:** no broker, order, trade, rebalance, transfer, money movement, portfolio mutation, autonomous scheduling, or background execution path.
9. **Untrusted text:** external/provider/model text is data, not instructions. Prompt injection cannot alter tools, ownership, or canonical state.
10. **Observability:** failures are sanitized for users and diagnosable through bounded internal reason codes without sensitive payload logging.

---

## 4. Phase-by-phase audit

## INV-10 — CIO reporting extensions

### Current capability

`generate_cio_report(...)` assembles validated portfolio, committee, recommendation, and evidence projections deterministically. Report hashes are reproducible and timestamps are explicit.

### Missing prerequisites

- No durable report identity/version repository.
- No typed authenticated report read route.
- No retention/archive policy for reports.
- No approved delivery/scheduling contract.
- No durable narrative contract, if prose is later required.

### Decision

**Not required now unless a concrete UI/report consumer requires it.** UI-10 can consume structured context directly; UI-12 can certify current report generation without an archive. Do not create speculative INV-10 persistence.

### If later authorized

Add a narrowly scoped immutable report repository and typed read API. Persist input references/hashes, report hash, owner, period, as-of, methodology, quality, and evidence IDs. Do not accept client-authored report facts. Scheduling/delivery remain separate decisions.

### Tests required

Deterministic replay, owner isolation, future-input rejection, evidence closure, immutable identity collision, sanitized corruption behavior, and report/API response typing.

---

## INV-12 — Evaluation, calibration, replay, and retention

### Current capability

INV-11 can calculate bounded outcomes from frozen observations. Existing forecast/scenario persistence has append-only/versioned patterns and a known external multi-user retention/deletion blocker.

### Missing canonical contract

INV-12 needs an explicit evaluation artifact, not merely an outcome row. The minimum contract must identify:

- evaluation ID and schema version;
- owner scope;
- recommendation identity and immutable recommendation hash/version;
- optional decision identity/hash;
- outcome identity/hash or frozen observation references;
- evaluation methodology/version;
- evaluation window and evaluation `as_of`/`as_known_at`;
- benchmark identity and benchmark observation hashes where applicable;
- result state, including insufficient/unavailable/incompatible;
- deterministic input hash and evaluation hash;
- calibration population/cohort definition if calibration is included;
- replay parameters and source snapshot IDs;
- provenance and creation timestamp.

### Retention prerequisite

The repository has an open product-security blocker: no approved retention and user-deletion policy exists for immutable forecast history. INV-12 cannot claim production-ready multi-user retention/deletion semantics until the policy is approved. Personal-use implementation may remain bounded/default-off, but the policy boundary must be explicit.

### Recommended INV-12 slices

1. **Evaluation contract and replay fixture slice:** define artifact semantics over existing immutable recommendations/outcomes/observations; no UI.
2. **Evaluation repository/read API:** owner-scoped immutable artifacts, deterministic replay, idempotency, no mutation of source history.
3. **Calibration slice:** only after the product defines a statistically valid cohort, minimum sample rules, missing-data policy, and metric definitions. Do not infer calibration from a few fixtures.
4. **Retention/deletion slice:** only after product-security approval; define legal hold, account deletion, backup deletion, and immutable-history handling.
5. **Read-only evaluation UI/API consumption:** can be consumed by UI-12 after contracts are stable.

### INV-12 blockers

- approved evaluation/calibration definitions;
- explicit retention/deletion policy;
- decision on whether evaluation is personal-use only or multi-user production;
- benchmark and cohort methodology for calibration.

### Safety

Evaluation is retrospective analysis only. It must not change recommendations, decisions, portfolio state, or execution.

---

## UI-10 — Contextual investment assistant

### Current capability

The general authenticated Scout remains unchanged. The isolated UI-10 investment assistant boundary is implemented and certified for the bounded read-only contextual Scout scope.

### Implemented UI-10 contract

`InvestmentAssistantContext/v1`, `InvestmentAssistantQueryRequest/v1`, and `InvestmentAssistantResponse/v1` are implemented with:

**Context input (server-resolved):**

- owner scope from authentication;
- exactly one persisted recommendation or committee-finding selector per request in the certified first slice;
- discovery, security, portfolio, decision, outcome, and report selectors are schema-compatible but intentionally resolve to an explicit unavailable state until dedicated server-owned adapters exist;
- server-resolved canonical projections only;
- bounded context size and evidence limits;
- context as-of and server-resolved source snapshot hashes;
- explicit unavailable/partial states;
- internal owner scope excluded from the public response projection.

**Response:**

- response ID and schema version;
- answer sections separated into facts, calculations, interpretations, assumptions, limitations, and refusals;
- citation IDs that resolve to supplied server-owned evidence/context hashes;
- optional source type and `as_of` metadata on response citations;
- no new authoritative recommendation/decision/outcome fields;
- sanitized error/offline state.

### Implemented assistant boundary

- tool registry allowlist contains read-only investment context tools only;
- tool parameters are typed and bounded;
- ownership is resolved server-side before lookup;
- no tool can create or mutate investment records;
- external text is marked untrusted and cannot provide instructions;
- model output is validated and citation-checked before response;
- no claim is presented as fact without a source or explicit uncertainty label.

### UI-10 completed slices

1. Context resolver and typed schemas.
2. Read-only investment tool allowlist and citation validator.
3. Authenticated API endpoint, error/offline contracts, and adversarial tests.
4. Contextual Scout page with server-owned selector flow.
5. Assistant response rendering with typed sections and citations.
6. Browser accessibility/privacy/no-execution certification.

### UI-10 tests

Prompt injection in evidence/provider/model text; citation mismatch; invented-number rejection; cross-owner selector access; malformed context; oversized context; unavailable source; model offline; deterministic tool authorization; no mutation; no execution vocabulary/capability.

### UI-10 current implementation status

UI-10 is certified for the bounded read-only contextual Scout scope without changing general Scout. `InvestmentAssistantContext/v1`, `InvestmentAssistantQueryRequest/v1`, an allowlisted `get_investment_context` tool, typed `InvestmentAssistantResponse/v1`, server-side citation validation, explicit untrusted-data prompt fencing, execution-intent refusal, sanitized offline handling, and `/api/v1/investments/assistant/{context,tool,query}` are implemented. The contextual Scout page is available at `/investments/assistant`.

The approved expansion adds a separate provider-backed research boundary: `InvestmentScoutResearchRequest/v1`, `InvestmentScoutSource/v1`, `InvestmentScoutClaim/v1`, `InvestmentScoutResearchResult/v1`, and `InvestmentScoutRunSummary/v1`; authenticated routes at `/api/v1/investments/scout/research`, `/api/v1/investments/scout/runs`, and `/api/v1/investments/scout/runs/{run_id}`; an additive immutable `investment_scout_runs` repository model; and the `/investments/scout` UI. The expansion reuses the server-only Finnhub and SEC normalized adapters, resolves security identity only from an authenticated owner's held canonical security (including when a recommendation or committee selector points to it), strips credential-bearing source query parameters, preserves source URL/title/publisher/publication/retrieval metadata when available, links deterministic claims to source IDs, rejects future timestamps, persists owner-scoped results, and leaves the existing assistant route unchanged. Recommendation/committee selectors do not bypass the held-security requirement.

Certification evidence includes a real persisted-recommendation model fixture with a valid citation, fail-closed unknown-citation handling, unavailable-context refusal before model invocation, execution-intent refusal, server-derived response identity, internal owner-scope exclusion, strict one-selector validation, typed evidence packet projection, 25 focused UI-10 backend tests, TypeScript validation, one focused UI test, and a Playwright browser test covering accessibility, responsive no-overflow behavior, privacy/no-enumeration surface, and absence of broker/order/trade/transfer/rebalance requests. The browser test uses the repository's Axe dependency and the fresh UI dev server. The provider-backed Scout expansion also has a dedicated focused page test and migration/API/domain evidence; it is included in the UI-12 route inventory as a read-only route.

### UI-10 limitations

The original contextual assistant boundary intentionally accepts exactly one selector and resolves persisted recommendation/committee context. The provider-backed expansion accepts one recommendation, committee-finding, or owner-authorized held-security selector; discovery-candidate research is rejected until a dedicated server-owned adapter exists. There is no unrestricted web search, arbitrary URL retrieval, general crawler, private portfolio-fact prompt context, numeric source-quality score, or third-party provider beyond the bounded existing Finnhub/SEC adapters. Recommendation and committee selectors still require the resolved security to be present in the authenticated owner's holdings; they are not independent security-master lookups. Historical source reconstruction remains unavailable; results are current-context only. Provider records that fail normalized timestamp, URL, or schema validation are omitted or cause an explicit unavailable/partial result. The citation projection preserves source URL/title/publisher/publication/retrieval metadata only when supplied by a validated provider record; it does not claim that missing metadata exists. Model output is accepted only when it matches the typed response contract and citations resolve to hashes in the server-resolved context; internal owner scope is excluded from public projections. UI-10 does not create recommendations, decisions, outcomes, portfolio state, or execution actions.

---

## UI-11 — Risk and scenario presentation

### Current capability

UI-11 now has a separate server-owned current-only portfolio baseline and on-demand descriptive hypothetical position-value preview. Existing Scenario Lab remains authoritative only for goal-scoped contribution/outflow scenarios and is not reused as portfolio-risk identity.

### Implemented first-slice contract

The accepted `InvestmentRiskScenario/v1` contract is separate from recommendations and goal scenarios. It contains:

- scenario ID/version and owner;
- baseline portfolio snapshot ID/hash and `as_of`;
- selected security/portfolio scope;
- explicitly bounded hypothetical assumption(s);
- methodology/calculation version;
- result metrics only from canonical supported risk contracts;
- data states and limitations;
- provenance and source observation hashes;
- deterministic result/input hashes;
- explicit hypothetical/non-predictive labels;
- no execution instructions or target allocations.

### Methodology boundary

The certified first slice supports only current-only position count, observed value, compatible single-currency total/exposure data, data-quality states, and bounded position-value deltas. Any future metric needs canonical meaning, units, period, currency, adjustment basis, observation availability, and compatibility rules. A risk score, probability, VaR, optimizer, or “recommended allocation” remains deferred.

### Safe reuse

Reuse existing Scenario Lab calculation/persistence conventions where applicable, but do not reuse its goal IDs or forecast semantics as portfolio risk identity. If UI-11 only needs existing Scenario Lab display, keep it explicitly goal-scoped and label it accordingly; that would be a limited UI-11 integration, not full investment risk delivery.

### UI-11 implementation slices

1. Risk/scenario methodology and contract ADR: complete for the approved first slice.
2. Trusted current-only baseline portfolio projection: complete.
3. Pure deterministic server-side projection and fail-closed metric states: complete.
4. Immutable saved/read projection: deferred because previews are on-demand and non-persistent.
5. Typed API and owner/temporal/no-mutation tests: complete for the bounded scope.
6. UI risk/scenario view with explicit hypothetical labels and table fallback: complete for the bounded scope.

### UI-11 limitations

The certified first slice supports only current-only owner-scoped value/data-quality metrics and bounded position-value deltas. Historical portfolio reconstruction, advanced aggregate risk metrics, FX normalization, classifications, liquidity, and persisted scenarios remain unavailable until separately specified and sourced.

---

## UI-12 — Integration hardening and trust certification

### Current capability

The repository has broad frontend/backend tests, Playwright coverage, Axe usage, typed investment persistence/discovery APIs, Scenario Lab, assistant, and market intelligence surfaces. UI-12 is a certification phase, not a new catch-all feature bucket.

### Required prerequisites

- UI-08/09 status and contracts reconciled in tracker;
- stable UI-10 contracts and completed or explicitly deferred assistant integration;
- stable UI-11 scope and either completed risk contract or an explicit exclusion;
- decision on INV-10 archive requirement;
- INV-12 evaluation/retention status and production-use boundaries;
- clean route inventory and feature flags;
- test data/privacy matrix for multiple owners and unavailable providers;
- performance budgets and browser support matrix.

### Certification matrix

**Trust and security**

- authentication and owner isolation on every investment route;
- non-enumerating not-found behavior;
- no raw ORM/provider payload leakage;
- no browser financial authority;
- prompt injection and untrusted-text handling;
- no execution imports, routes, vocabulary, or controls.

**Temporal/provenance**

- as-of/known-at rendering and API preservation;
- future-data rejection;
- evidence closure;
- methodology/version visibility;
- stale/insufficient/unsupported states;
- adjustment-basis/currency compatibility.

**Functional**

- discovery, recommendation, committee, evidence, decisions, outcomes, assistant, scenarios, and reports compose without semantic inversion;
- decision and outcome histories remain append-only;
- evaluation replay reproduces hashes where implemented;
- route failures have typed/sanitized recovery states.

**Accessibility/responsiveness**

- Playwright at 390, 768, 1024, 1440, and 1728 widths;
- keyboard-only flow and visible focus;
- Axe serious/critical zero;
- reduced-motion behavior;
- dialog/drawer focus management;
- zoom/text scaling and table fallback;
- no horizontal overflow except intentional bounded data tables.

**Performance/operations**

- route load and interaction budgets;
- bounded payload/context sizes;
- no unbounded API queries;
- no unnecessary provider calls;
- offline/default-off behavior;
- source freshness and operational error observability;
- build/type/lint/test evidence.

UI-12 must not be marked complete if it merely passes a happy-path screenshot. It requires a documented evidence matrix and explicit unresolved limitations.

---

## 5. Dependency graph and recommended sequencing

```text
Tracker reconciliation / UI-09 closure
              ↓
UI-10 context contract + read-only tools
              ↓
UI-10 assistant surface certification
              ↓
UI-11 risk methodology + portfolio baseline contract
              ↓
UI-11 server projection + UI certification
              ↓
INV-12 evaluation/replay contract
              ↓
INV-12 retention/calibration decisions and implementation
              ↓
Optional INV-10 archive (only if required)
              ↓
UI-12 cross-route certification
```

### Why this order

- UI-10 can be bounded against already-stable INV-08/09/11 data, but needs its own context boundary.
- UI-11 cannot safely be completed from current holdings/Scenario Lab alone because risk/scenario semantics are not defined.
- INV-12 should follow stable outcome history and before UI-12 certification because evaluation metadata affects trust reporting.
- INV-10 archive is optional and should not delay the rest unless a required consumer is identified.
- UI-12 must certify actual final surfaces, not speculative future APIs.

---

## 6. Exact next bounded tasks

### Task A — Governance reconciliation

- reconcile UI-09 tracker status and stale blocker;
- record commit evidence `db69bf3`;
- preserve unrelated worktree files;
- run tracker validation/render and handoff check.

### Task B — UI-10 architectural prerequisite

- write an ADR or phase plan for `InvestmentAssistantContext/v1` and response/citation semantics;
- inventory allowed read-only tools and selectors;
- define owner, temporal, provenance, context-size, and offline behavior;
- add contract tests only; no UI or model integration yet.

### Task C — UI-10 backend

- implement context resolver, typed API, citation validator, and read-only tool boundary;
- add adversarial HTTP tests;
- prove no recommendation/decision/outcome mutation.

### Task D — UI-10 UI

- add context launchers and cited response rendering;
- add loading, offline, unavailable, partial, refusal, and error states;
- run component/browser/accessibility/privacy tests.

### Task E — UI-11 design gate

- define supported risk/scenario semantics and metrics from existing canonical sources;
- decide whether the first slice is goal Scenario Lab integration, portfolio risk presentation, or both explicitly separated;
- reject unsupported metrics rather than invent them.

### Task F — UI-11 implementation

- implement only the approved contract and server-owned projection;
- add owner/temporal/provenance/no-mutation tests;
- build UI with hypothetical labels and accessible tabular fallback.

### Task G — INV-12 design and foundation

- approve evaluation artifact, replay, calibration, and retention definitions;
- implement evaluation/replay over immutable sources;
- defer calibration and deletion enforcement until sample/policy decisions are approved.

### Task H — Optional INV-10 archive decision

- make a product decision only if a concrete report history consumer requires archive;
- otherwise document INV-10 as bounded complete/deferred extensions.

### Task I — UI-12 certification

- freeze route/contract inventory;
- run cross-route test matrix and performance/accessibility/privacy checks;
- publish evidence and limitations;
- certify only after all blocking findings are closed or explicitly excluded.

---

## 7. Required decisions before implementation

The following are the only product/architecture decisions not safely inferable from current code:

1. **UI-10 assistant scope:** recommendation/committee context only, or also discovery/security/portfolio context in the first slice?
2. **UI-10 model policy:** local Ollama only for the first slice, or a provider-neutral adapter contract with local implementation?
3. **UI-11 first slice:** goal-scoped Scenario Lab integration, dedicated portfolio risk projection, or two explicitly separated surfaces?
4. **UI-11 supported metrics:** which already-defined metrics are required for the first release?
5. **INV-12 rollout scope:** personal-use/default-off foundation now, or wait for multi-user retention/deletion policy?
6. **INV-10 archive:** required for a concrete consumer, or explicitly deferred?
7. **UI-12 completion boundary:** certify only implemented surfaces, or require INV-12 and all optional archives first?

Recommended defaults are:

- UI-10: recommendation/committee/evidence context first, local model through a provider-neutral read-only adapter;
- UI-11: explicitly labeled goal Scenario Lab integration first, with portfolio risk deferred until methodology exists;
- INV-12: personal-use/default-off evaluation/replay foundation, calibration and deletion enforcement gated;
- INV-10 archive: defer;
- UI-12: certify implemented surfaces and explicitly list deferred capabilities.

---

## 8. Validation and evidence requirements

Every implementation slice must run the narrowest strong evidence set plus regressions:

- Python compilation/imports;
- focused domain/service/API tests;
- real HTTP boundary tests;
- UI unit tests and TypeScript;
- Playwright at required widths;
- Axe serious/critical scan;
- migration one-head/import/round-trip checks if schema changes;
- execution-boundary scan;
- `git diff --check`;
- staged ownership review;
- tracker/handoff validation when status changes.

Tests must use isolated synthetic data and must not call production providers or mutate personal financial data. Existing unrelated failures must be reported, not repaired in-scope.

---

## 9. Safety and rollback

No remaining phase authorizes execution. All new routes/features must be feature-gated where appropriate. Rollback means disabling the feature/read route or reverting a new immutable version, never deleting or rewriting historical recommendations, decisions, outcomes, reports, or evaluations.

External multi-user rollout remains blocked by the existing retention/deletion policy risk. This does not block bounded personal-use planning or default-off foundation work, but it must not be silently reclassified.

---

## 10. Final verdict

**READY WITH PREREQUISITES**

The repository has enough stable foundations to proceed, but only through the bounded sequence above. The immediate prerequisite is governance reconciliation followed by the UI-10 context-contract design gate. UI-11 requires a separate methodology decision. INV-12 requires an evaluation/retention decision. UI-12 is last and must certify actual implemented surfaces, not planned functionality.

### Do not start yet

- UI-11 portfolio risk implementation;
- calibration claims;
- durable CIO report archive;
- multi-user retention/deletion enforcement;
- any execution or autonomous investment behavior.

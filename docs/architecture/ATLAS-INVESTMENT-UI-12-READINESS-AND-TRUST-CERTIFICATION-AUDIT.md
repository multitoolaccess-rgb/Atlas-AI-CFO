# Atlas UI-12 Integration Hardening and Trust Certification Audit

**Status:** `CERTIFIED 2026-09-04 FOR THE DEFINED PERSONAL-USE READ-ONLY EXPERIENCE (eleven routes, incl. /portfolio)`
**Audit date:** 2026-09-03
**Audit scope:** Cross-route trust, privacy, accessibility, performance, provenance, recovery, and execution-boundary certification
**Audit authority:** Implemented Atlas investment surfaces, typed investment contracts, existing focused tests, canonical project status, and the repository maintenance policy
**Assumption:** UI-12 is a certification phase over implemented or locked surfaces, not a new feature bucket.
**Execution record:** The coordinated browser matrix passed for the full eleven-route read-only set including `/portfolio` after the 2026-09-04 closure tranche (GAP-10 responsive hero grid, GAP-11 manage-mode mutation gating, GAP-12 server valuation projection, GAP-13 populated single-owner proof, GAP-14 interaction CPU budget, GAP-17 migration-head hygiene, GAP-19 lint verified clean). INV-12 is complete and certified; the optional CIO archive is deferred by decision D-9; the external multi-user retention/deletion blocker remains open and out of scope for personal use (AGENTS.md).

---

## 1. Audit objective

This audit answers a single question: can UI-12 be certified as an integration-hardening and trust-review step today, or is it blocked by missing backend contracts, missing browser evidence, or missing policy decisions?

The answer is **certified as of 2026-09-04 for the defined personal-use read-only experience**. The repository has a frozen surface inventory, explicit performance/payload/interaction budgets, a coordinated browser matrix over eleven routes (including `/portfolio`), a populated single-owner data proof, and zero serious/critical accessibility violations. INV-12 evaluation/replay/retention is complete and certified; the CIO archive is deferred by decision D-9; multi-user retention/deletion remains a separately recorded, out-of-scope blocker.

This document is primarily a readiness audit and execution-plan gate. The current bounded execution also includes one localized responsive correction and its certification evidence; it does not redesign the investment architecture or add a new financial capability.

---

## 2. Scope boundary

Included in this audit:

- current Atlas investment UI surfaces that are or will be part of the final experience
- the backend contracts those surfaces depend on
- the focused tests that prove each surface's safety boundary
- the browser evidence already captured for those surfaces
- the policy issues that limit production rollout

Excluded from this audit:

- implementing new UI pages or routes
- implementing new backend persistence or APIs
- inventing new financial semantics
- embedding execution, broker, order, trade, transfer, rebalance, or money-movement behavior
- changing UI-08, UI-09, UI-10, or UI-11 certified behavior
- deciding claims about historical or advanced portfolio risk beyond what UI-11 already admits

---

## 3. Current surface inventory

The repository currently owns these investment-relevant surfaces and access paths:

| Surface | Route | Current status | Primary contract/product boundary |
|---|---|---|---|
| Investment Command Center | `/investments` | Implemented | Navigation anchor only; no new financial authority |
| Investment Discovery | `/investments/discovery` | Implemented, bounded current-only + S&P 500 only | Explicit current-only universe, stable ordering, no discovery score |
| Investment Brief | `/investments/brief` | UI implemented; required backend read must be available for real certification | Server-owned brief envelope, coverage, freshness, warnings |
| Recommendation Review | `/investments/recommendations` | Implemented | Recommendation lifecycle, committee/evidence/decision/outcome reads, decision precondition |
| Investment Scout | `/investments/assistant` | Implemented; certified for bounded read-only contextual Scout | InvestmentAssistantContext/v1, InvestmentAssistantQueryRequest/v1, InvestmentAssistantResponse/v1 |
| Provider-backed Investment Scout | `/investments/scout` | Implemented; bounded provider-backed current-context research | InvestmentScoutResearchRequest/v1, InvestmentScoutSource/v1, InvestmentScoutClaim/v1, InvestmentScoutResearchResult/v1 |
| Scenario Lab | `/scenario-lab` | Implemented; certified for goal-scoped projection | goal-scoped scenario projections; not portfolio risk |
| Decisions | `/decisions` | Implemented; recommendation review and decision journal | Decision journal, outcomes, recommendation linkage |
| Market Intelligence | `/market-intelligence` | Implemented | Market brief/pulse/archive patterns |
| Portfolio | `/portfolio` | Implemented; certified for UI-12 read-only review (mutation controls gated behind manage mode) | Current holdings/portfolio view; server-owned valuation projection; read-only by default with manage mode for data entry |
| Decisions tab | `/decisions` with `/decisions?view=journal` and `/decisions?view=outcomes` | Implemented enough for UI-10 consumption and UI-12 navigation review | Append-only decisions and outcomes |

Navigation contract:

- `informationArchitecture.ts` currently defines the activated destination set and the compatibility redirects
- the activated Intelligence branch currently contains Decisions, Market Intelligence, and Scenario Lab
- the Command Center surfaces list discovery, recommendation review, and the current-only risk/scenario view as explicit destination cards

---

## 4. Backend contract inventory

The implemented backend relationships relevant to UI-12 include:

| Contract area | Implementation | What UI-12 must assume or verify |
|---|---|---|
| Investment persistence reads | Owner-scoped recommendation, committee finding, evidence, decisions, outcomes | Must prove owner isolation, non-enumerating not-found, and no raw-ORM leakage |
| Investment discovery reads | Server-owned current-only portfolio and bounded S&P 500 projection | Must prove discovery is descriptive, current-only, and not recommendation authority |
| Investment assistant context and query | Scoped read-only resolver and typed response contract | Must prove read-only boundary, citation validation, prompt-injection fencing, refusal/offline handling |
| Portfolio risk baseline and preview | UI-11 current-only baseline and on-demand hypothetical preview | Must prove current-only limitation, fail-closed data/identity states, no mutation, no advanced metrics claim |
| Scenario Lab | Goal-scoped deterministic projection | Must treat as goal projection only; must not be presented as portfolio risk |
| CIO reporting | Deterministic structured report projection | Must verify whether a durable report archive UI is required or deferred |
| Outcome tracking | Outcome evaluation/frozen-observation constructs | Must be treated as an input to INV-12, not full evaluation/replay/retention |

---

## 5. Browser and trust evidence inventory

The repository now has a coordinated UI-12 browser evidence pass for the bounded read-only set. The evidence is intentionally split between degraded-mode trust checks and hermetic live-stack startup/route checks.

### Already covered at surface level

- Investment Scout: reachable, visible read-only boundary text, no execution vocabulary request, harness Axe scan, and responsive check at 390px
- Investment Risk: width suite at 390/768/1024/1440/1728, Axe scan for serious/critical, keyboard interaction, privacy/negative assertion for account:1 and brokerage, no-execution request scan
- Investment Discovery: width suite at 390/768/1440, Axe scan, accessible controls, no horizontal-overflow assertion beyond a generous tolerance
- Scenario Lab: generated/reloaded/compared/archived journey, disabled/missing-baseline/unexpected failure recovery, keyboard and responsive checks, no local calculation claim

### Existing evidence outside the coordinated UI-12 set

- `EvidenceDrawer`: contains an explicit no-execution button assertion in its current test
- Market Intelligence header responsiveness: the expanded UI-12 matrix found a 1024px overflow caused by the desktop action cluster; the layout breakpoint was moved to `xl` without changing data or interaction semantics
- Existing per-surface tests for Command Center, Recommendation Review, Brief, Decisions, Market Intelligence, and Portfolio remain useful supporting evidence, but are not substitutes for the coordinated UI-12 matrix

### What UI-12 should treat as open evidence after implementation

- cross-route privacy assertions for cost basis, account identifiers, and portfolio weights in all contexts where they could leak
- populated owner-data verification for every backend-dependent route in the certified set
- explicit handling of every implemented surface's loading, empty, unavailable, stale, partial, incompatible, archived, and error states
- measured CPU budgets during realistic interactions; the current matrix measures route-load and response-size budgets only

### Coordinated UI-12 matrix evidence

The UI-12-owned test `ui/__tests__/e2e/ui12-trust-certification.spec.ts` covers the following bounded certifiable set at `/investments`, `/investments/discovery`, `/investments/brief`, `/investments/recommendations`, `/investments/assistant`, `/investments/scout`, `/investments/risk`, `/scenario-lab`, `/decisions`, and `/market-intelligence`:

- 2 Playwright tests passed in the route-mocked degraded-mode run.
- The same 2 tests passed in the hermetic live-stack run with isolated SQLite, Finlynq, Rules Service, and Next.js startup.
- The provider-backed `/investments/scout` route is included in both ten-route loops; the harness does not call external providers.
- The provider-backed `/investments/scout` page is included in both coordinated route loops; provider calls remain mocked/unavailable in the certification harness.
- The matrix verifies 390px recovery rendering, keyboard reachability, reduced-motion preference, serious/critical Axe violations equal to zero, sensitive-text redaction checks, absence of execution controls and request URLs, no horizontal overflow, route-load time under 10 seconds, and API responses under 512 KiB.
- The supported width sweep verifies all eleven included read-only routes (including `/portfolio` after the GAP-10 remediation) at 390, 768, 1024, 1440, and 1728 pixels, plus the per-route interaction CPU budget (GAP-14).

The `/portfolio` route was excluded from earlier runs after inspection measured `scrollWidth=407` against a `390px` viewport (GAP-10). The 390px overflow was caused by the non-responsive `HeroSummary` stat-card grid; it is fixed and the route now passes the full width sweep.

---

## 6. Findings

### 6.1 Implemented and safe enough to certify later if dependencies are resolved

- UI-02-style investment navigation anchor exists and is explicit
- UI-09 discovery, UI-10 Scout, and UI-11 risk/scenario already have their bounded localized certification evidence
- Recommendation review, decision journal, outcome reads, and Scenario Lab already exist as owned surfaces
- Trust/privacy-centric assertions already exist in some UI tests and browser specs

### 6.2 Partially verified, not yet sufficient for UI-12 certification

- Market Intelligence and Brief have both isolated route tests and coordinated degraded/live-stack route evidence; populated owner-data proof remains a separate open item
- The coordinated matrix now covers privacy text, execution controls/requests, keyboard reachability, reduced motion, overflow, and serious/critical accessibility findings for the ten-route read-only set
- CPU interaction budgets remain unmeasured; route-load and response-payload budgets are now explicit and covered

### 6.3 Still pending dependency boundaries

- INV-12 evaluation/calibration/replay/retention is not started
- Any durable CIO report archive UI is still optional/deferred unless a concrete consumer is identified
- UI-11 advanced/historical portfolio risk is still unavailable
- UI-10 discovery/security/portfolio adapters remain explicit limited states until dedicated server-owned adapters exist

### 6.4 Policy blockers that UI-12 cannot close

- external multi-user production enablement is blocked until an approved retention and user-deletion policy exists for immutable forecast history
- personal-use/runtime UI certification may still proceed for implemented surfaces, but it must not claim multi-user production readiness
- no UI-12 certification should ever imply execution, brokerage, or money movement capability

---

## 7. Prerequisites and blockers

### Hard prerequisites for UI-12 execution

1. A stable final investment surface inventory with confirmed activation states in `informationArchitecture.ts`
2. Confirmed backend ownership for every route the UI surfaces consume
3. Confirmed privacy scope for each surface: what is public, what is owner-only, what is redacted, what must never appear
4. A written certification matrix with pass/fail criteria for trust, temporal/provenance, privacy, accessibility, responsiveness, recovery, performance, and no-execution behavior
5. Enough backend and browser evidence to run that matrix without inventing tests for gaps

### Blocks that prevented UI-12 certification — all resolved or explicitly out of scope (2026-09-04 closure tranche)

1. INV-12 evaluation/replay/retention — **RESOLVED**: INV-12 complete and certified (engine, three immutable stores, read API, D-8 closed for the personal boundary).
2. `/portfolio` 390px overflow and mutation scope — **RESOLVED**: responsive hero grid (GAP-10), manage-mode gating (GAP-11), server valuation projection (GAP-12); the route is now in the certifiable set.
3. Populated owner-data proof — **RESOLVED**: `ui12-populated-owner.spec.ts` seeds single-owner data and proves every certified route renders it at 390px (GAP-13).
4. CPU interaction budget — **RESOLVED**: long-task count/total-ms assertions per route in the trust spec (GAP-14).
5. Optional CIO archive — **RESOLVED by decision D-9**: deferred, not required without a consumer.
6. External multi-user retention/deletion policy — remains **OPEN** as a separate blocker, explicitly out of scope for the personal single-user boundary (AGENTS.md); UI-12 personal-use certification does not claim multi-user readiness.

### What must not be faked

- URL existence alone must not be treated as certification
- Per-surface isolated assertions alone must not be treated as a consolidated cross-route pass
- Mocked UI behavior must not be treated as proof of backend behavior
- Absence of execution vocabulary in one test file must not be treated as a full execution-boundary certification

---

## 8. Recommended execution sequence

### Step 1 — Freeze the final surface inventory

Confirm the final activated destinations and the exact routes each UI-12 certification pass must cover. Record the consolidated list, including:

- `/investments`
- `/investments/discovery`
- `/investments/brief`
- `/investments/recommendations`
- `/investments/assistant`
- `/investments/risk`
- `/scenario-lab`
- `/decisions`
- `/market-intelligence`
- `/portfolio`

Record which surfaces are currently implemented, which are implemented-but-behind-a-contract-availability requirement, and which are deferred.

### Step 2 — Confirm backend dependency status

For each surface, record:

- the backend route(s) it hits
- the contract envelope
- the owner-authorization boundary
- the privacy boundary
- the failure and availability states
- whether the route is currently available in the repository-managed environment

Confirm whether any surface still depends on a backend route that is not available or not implemented.

### Step 3 — Define the UI-12 certification matrix

Build the matrix in the exact categories below, with explicit pass/fail criteria and the test evidence required to close each one.

#### Trust and security

- owner isolation on every investment route
- non-enumerating not-found behavior
- no raw ORM/provider payload leakage
- no browser financial authority
- prompt-injection and untrusted-text handling where assistant or evidence text is used
- no execution imports, routes, vocabulary, or controls

#### Temporal and provenance

- as-of/known-at rendering and API preservation
- future-data rejection
- evidence closure
- methodology/version visibility
- stale/insufficient/unsupported states
- adjustment-basis/currency compatibility handling

#### Privacy

- account identifiers, cost basis, and portfolio weights kept out of public contexts
- public security detail separated from private portfolio context
- no cross-owner disclosure

#### Functional coherence

- discovery, recommendation, committee, evidence, decisions, outcomes, assistant, scenarios, and reports compose without semantic inversion
- decision/outcome history remains append-only
- each surface's unavailable/stale/partial/incompatible/archived states are handled

#### Accessibility and responsiveness

- supported widths including at least 390, 768, 1024, 1440, and 1728
- keyboard-only reach and visible focus
- Axe serious/critical at zero
- reduced motion behavior
- zoom/text scaling behavior
- accessible data-table fallback for meaningful financial content

#### Performance and operations

- response-time and payload budgets for the surfaces included
- bounded context sizes and pagination for large collections
- offline/default-off behavior where applicable
- operational error observability without sensitive payload leakage

### Step 4 — Close every blocking finding except the ones explicitly deferred

Fix only the gaps that block certification. Do not invent new features to make the matrix look complete. If a required backend read is not available, certify the surface as unavailable or blocked, not missing.

### Step 5 — Run the consolidated browser pass

Run one coordinated UI-12 browser pass over the final implemented surfaces using the repository's accessibility and route-mocked/live conventions and the supported width set. Record exact results, not only screenshots.

### Step 6 — Record the final certification report

Record:

- exactly which surfaces were certified
- exactly which were unavailable, blocked, or deferred
- the exact test commands and results
- the exact browser widths and acceptance checks
- the exact limitations and unresolved items
- the exact policy boundaries that remain open

---

## 9. Alternate brief reconciliation: readiness classification matrix

The alternate UI-12 brief requires a four-state audit classification. The following matrix reconciles that requirement with the measured repository evidence. `Certified` means certified only within the bounded scope stated in this document; it does not mean the entire investment domain is complete.

| Area | Expected boundary | Exists | Tested | Certified | Classification | Blocking issue or evidence |
|---|---|---:|---:|---:|---|---|
| Security identity | One canonical identity across investment surfaces | Yes | Yes | Yes, populated | COMPLETE (bounded) | Populated single-owner proof covers all eleven certified routes (closure tranche 2026-09-04); unresolved identities remain explicit |
| Market observations | Point-in-time source identity, timestamps, freshness, and hashes | Yes | Yes | Yes, populated | COMPLETE (bounded) | Contract and focused evidence; populated browser journey proven on certified routes |
| Fundamentals | Typed descriptive research only | Yes | Yes | Yes, populated | COMPLETE (bounded) | Populated journey proven; descriptive only |
| Technical | Typed descriptive research only | Yes | Yes | Yes, populated | COMPLETE (bounded) | Populated journey proven; no aggregate-risk reinterpretation |
| Macro | Typed contextual evidence only | Yes | Yes | Yes, populated | COMPLETE (bounded) | Populated journey proven |
| Quant | Bounded descriptive calculations with compatible inputs | Yes | Yes | Yes, populated | COMPLETE (bounded) | Populated journey proven; portfolio aggregate risk remains deferred (UI-11 scope) |
| Committee | Evidence-linked analysis, separate from recommendation and decision | Yes | Yes | Yes, bounded | COMPLETE | Existing persistence/HTTP/domain evidence; populated committee context rendered in the seeded proof |
| Recommendation | Canonical immutable recommendation projection | Yes | Yes | Yes, bounded | COMPLETE | Owner-scoped typed reads and recommendation derivation tests pass |
| Decisions | Explicit human action, preconditions, idempotency, append-only history | Yes | Yes | Yes, bounded | COMPLETE | Focused HTTP/service tests cover `If-Match`, idempotency, conflict, owner scope, and malformed commands |
| Outcomes | Historical/evaluative, deterministic, non-predictive | Yes | Yes | Yes, bounded | COMPLETE | Outcome service/migration/route tests cover linkage, timing, insufficiency, and owner scope |
| Discovery | Explicit current-only universe/filter, not recommendation authority | Yes | Yes | Yes, bounded | COMPLETE | UI-09 current-only/S&P 500 and separation tests pass; no discovery score |
| Scout | Contextual and bounded provider-backed read-only research with validated citations, provenance, and refusal/offline states | Yes | Yes | Yes, bounded | COMPLETE | Assistant query tests plus Scout domain/HTTP/migration tests cover typed source/claim closure, credential stripping, future timestamps, persistence immutability, owner isolation, and untrusted-data fencing |
| Risk/scenario | Current-only baseline and bounded hypothetical preview, not prediction/execution | Yes | Yes | Yes, bounded | COMPLETE | UI-11 focused domain/HTTP/browser evidence passes; advanced metrics remain unavailable |
| Authentication | Required authentication before investment disclosure | Yes | Yes | Yes, bounded | COMPLETE | Focused unauthenticated HTTP tests return 401 for investment routes |
| Authorization | Owner scope enforced at every private resource boundary | Yes | Yes | Yes, populated | COMPLETE (bounded) | Focused owner-isolation tests pass; populated single-owner proof now covers every certified route |
| Provenance | Source IDs/hashes, evidence linkage, retrieval/analysis metadata where applicable | Yes | Yes | Yes, populated | COMPLETE (bounded) | Contract and focused provenance evidence pass; populated cross-route display closure proven |
| Temporal integrity | No future-data leakage; as-of/known-at/retrieval semantics preserved | Yes | Yes | Yes, populated | COMPLETE (bounded) | Domain guards and focused future/stale tests pass; populated cross-route journey proven |
| Accessibility | Keyboard, focus, semantic structure, serious/critical Axe zero | Yes | Yes | Yes, bounded | COMPLETE | Coordinated matrix passes for eleven read-only routes incl. /portfolio with zero serious/critical axe violations (populated proof); focusable-children donut charts and scrollable risk tables fixed in the closure tranche |
| Performance | Measured route/payload/interaction budgets | Yes | Yes | Yes | COMPLETE | Route-load <10s, API payload <512 KiB, and per-route interaction CPU long-task budget measured and asserted |
| Execution boundary | No broker/order/trade/transfer/rebalance/money movement/autonomous mutation | Yes | Yes | Yes, bounded | COMPLETE | Route/request/control scans and focused no-execution tests pass; no execution layer is introduced |
| Database/migrations | One head, additive/validated migration behavior, immutable history preserved | Yes | Yes | Yes | COMPLETE | Single head `AE19a1b2c3d4e5` (45 files); migration suites pass upgrade/downgrade/re-upgrade and immutability checks; GAP-17 stale forecast assertion fixed |
| INV-12 evaluation/replay/retention | Separate evaluation and retention authority | Yes | Yes | Yes | COMPLETE (bounded) | INV-12 complete and certified (engine reuses `evaluate_outcome()`, three immutable stores, replay C+D+E, read API); D-8 closed for the personal boundary |
| CIO report archive | Durable report archive only if a concrete consumer exists | Partial | Partial | No | NOT REQUIRED (deferred) | Decision D-9: deferred; no archive without a consumer |
| Multi-user retention/deletion | Approved production retention and user deletion policy | No | No | No | OUT OF SCOPE | External multi-user blocker remains open and separately recorded; not required for personal-use certification (AGENTS.md) |
| Earlier-phase regression | UI-08 through UI-11 remain within their certified contracts | Yes | Yes | Yes, bounded | COMPLETE | Existing focused regressions and the coordinated route matrix pass; no earlier-phase product files changed |

Classification rule: a row marked `PARTIAL` or `BLOCKED` is not upgraded by documentation, route existence, or mocked data. The 2026-09-04 closure tranche upgraded the previously `PARTIAL`/`BLOCKED` rows above with runtime evidence (populated e2e proof, CPU interaction budget, `/portfolio` remediation, INV-12 completion, migration-head hygiene). A `REGRESSION` classification would require measured breakage of an earlier certified contract; none was found in this review.

## 10. Alternate brief reconciliation: end-to-end journey and data-flow evidence

The conceptual journey is represented as follows. The browser is a projection layer throughout; the route-mocked and empty-database evidence is explicitly not treated as populated owner-data proof.

| Journey stage | Canonical source/application boundary | UI route(s) | Evidence status | UI-12 disposition |
|---|---|---|---|---|
| Discover | UI-09 server-owned universe/filter projection | `/investments/discovery` | Focused HTTP/domain tests and coordinated browser matrix | COMPLETE within current-only bounded discovery; candidate is not recommendation |
| Research | Market/technical/quant/context contracts and server adapters | `/investments`, `/investments/brief`, `/market-intelligence` | Route/browser coverage exists; populated provider/source journey remains limited | PARTIAL; unavailable/stale states remain authoritative |
| Analyze | Committee/evidence/recommendation projections | `/investments/recommendations`, `/investments/brief` | Persistence, committee, recommendation, and HTTP suites pass | COMPLETE within existing read-only contracts |
| Committee | Evidence-linked `CommitteeRun`/`CommitteeFinding` read boundary | `/investments/recommendations` | Domain and persistence tests pass | COMPLETE; not a risk engine or decision |
| Recommendation | Canonical recommendation projection with hash/lifecycle | `/investments/recommendations` | Recommendation schema/route/owner/isolation tests pass | COMPLETE within bounded lifecycle |
| Review | Recommendation risks, thesis, invalidation, evidence, and provenance | `/investments/recommendations`, EvidenceDrawer | Focused UI/HTTP evidence exists; full populated cross-route browser proof remains open | PARTIAL |
| Decide | Explicit human decision with `If-Match`, idempotency, and append-only journal | `/decisions` and recommendation review | Decision service/route tests pass | COMPLETE within bounded human-controlled actions |
| Scenario / Risk | UI-11 baseline and on-demand hypothetical preview; goal Scenario Lab remains separate | `/investments/risk`, `/scenario-lab` | UI-11 and Scenario Lab suites plus coordinated browser matrix pass | COMPLETE within separate declared semantics |
| Outcome | Historical deterministic evaluation linked to recommendation/decision where available | `/decisions` with outcomes view | Outcome domain/migration/service/route evidence exists | COMPLETE within existing evaluative contract; INV-12 remains separate |

### Canonical data-flow certification

The accepted chain is:

`canonical domain -> application service -> trusted repository/projection -> typed API -> UI`

The review found no UI-12-owned browser calculation of authoritative recommendations, risk, outcomes, ownership, temporal filtering, or provenance. The following limitations remain explicit:

- UI-09 discovery data is not recommendation data.
- UI-10 Scout content is untrusted contextual data, not canonical financial fact.
- UI-11 risk/scenario data is current-only descriptive/hypothetical output, not historical portfolio risk or prediction.
- Goal Scenario Lab output is not portfolio risk.
- Recommendations, decisions, and outcomes retain distinct lifecycle and authority.
- The browser does not receive client authority to submit owner IDs, canonical values, source hashes, result snapshots, or execution commands.

## 11. Alternate brief reconciliation: trust, safety, and privacy gates

### Identity consistency

The repository preserves canonical security identifiers where contracts provide them. Ticker, company name, holding ID, account ID, and provider identifiers remain aliases or source references rather than replacements for canonical identity. UI-09 unresolved/unsupported states and UI-11 identity limitations are surfaced rather than silently reconciled. A fully populated cross-route identity replay is not claimed because the current live-stack evidence uses an isolated environment without production-like owner data.

### Owner isolation and privacy

Focused HTTP evidence proves authentication, owner filtering, non-enumerating recommendation/evidence reads, discovery portfolio scoping, UI-11 private holding exclusion, decision/outcome ownership, and strict client-authority rejection. The coordinated browser matrix additionally checks that account identifiers, account numbers, password/hash markers, and API-key markers are absent from the rendered included routes. It does not prove that every possible populated private field is absent in every provider response; that remains a limitation.

### Temporal and provenance integrity

Existing domain tests preserve source hashes, as-of/known-at constraints, freshness, adjustment/currency state, decision/recommendation timestamps, outcome evaluation timing, and scenario methodology versions. Future/stale/incompatible inputs fail closed where the underlying contract defines those rules. UI-12 does not claim historical portfolio reconstruction where holdings/valuations cannot establish it.

### Scout prompt-injection boundary

The actual application-path UI-10 query tests prove that untrusted context is wrapped as data, commands in it are ignored by the model instruction, citations outside resolved hashes result in a refusal, unavailable context avoids model invocation, and execution-intent questions are refused. The contextual projection excludes internal owner scope and raw recommendation/committee metadata. The provider-backed Scout separately validates provider source URLs, metadata, source hashes, claim closure, credential stripping, and future timestamps using hermetic provider fixtures; live third-party retrieval and live-model behavior remain outside repository-managed certification evidence.

### Decision and outcome safety

Decision routes preserve recommendation-versus-user-decision separation, `If-Match`, idempotency, lifecycle preconditions, owner scope, append-only behavior, and sanitized errors. Outcome routes preserve historical/evaluative semantics, deterministic calculations, insufficient-history handling, linkage, and no execution. No UI-12 change modifies those boundaries.

### Error-state coverage

Existing route tests and focused browser journeys cover authentication failure, unavailable context, invalid/stale/incompatible scenario inputs, missing baselines, malformed server responses, server-unavailable states, and safe retry/recovery behavior where implemented. Complete populated coverage of every route’s stale/partial/archived/error variant is not proven and remains a certification limitation.

## 12. Alternate brief reconciliation: regression and migration evidence

The relevant investment regression suites include assistant context/query, discovery, persistence, recommendation, decision, outcome, risk/scenario, Scenario Lab, and hardening tests. The historical consolidated run recorded 158 focused backend tests and 691 frontend tests, together with TypeScript, frontend lint, production build, and the expanded UI-12 matrix in degraded and hermetic live-stack modes. This reconciliation reran 43 focused backend tests, 5 focused UI tests, TypeScript, frontend lint, and the two-test UI-12 Playwright matrix. The approved UI-10 expansion additionally passed 21 focused Scout/domain/API/migration/model tests, one focused Scout UI test, TypeScript, lint, and the same UI-12 matrix with `/investments/scout` included. The focused historical migration command previously had stale assertions expecting `Z14a1b2c3d4e5`; GAP-17 replaced them with the live head `AE19a1b2c3d4e5` and the 9-test migration suite passes. The UI-10 expansion added the additive Scout migration and route/backend files; UI-12 itself added no backend migration.

No regression classification was found in this review. The Market Intelligence overflow found by the expanded matrix was corrected and the full included-route matrix now passes. The `/portfolio` overflow and mutation-scope issue was resolved in the 2026-09-04 closure tranche (GAP-10/11/12) and the eleven-route matrix including `/portfolio` now passes — not evidence that the separate UI-11 risk/scenario contract regressed.

## 13. Certification gate

UI-12 may be marked complete only if all of the following are true for the certified surfaces:

- [x] Final surface inventory is stable and documented
- [x] Every certified surface has a known backend contract and an available backend behavior
- [x] Owner isolation is proven for every owner-scoped investment route included
- [x] Privacy boundaries are proven for account identifiers, cost basis, and portfolio-private context
- [x] No execution capability exists anywhere in the certified set
- [x] No-authority claims are clearly separated from descriptive/explanatory content
- [x] Temporal/provenance constraints are visible on the implemented surfaces
- [x] Accessibility and responsive checks pass for the consolidated set
- [x] Error/unavailable/partial/empty/archived/incompatible states are handled and tested
- [x] Performance and payload criteria are stated and met for certified surfaces
- [x] INV-12 dependency items that touch UI-12 presentation are either resolved or explicitly deferred with an honest limitation
- [x] The external multi-user retention/deletion blocker is recorded as still open and is not claimed resolved

All required items pass for the defined personal-use read-only experience. UI-12 is **certified 2026-09-04** with the unresolved limitations recorded in the closure addendum below.

## Certification closure addendum (2026-09-04)

### What was remediated and certified

- **GAP-10** — `/portfolio` 390px overflow fixed: the `HeroSummary` stat-card grid is now responsive (4 `col-span-3` cards → responsive stacking); the trust spec runs the eleven-route set (including `/portfolio`) at 390/768/1024/1440/1728 with zero horizontal overflow.
- **GAP-11** — `/portfolio` mutation controls (add/edit/delete account, symbol, import, auto-refresh) are gated behind an explicit manage mode; the certified surface is read-only by default (verified by `ui12-populated-owner` manage-mode test).
- **GAP-12** — client-side portfolio arithmetic replaced by the server-owned holdings valuation projection `GET /api/v1/holdings/valuation` (totals, allocation %, gain %, with zero-denominator/negative-cost-basis fail-closed rules and owner isolation tests).
- **GAP-13** — populated single-owner e2e proof (`ui12-populated-owner.spec.ts`): seeded owner data renders on all 11 certified routes at 390px with no overflow, no cross-owner/execution request leakage, committee + evidence context rendering, and zero serious/critical axe violations (incl. keyboard-accessible scrollable risk tables and donut charts that no longer expose focusable descendants under `role=img`).
- **GAP-14** — interaction CPU budget measured in the trust spec (long-task count ≤ 4 and total ≤ 600 ms per route during load + keyboard interaction).
- **GAP-17** — stale `Z14…` migration-head assertion replaced with the live head; migration suite passes.
- **GAP-19** — repo-wide lint verified clean (`next lint` zero warnings/errors); tracker risk resolved.

### Evidence

- Backend: 312 investment/holdings/migration/dashboard/budgets tests passed (3 skipped) + 16 focused (valuation + migration).
- Frontend: 693 vitest tests passed (86 files); `tsc --noEmit` clean; `next lint` clean.
- E2E: `ui12-trust-certification` 2/2 and `ui12-populated-owner` 4/4 passed; 70 additional route-mocked e2e tests passed. Two environment-only failures (`universe.spec.ts`, `imports-and-analyst` upload) require the live `scripts/test-e2e.sh` stack (`ECONNREFUSED :8000`) and are unrelated.
- `git diff --check` clean.

### Remaining limitations (non-blocking, recorded)

- Populated coverage of every stale/partial/archived/error variant per route is not exhaustively proven (pre-existing limitation).
- The external multi-user retention/deletion blocker (`external-multi-user-retention-deletion-blocker`) remains open and is not claimed resolved; it is out of scope for the personal single-user boundary (AGENTS.md).
- Deferred by decision: CIO archive (D-9), calibration (D-7), replay A+B, methodology registry (D-10), canonical universe master (GAP-06), UI-11 advanced historical risk.

---

## Appendix A — UI-11 residual limitation (explicit handoff constraint)

UI-12 must inherit the current UI-11 boundary honestly:

- UI-11 is implemented and certified only for a current-only owner-scoped portfolio baseline, descriptive value/data-quality metrics, and an on-demand hypothetical position-value preview
- UI-11 does not claim historical portfolio reconstruction
- UI-11 does not claim portfolio volatility, covariance, correlation, drawdown history, liquidity, FX normalization, sector/geography risk, VaR, probability, optimization, target allocation, or persisted scenarios
- UI-11 does not resolve security identities where no verified security-master reference exists; unresolved/unsupported positions remain explicit
- UI-11 does not mutate accounts, holdings, recommendations, decisions, outcomes, forecasts, or Scenario Lab records

UI-12 must not relabel current UI-11 coverage as complete portfolio risk, and it must not invent unavailable advanced metrics to make the portfolio surface appear finished.

---

## Appendix B — Final audit verdict

**UI-12 remains PARTIAL and is not certified.**

The repository has a frozen surface inventory, typed owner-scoped contracts, a coordinated browser matrix, explicit route/payload budgets, and a successful hermetic live-stack run for the bounded read-only candidate set. Certification is still blocked by the measured `/portfolio` mobile overflow and mutation scope, lack of populated owner-data proof for every backend-dependent surface in the isolated live run, unresolved INV-12 evaluation/replay/retention semantics, the undecided optional CIO archive, the unmeasured CPU interaction budget, and the open multi-user retention/deletion policy.

The next implementation task is the separately bounded remediation of those concrete blockers. UI-12 must not be marked complete until the certified surface set and dependency policy are closed.

---

## Appendix C — Implemented investment surface inventory

This inventory is the current canonical starting point for UI-12. Activation is from `ui/lib/informationArchitecture.ts` and the implemented route files in the repository.

### Final activated investment surfaces

| Surface | Route | Implementation state | Backend contract availability in audit scope | UI-12 disposition |
|---|---|---|---|---|
| Investment Command Center | `/investments` | Implemented UI only | Navigation anchor; no new financial authority | Certify as navigation landing, not as a data authority surface |
| Investment Discovery | `/investments/discovery` | Implemented | Server-owned current-only portfolio and bounded S&P 500 projection exists | Certify within bounded current-only scope only |
| Investment Brief | `/investments/brief` | Implemented UI | Required backend read must be available for real certification | Certify only when the real backend read path is available; otherwise unavailable |
| Recommendation Review | `/investments/recommendations` | Implemented | Owner-scoped recommendation/committee/evidence/decision/outcome reads exist | Certify with privacy isolation and decision precondition checks |
| Investment Scout | `/investments/assistant` | Implemented | InvestmentAssistantContext/v1, InvestmentAssistantQueryRequest/v1, InvestmentAssistantResponse/v1 exist | Certify as read-only contextual workspace; keep prompt-injection/citation/refusal boundaries |
| Risk and Scenario Views | `/investments/risk` | Implemented | InvestmentPortfolioBaseline/v1 and InvestmentRiskScenario/v1 exist | Certify within current-only slice; do not relabel as complete portfolio risk |
| Scenario Lab | `/scenario-lab` | Implemented | Goal-scoped scenario projections exist | Certify as goal projection only; do not present as portfolio risk |
| Decisions | `/decisions` | Implemented | Decision journal, outcomes, recommendation linkage exist | Certify append-only decision/outcome/history behavior |
| Market Intelligence | `/market-intelligence` | Implemented | Market brief/pulse/archive patterns exist | Certify with provider-availability and operational-recovery checks |
| Portfolio | `/portfolio` | Implemented, blocked for UI-12 read-only certification | Current holdings/portfolio view exists, but the 390px browser check measured 407px document width and the page includes mutation controls | Exclude from the current certifiable set; remediate responsive/scope boundary separately |

### Current certifiable set and exclusions

The current UI-12 certifiable set is the ten read-only routes covered by `ui12-trust-certification.spec.ts`: `/investments`, `/investments/discovery`, `/investments/brief`, `/investments/recommendations`, `/investments/assistant`, `/investments/scout`, `/investments/risk`, `/scenario-lab`, `/decisions`, and `/market-intelligence`. The `/portfolio` route remains in the inventory but is excluded because its measured mobile overflow and mutation controls fail the current read-only gate.

### Surfaces that remain deferred or blocked

- Advanced/historical portfolio risk: deferred by design; blocked by missing approved methodology and proven reconstructed historical inputs
- Durable CIO report archive UI: deferred unless a concrete consumer is identified
- Any discovery/security/portfolio selector adapters that would expand UI-10 context beyond the approved bounded read-only scope: deferred until dedicated server-owned adapters exist
- INV-12 evaluation/replay/retention UI: not started; depends on its own approved contract and policy boundary

---

## Appendix D — Documented blocking gaps

These are the gaps that still prevent a real UI-12 certification. Each one is phrased as a concrete missing item, not a vague feeling.

1. **`/portfolio` is outside the certifiable read-only set.** The existing page measured `scrollWidth=407` against a `390px` viewport and includes mutation controls; it needs a separately owned responsive/scope remediation.
2. **Populated live-backend evidence is incomplete.** The hermetic run proves isolated migration, service startup, route registration, and safe rendering, but the empty isolated database does not prove populated owner data for every backend-dependent surface.
3. **CPU budgets are not yet measured.** Route-load and payload budgets are now explicit and pass for the bounded set; CPU interaction budgets remain a follow-up measurement.
4. **INV-12 evaluation/replay/retention semantics are not resolved.** No UI-12 claim depends on or invents those semantics.
5. **Optional durable CIO report archive decision is unresolved.** The archive is excluded from the certifiable set until a concrete consumer authorizes it.
6. **External multi-user retention/deletion blocker remains open.** UI-12 cannot conclude multi-user production readiness, even if personal-use/runtime UI certification later passes.

---

## Appendix E — Verified pass criteria for the implemented surfaces

For the surfaces that are implemented and included in the audit scope, UI-12 certification requires the following documented pass criteria.

### Trust and security

- Every owner-scoped investment route in the certified set resolves owner scope from authentication before disclosure
- Cross-owner IDs return non-enumerating not-found behavior
- No raw ORM/provider payload leaks into browser responses
- No execution imports, routes, vocabulary, or controls appear in the certified surfaces
- Assistant/scenario/evidence text is treated as data, with prompt-injection and untrusted-content boundaries preserved

### Privacy

- Account identifiers, cost basis, and portfolio weights are not shown in public contexts
- Public security detail is separated from private portfolio context
- Cross-owner disclosure is blocked and documented

### Temporal and provenance

- As-of/known-at/freshness/yield/source metadata are visible where the surface claims authority
- Future-source data is rejected or explicitly unavailable
- Stale, insufficient, unsupported, incompatible, and archived states are explicit, not converted into current/authoritative values
- Methodology/version metadata is visible where the surface presents results

### Functional coherence

- Discovery, recommendation, committee, evidence, decisions, outcomes, assistant, scenarios, and reports compose without semantic inversion
- Decision/outcome history remains append-only
- Each surface handles loading, empty, unavailable, partial, stale, incompatible, archived, and error states

### Accessibility and responsiveness

- Supported widths include at least 390, 768, 1024, 1440, and 1728
- Keyboard-only reach works and focus is visible
- Axe serious/critical violations remain at zero
- Reduced motion and zoom/text-scaling behavior is acceptable
- Meaningful financial content has an accessible data-table fallback

### Performance and operations

- Route-load budget: under 10 seconds from navigation to the route's main heading in the certification harness
- API response payload budget: under 512 KiB for responses observed by the UI-12 harness
- Collection limits: discovery requests remain server-bounded at 100 items; assistant context remains bounded by its `max_evidence` contract; Scenario Lab comparisons remain bounded by the existing route contract
- Response-time and payload budgets are stated and met for the 10-route certifiable set
- Large collections use bounded pagination or selection
- Offline/default-off behavior is explicit where applicable
- Operational failures are observable without sensitive payload leakage

---

## Appendix F — Final execution verdict and remaining certification gaps

The remaining UI-12 work is now explicitly separated into two different things:

1. **Repository-scoped audit and coordinated evidence work, which is complete for the bounded set.**
2. **UI-12 certification, which remains partial because concrete route and policy blockers remain.**

Audit completion work done:

- Created and updated `docs/architecture/ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md`
- Documented the final implemented surface inventory and activation states
- Documented the blocking gaps that still prevent UI-12 certification
- Documented the pass criteria required to certify the implemented surfaces
- Added the UI-12-owned coordinated browser certification matrix
- Ran the matrix once in degraded route-mocked mode and once through the hermetic live stack
- Ran the implemented investment browser specs in one coordinated run and recorded the results
- Historical consolidated evidence recorded 138 focused backend contract/route tests covering assistant, discovery, persistence, UI-11 risk, Scenario Lab, accounts, holdings, and decision history
- Historical consolidated evidence recorded 691 frontend Vitest tests, TypeScript typecheck, and the production build
- UI-10 expansion evidence passed 21 focused backend Scout/domain/API/migration/model tests, one focused Scout UI test, TypeScript, frontend lint, and the two-test UI-12 Playwright matrix including `/investments/scout`
- Reconciliation rerun passed 43 focused backend tests, 5 focused UI tests, TypeScript, frontend lint, and the two-test UI-12 Playwright matrix
- Ran tracker validation, render check, and `git diff --check`
- Preserved the unrelated dirty worktree

Remaining items that still block UI-12 certification:

- `/portfolio` remains blocked: the current route measured 407px document width at a 390px viewport and contains mutation controls outside the read-only UI-12 set
- the live-stack pass proved service startup and route rendering, but did not prove populated owner data for every backend-dependent surface; empty/unavailable states were the safe result in the isolated database
- INV-12 evaluation/replay/retention semantics remain unresolved and are not claimed by UI-12
- the optional durable CIO report archive remains deferred pending a concrete consumer
- external multi-user production readiness remains blocked until retention and user-deletion policy is approved

---

## Appendix G — Remaining work before UI-12 certification

- Remediate `/portfolio` overflow and explicitly separate or gate its mutation workflow before adding it to the certified set
- Seed deterministic synthetic owner data in the hermetic live-stack harness, or document each backend-dependent route as unavailable, then rerun populated live-backend proof
- Measure and record CPU interaction budgets for the final certified set
- Resolve the INV-12 evaluation/replay/retention boundary and keep evaluation-linked UI excluded until then
- Record the CIO archive as deferred unless a concrete consumer is approved
- Preserve the external multi-user retention/deletion blocker and do not claim multi-user production readiness

---

## Appendix H — Files and artifacts

Created or updated for this audit:

- `docs/architecture/ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md`
- `ui/__tests__/e2e/ui12-trust-certification.spec.ts`
- `ui/components/market-briefs/MarketIntelligenceCenter.tsx`

The UI-12-specific change in the prior certification execution was limited to the certification harness, documentation/status evidence, and a localized responsive layout correction in Market Intelligence. The separately approved UI-10 expansion in the current worktree adds the provider-backed Scout contracts, route, immutable migration/model, client/UI surface, and focused tests; it does not modify UI-08 through UI-11 semantics or add execution capability.

The alternate UI-12 final-certification brief was reconciled against this audit on 2026-09-04. Its broader journey and trust requirements are represented below as evidence gates; they do not upgrade mocked or empty-database evidence into certification.

The coordinated matrix is evidence for a bounded 10-route read-only set, including `/investments/scout`; provider-backed external calls are not exercised by the harness. It is not a certification of `/portfolio`, INV-12 evaluation/replay/retention, the optional CIO archive, or external multi-user production readiness.

References:

- `docs/10-roadmap/PROJECT_STATUS.json`
- `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`
- `docs/architecture/ATLAS-INVESTMENT-UI-UX-IMPLEMENTATION-ROADMAP.md`
- `docs/architecture/ATLAS-INVESTMENT-CONSOLIDATED-EXECUTION-PLAN.md`
- `docs/architecture/ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md`
- `docs/adr/ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`
- `ui/lib/informationArchitecture.ts`
- `ui/__tests__/e2e/ui12-trust-certification.spec.ts`

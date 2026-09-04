# Atlas Investment System — Comprehensive INV/UI Cross-Phase Audit

**Date:** 2026-09-04
**Status:** Audit-only deliverable. No application code, schema, migration, test, UI, configuration, or roadmap file was changed except this report. Nothing was committed or pushed.
**Method:** Read-only inspection of `services/rules-service` (contracts, models, routes, migrations, tests), `ui` (routes, e2e specs), `docs/10-roadmap`, `docs/architecture`, `docs/adr`, and git history. Where documentation and implementation disagree, **implementation + tests + accepted ADRs take precedence**; every disagreement is recorded below.
**Supersedes:** `ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` v1 (2026-09-04). The v1 blocking-vs-polish finding is preserved but refined here into a full dependency/contract/certification audit.

---

# Comprehensive INV/UI Cross-Phase Audit

## Executive Verdict

**ROADMAP READY WITH BOUNDED PREREQUISITES**

The roadmap's headline sequence (INV-01…09 → INV-11 → INV-12 → UI-12) is correct and matches implementation evidence; there are **no circular dependencies**. However, the audit found that the remaining roadmap is not a single contiguous build. It is gated by a small, clearly defined set of prerequisites, several of which are **not yet defined as contracts** (INV-12 evaluation artifact, durable market-observation store, durable portfolio-snapshot store, retention/deletion policy) and several of which have been **mis-bucketed into the UI-12 blocker list when they actually belong to earlier phases** (`/portfolio` remediation, populated-owner-data harness proof).

The honest characterization:

- **INV-01…INV-11, UI-01…UI-11**: implemented and certified within bounded scope — GREEN (no evidence of incorrect "complete" labels).
- **INV-12**: ORANGE/RED — not started, and **cannot be implemented to production quality without three contracts that do not exist yet**: (1) a durable historical market-observation store with `as_known_at` vintages, (2) a durable immutable portfolio-snapshot store, and (3) an approved retention/deletion policy for immutable history.
- **UI-12**: ORANGE — certification is correctly `PARTIAL`, and **two of its seven documented blockers are not UI-12 work**: `/portfolio` remediation (belongs to the portfolio surface / UI-04 boundary) and populated-owner-data proof (belongs to the test harness). The remaining five are genuine gates (INV-12, CPU budget, CIO archive decision, retention policy, and the `/portfolio` read-only exclusion).
- **Two implementation defects were found and are documented, not fixed** (see GAP-09 duplicate baseline engine with divergent identity semantics; GAP-12 `/portfolio` client-side authoritative arithmetic).

---

## 1. Current Repository State

| Item | Value |
|---|---|
| Branch | `main` |
| Worktree | **clean** at audit start (0 modified, 0 untracked) |
| Upstream sync | `0 ahead / 0 behind origin/main` |
| Latest commits | `eb088de` chore(atlas): mark ui-10 provider-backed scout expansion complete; `84259ee` feat(investment): complete ui-10 provider-backed scout expansion and publish completeness gap report; `ad6bfb8` chore(atlas): record ui-12 trust certification evidence |
| Migration head | exactly one: **`AB16a1b2c3d4e5`** (`42` version files) |
| Pre-existing changes | none (clean worktree) — audit adds only this report |

---

## 2. Master Phase Matrix

Legend — Documented Status: from canonical tracker `PROJECT_STATUS.json`. Actual: verified by inspection of code/tests/migrations. Classification: GREEN = complete; YELLOW = implemented with non-blocking gaps; ORANGE = incomplete/dependency gap; RED = architectural blocker; GREY = deferred/out of scope.

| Phase | Intended Capability | Documented | Actual | Contract | Impl | Tests | Integration | Blocking Dependencies | Recommended Action | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| INV-01 | Canonical security identity; aliases never authority | complete | Verified: `SecurityIdentity/v1`, `SecurityIdentifier/v1`, hashed ids, state machine (resolved/unresolved/ambiguous/unsupported/inactive). **No durable security-master table.** | Yes | Yes | Yes | Partial | Security master (hidden prereq) | Keep; add master only when a source exists | GREEN (bounded) |
| INV-02 | Point-in-time market observations | complete | Verified: `MarketObservation/v1` with `observation_hash`, `as_of <= retrieved_at`, freshness/adjustment/quality. **Contract-only — no persisted observation table.** | Yes | Partial | Yes | Partial | **Durable observation store (pre-INV-12)** | Keep; treat as contract layer pending store | YELLOW |
| INV-03 | Portfolio intelligence, no second ledger | complete | Verified: `PortfolioSnapshot/v1` deterministic, owner-scoped, hashed, consumes Account/Holding. **Snapshot not persisted as a table** (only `portfolio_snapshot_hash` column on recommendation). | Yes | Yes | Yes | Partial | Durable snapshot store (pre-INV-12) | Keep | YELLOW |
| INV-04 | Fundamentals research | complete | Contract + adapters exist; descriptive only | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-05 | Technical research | complete | Contract + `PriceSeriesPoint`; adjustment-basis-safe | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-06 | Macro intelligence | complete | Contract + vintaged observation contract | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-07 | Quant metrics | complete | Verified `quant.py`: returns, volatility, max drawdown, Sharpe (risk-free gated), beta (benchmark gated), zero-close fail-closed, insufficient-history states, deterministic hash | Yes | Yes | Yes | Partial | none (single-security only) | Keep; aggregate portfolio risk is UI-11-deferred | GREEN (bounded) |
| INV-08 | AI Investment Committee | complete | Verified: `CommitteeRun/Finding`, `EvidencePacket`, links, frozen payloads, `analysis_as_of`, methodology, hashes; persisted owner-scoped | Yes | Yes | Yes | Yes | none | Keep | GREEN |
| INV-09 | Investment recommendations | complete | Verified: full lifecycle (active/superseded/expired/withdrawn), conviction, thesis/risks/invalidation, evidence links, `input_hash`/`recommendation_hash`, `portfolio_snapshot_hash`, persisted | Yes | Yes | Yes | Yes | Durable snapshot store for point-in-time reconstruction | Keep | GREEN |
| INV-10 | CIO reporting | complete (bounded) | Verified: deterministic in-memory `CIOReport/v1` + hash. **No persistence, route, scheduler, delivery, or archive.** | Yes | Yes | Yes | Partial | Archive decision (deferred) | Keep deferred; do not build archive without consumer | GREY (extensions) |
| INV-11 | Decision / outcome tracking | complete | Verified: `InvestmentDecisionRecord` (`If-Match` + `Idempotency-Key` required, 428 otherwise, idempotent), `InvestmentOutcomeRecord`, `RecommendationOutcome/v1` deterministic evaluation with zero-price/insufficient-history fail-closed; separate append-only goal substrate exists too | Yes | Yes | Yes | Yes | Durable observation store for outcome re-evaluation | Keep | GREEN |
| INV-12 | Evaluation / calibration / replay / retention | **not_started** | **No module, no contract, no test, no migration exists.** | **No** | No | No | No | **3 contracts below (§7)** | Design gate first (§17 step 3) | **RED** |
| UI-08 | Recommendation review + human decision | complete | Verified: `routes/investment_persistence.py` — auth via `require_user`, owner-scoped reads, non-enumerating not-found, `If-Match`/`Idempotency-Key` (428), typed responses | Yes | Yes | Yes | Yes | none | Keep | GREEN |
| UI-09 | Discovery + comparison | complete (bounded) | Verified: current-only portfolio + bundled `sp500_symbols.json` universe; deterministic stable ids; **no canonical security/universe master** | Yes | Yes | Yes | Yes | Canonical universe/master (hidden prereq for real discovery) | Keep; bounded claim is accurate | YELLOW |
| UI-10 | Context Scout + provider-backed Scout | complete (both slices) | Verified: assistant context/query + scout research/runs routes; Finnhub/SEC server adapters; held-security resolution; credential stripping; future-timestamp rejection; immutable scout runs; **no Phase 1R operator flow exists in repo** | Yes | Yes | Yes | Yes | Dedicated adapters for discovery/security/portfolio selectors (deferred) | Keep; limitations accurate | GREEN |
| UI-11 | Risk/scenario decision support | complete (bounded) | Verified: current-only baseline + hypothetical value preview; **duplicate baseline engine vs INV-03 (GAP-09)**; no volatility/drawdown/VaR; no persistence | Yes | Yes | Yes | Yes | Approved historical methodology + inputs (deferred) | Keep; fix GAP-09 at owning boundary | YELLOW |
| UI-12 | Final cross-route certification | in_progress (not certified) | Verified: ten-route read-only matrix passes (degraded + hermetic); `/portfolio` excluded (407px overflow at 390px, mutation controls, client-side calc); four policy/evidence blockers open | Partial | Partial | Partial | Partial | INV-12, `/portfolio` remediation, populated-data proof, CPU budget, CIO decision, retention policy | Close blockers (§17) | ORANGE |

**Incorrect "complete" labels found:** none. Every phase marked complete has contracts, implementation, and test evidence within its declared bound. The two material findings are **missing contracts** (INV-12, observation store, snapshot store) and **mis-bucketed blockers**, not false certifications.

---

## 3. Actual Architecture (verified data flow)

```text
External provider (Finnhub / SEC) ── server-side adapters only ──┐
                                                                  ▼
Account/Holding (legacy models) ──▶ INV-03 PortfolioSnapshot (hash; NOT persisted as table)
Holding-derived SecurityIdentity (symbol+type inference)          │
   ├── portfolio_intelligence: RESOLVED from symbol+type          ▼
   └── risk_scenarios: UNRESOLVED until master        INV-07 Quant (returns/vol/dd/sharpe/beta; hash)
                                                                  ▼
MarketObservation (contract, ephemeral) ──▶ EvidencePacket (persisted, frozen payload)
                                                                  ▼
INV-08 CommitteeRun/Finding (persisted, hashed) ──▶ INV-09 Recommendation (persisted, hashed,
                                                        portfolio_snapshot_hash, evidence links)
                                                                  ▼
INV-11 HumanDecision (persisted; If-Match + Idempotency) ──▶ RecommendationOutcome (persisted;
                                                        evaluation frozen from supplied observations)
                                                                  ▼
INV-12 Evaluation/Replay/Retention ──✗ does not exist
                                                                  ▼
UI-08..11 consume typed API projections; UI-12 certifies the ten read-only routes
(/portfolio excluded)
```

Discrepancies found versus the "ideal" chain:

- **No durable observation store**: `MarketObservation` exists as a Pydantic contract only; `outcome_tracking.py` defines its own `MarketObservation`. Nothing persists price history, so the `source_observation_hashes` referenced by quant/committee/evidence cannot be re-resolved to values later.
- **No durable portfolio-snapshot store**: `PortfolioSnapshot` is computed on demand; only the hash is stored on recommendations. Historical snapshot payloads are not reconstructable from a table (only from whatever `payload_json` embedded).
- **Two independent decision/outcome substrates**: the goal/forecast substrate (`Recommendation`, `DecisionJournalEntry`, `OutcomeEvaluation` — append-only triggers) and the investment substrate (`InvestmentRecommendationRecord`, `InvestmentDecisionRecord`, `InvestmentOutcomeRecord`). Deliberate, but INV-12 must state which substrate its evaluation artifact covers (investment substrate per roadmap; goal substrate is Phase-1 personal-finance domain).
- **No duplicate calculation engine in UI code for the certified set**: Scenario Lab and risk pages make no browser-side financial calculations. **But** the legacy `/portfolio` page computes totals, allocation %, and gain % client-side (GAP-12), and UI-11's `risk_scenarios.py` duplicates INV-03's baseline aggregation with divergent identity semantics (GAP-09).

---

## 4. Dependency Graph (from evidence)

```text
INV-01 Security identity
  └─▶ INV-02 Market observations ──┐
INV-03 Portfolio snapshot ─────────┤
INV-04/05/06 Fundamentals/Tech/Macro ──┘
                  ▼
           INV-07 Quant
                  ▼
           INV-08 Committee ──▶ INV-09 Recommendation ──▶ INV-11 Decision/Outcome
                  │                     │                       │
UI-09 Discovery ◄─┘                     ▼                       ▼
UI-10 Scout ◄───────────────────────────┘                       │
UI-11 Risk ◄──────── holdings/INV-03/INV-07 (bounded)           │
                  ▼                       ▼                     ▼
                              INV-12 (not started) ◄── durable observations + snapshots + retention policy
                  ▼                       ▼
UI-08 ◄──────────Recommendation/Decision/Outcome typed reads
UI-12 ◄────────── all certified surfaces + INV-12 boundary + policy
```

Positioning of UI phases (from evidence): UI-08 sits on INV-09/11 reads; UI-09 on INV-02/03 projections + bundled S&P 500 file; UI-10 on INV-08/09 persisted context + Finnhub/SEC adapters; UI-11 on holdings/INV-03 baseline + INV-07 metric availability (advanced deferred); UI-12 is the terminal certification phase over all of them plus INV-12 and policy. This matches the roadmap's documented order (INV-12 before UI-12).

---

## 5. Circular Dependencies

**None found.**

- UI-12 requires INV-12; INV-12 does **not** require UI-12 (INV-12 is backend-first by roadmap and audit) → no cycle.
- UI-09 requires INV-09 outputs as optional `recommendation_id` on candidates, but INV-09 does not require discovery → no cycle.
- UI-10 requires INV-08/09 persisted context and provider adapters; the provider adapters do not consume Scout → no cycle.
- UI-11 requires holdings/INV-03-style baseline; INV-03 does not require UI-11 → no cycle.

**Soft dependency to watch (not a cycle):** UI-12's certification gate text says "INV-12 dependency items that touch UI-12 presentation are either resolved or explicitly deferred" — so UI-12 cannot be *certified* until INV-12 is decided. This is an intended ordering, and the audit recommends keeping it, not breaking it.

---

## 6. Hidden Prerequisites

Capabilities assumed or implied by the roadmap but **not formally defined/implemented**:

| # | Hidden prerequisite | Kind | Required before | Current state |
|---|---|---|---|---|
| HP-01 | Durable historical market-observation store (with `as_known_at` vintages, hashes) | CONTRACT + ARCHITECTURE | **INV-12** (replay/baseline/evaluation re-run), full UI-11 historical | Missing (contract-only) |
| HP-02 | Durable immutable portfolio-snapshot store (payload + hash) | CONTRACT + ARCHITECTURE | **INV-12**, point-in-time portfolio reconstruction, UI-11 historical | Missing (hash-only) |
| HP-03 | INV-12 evaluation artifact contract (ID, owner, rec hash, window, methodology, benchmark, state, hashes) | CONTRACT | INV-12 implementation | Missing |
| HP-04 | Replay semantics definition (A..E in §13) resolved to exactly one contract meaning | CONTRACT | INV-12 implementation | Ambiguous — flag for product owner |
| HP-05 | Retention & user-deletion policy for immutable history | POLICY | Multi-user production; INV-12 retention slice; UI-12 multi-user gate | Open product-security blocker |
| HP-06 | Canonical security/universe master | CONTRACT | Real discovery beyond portfolio+S&P500 file; UI-10 security-master selector; identity consistency | Missing (only bundled `sp500_symbols.json` + holdings) |
| HP-07 | Model/methodology version registry | CONTRACT | INV-12 replay reproducibility (D) | Partial (version strings embedded, no registry) |
| HP-08 | Calibration cohort/methodology + minimum sample rules | CONTRACT | INV-12 calibration slice | Missing (deliberately gated) |
| HP-09 | CIO report archive decision + durable archive | DECISION | Only if a concrete report consumer emerges | Deferred; correctly optional for UI-12 |
| HP-10 | Scenario persistence (UI-11) | CONTRACT | Only if roadmap wants reusable scenarios | Deferred; current previews are on-demand non-persistent |
| HP-11 | Populated owner-data synthetic seeding | TEST | UI-12 populated-route proof | Missing (hermetic run used empty DB) |

---

## 7. INV-12 Readiness

**Verdict: NOT READY. Three exact missing contracts:**

1. **Durable market-observation store (HP-01).** INV-12 replay/re-evaluation must reconstruct "what the system knew" at evaluation time. Today `evaluate_outcome()` receives observations as a parameter; nothing persists them. Outcomes freeze the computed prices/returns and hashes, but a later re-baseline, horizon change, or restated-price re-run is impossible without the original series. The goal substrate's `OutcomeEvaluation` is hash-only evidence by design, so it does not help.
2. **Durable immutable portfolio-snapshot store (HP-02).** Recommendations store `portfolio_snapshot_hash` but not the snapshot payload as a first-class immutable record. Replay of portfolio-linked evaluation cannot reconstruct the baseline allocation.
3. **Approved retention/deletion policy (HP-05)** — the known product-security blocker.

Also missing: the evaluation artifact contract itself (HP-03) and an unambiguous replay definition (HP-04). The roadmap already defines the minimum artifact fields in `ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md` §INV-12, so the design gate is spec'd, but no code or migration exists.

**Can INV-12 be safely implemented on the current architecture?** For the *deterministic recalculation of already-frozen values* (replay meaning D: reproduce hashes) — yes, hashes and frozen payloads support re-derivation. For *reconstruction of what the system knew at a point in time* (meaning B/C) or *re-evaluation over a different horizon with revised data* (meaning A with restated facts) — **no**, because observations and snapshots are not durably stored. The audit therefore recommends: **define INV-12 as replay over frozen artifacts first (D + C), and gate B/A on HP-01/HP-02.**

---

## 8. UI-12 Readiness

**Verdict: PARTIAL / NOT CERTIFIED — confirmed accurate, with two blockers mis-bucketed.**

Verified against the audit and live code:

| Documented blocker | Verified? | Truly a UI-12 blocker? | Recommended owner |
|---|---|---|---|
| `/portfolio` 390px overflow (scrollWidth 407 > 390) | Yes (measured, documented in audit) | **No — earlier-phase surface work** | Portfolio surface / UI-04 boundary |
| `/portfolio` mutation controls | Yes (page has add-account/symbol/import/auto-refresh controls) | **No — it is expected local portfolio data-entry; it must be separated/gated from the read-only certifiable set, but is not an execution-boundary violation** | Portfolio surface |
| `/portfolio` client-side authoritative arithmetic (new finding GAP-12) | Yes (totals, allocation %, gain % computed in browser) | **No** — strengthens the exclusion | Portfolio surface |
| Populated-owner-data proof | Yes (hermetic run used empty DB) | **No — harness/test work, not phase work** | Test harness |
| CPU interaction budget | Yes (route-load & payload budgets only) | Yes | UI-12 |
| INV-12 evaluation/replay/retention | Yes (not started) | Yes (gate) | INV-12 |
| Optional CIO archive | Yes (undecided) | Conditional — required only if a consumer exists; currently correctly deferred | Product decision |
| Multi-user retention/deletion policy | Yes (open blocker) | Yes for production claim; **not needed for personal-use certification** | Product/security |

**Key correction:** UI-12 certification for the personal-use read-only experience does **not** require INV-12 to be fully implemented — it requires the INV-12 *boundary decision* to be recorded (which the audit already records as an explicit deferred limitation). The audit brief's own rule ("certify implemented surfaces and explicitly list deferred capabilities") supports certifying the ten-route set once `/portfolio` is remediated/separated, populated-data proof is added, and CPU budgets are measured — even while INV-12 remains deferred, provided the audit language says so. The current audit already says exactly that, so the disposition is sound; the *action* of certifying is simply not done yet.

---

## 9. Security Boundary

**Findings (verified, none fixed):**

- Authentication: every investment route inspected (`investment_scout.py`, `investment_persistence.py`, `investment_risk.py`, `investment_discovery.py`, `investment_assistant.py`) requires `require_user`; unauthenticated requests → 401 (test evidence exists per surface).
- Owner isolation: owner scope resolved from auth; owner-id injection in client payloads rejected (422 test evidence); non-enumerating not-found (404) tests for recommendations/evidence/runs.
- Decision preconditions: `create_decision` requires `Idempotency-Key` + `If-Match` → 428 if missing; validates recommendation hash; append-only journal.
- Scout prompt-injection: untrusted source text is wrapped as data; citation validation against resolved hashes; credential stripping of source URLs; execution-intent refusal.
- Execution boundary: **no order/trade/broker/rebalance/transfer/money-movement route, import, control, or vocabulary exists in the certified set** (verified by route inventory + scans). `/portfolio` mutation controls mutate local `Account`/`Holding` rows (import/data-entry) and **do not cross** the broker/execution boundary — they are local personal-finance data entry.
- Weakness (documented, not fixed): `/portfolio` performs authoritative arithmetic client-side (GAP-12), which is outside the certified read-only boundary but violates the "no browser financial authority" principle within its own surface.

---

## 10. Temporal / Provenance Integrity

**Findings:**

- Strong where contracts define it: `MarketObservation.as_of <= retrieved_at`; quant zero-close fail-closed; outcome evaluation filters `as_known_at <= as_of` and `observed_at <= as_of`; health of Scout future-timestamp rejection for retrieved/publication timestamps; UI-11 future-source fail-closed; recommendation/committee `analysis_as_of` ordering invariants.
- **Provenance loss points (documented):**
  1. `source_observation_hashes` are stored on quant/evidence/outcome records, but the observation values themselves are not durable → a hash cannot later be "opened" to prove what it was. Provenance chain breaks at the observation boundary (pre-INV-12).
  2. `PortfolioSnapshot` payload not persisted → portfolio provenance is hash-only.
  3. Two identity-resolution semantics for the same holding (GAP-09) produce different `security_id`/state values depending on which module builds the identity → identity provenance is inconsistent across surfaces.
- No path found where future information can silently back-fill an older recommendation: evidence packets are frozen payloads and committee findings carry `analysis_as_of`; temporal validation exists in domain and HTTP tests for each surface.

---

## 11. Data Lifecycle / Retention

**Findings:**

- Immutable/append-only enforced on: goal substrate `Recommendation` and `OutcomeEvaluation` (DB triggers), Scout runs (migration test suite), statistical invariants on decision idempotency.
- Investment recommendation/decision/outcome tables use RESTRICT FKs and lifecycle statuses (supersede/expire are *new state*, not rewrites); no destructive migration exists.
- **No retention policy** exists for: recommendations, decisions, outcomes, evidence, source snapshots, portfolio snapshots, committee runs, Scout runs, evaluation records, or CIO reports (which are not even persisted). This is the known product-security blocker (HP-05).
- **No user/owner deletion semantics** for investment records. Orphan behavior is RESTRICT (cannot delete a user with investment records), which fails safe but leaves no deletion path — fine for personal use now, blocking for multi-user production.
- **Distinction:** retention duration = product requirement (undefined); account/owner deletion = operational/policy requirement (undefined); cascade/orphan semantics = architecture requirement (RESTRICT is a safe partial answer but unplanned for cleanup).

---

## 12. Multi-User / Privacy

**Findings:**

- All persisted investment objects carry `owner_id` + RESTRICT FK to `users`; owner filtering at repository/route boundaries; cross-owner HTTP tests pass per surface.
- No multi-owner production proof for the whole surface set (empty-DB hermetic run only).
- Tenant/account boundary beyond `owner_id` is transitional (`risk-transitional-tenancy`), and `get_or_create_local_user` in scout routes creates local users on demand — a personal-use convenience that must be revisited before multi-user rollout.
- Privacy: public security detail vs private portfolio context is separated in typed projections; account identifiers/cost basis/other-owner data are excluded from certified read-only surfaces (redaction checks pass). `/portfolio` intentionally displays holdings with cost basis and account context — that is its legitimate private function, not a leak.

---

## 13. Determinism / Replay

**Findings:**

| Subsystem | Class | Notes |
|---|---|---|
| Quant (INV-07) | Deterministic | Same points+as_of → same hash |
| Portfolio snapshot (INV-03) | Deterministic | Same holdings → same hash; but recomputation uses *current* holdings, not historical |
| Committee/Recommendation | Deterministic over frozen inputs | Hash = f(payload); model_metadata string-only |
| Outcome (INV-11) | Deterministic | Same observations+tracking → same hash; observations not durable |
| Scout | Deterministic metadata, model prose probabilistic | Explicit contract |
| Legacy goal Recommendation | Deterministic | Deterministic PK over inputs |

**Replay meaning analysis (the roadmap is ambiguous — flag):**
- A (recalculate historical result with exact historical inputs): possible only where inputs frozen (committee/rec) — not for market observations.
- B (reconstruct what system knew, point-in-time evidence): **not possible** without HP-01 (durable observations with `as_known_at`).
- C (reconstruct recommendation from frozen inputs): possible (hashes + payload_json).
- D (reproduce model output with same methodology/version): partially — methodology versions are embedded strings, but no version registry (HP-07) and LLM prose is non-deterministic by design.
- E (audit decision outcome vs later result): possible now (outcomes frozen), richer with HP-01.

**Recommendation:** INV-12 requirement should be defined as **C + D + E first**, with B/A gated on HP-01/HP-02.

---

## 14. Gap Register

| ID | Gap | Phase | Sev | Type | Dependency | Required Before | Evidence | Recommended Resolution |
|---|---|---|---|---|---|---|---|---|
| GAP-01 | INV-12 evaluation artifact contract absent | INV-12 | CRITICAL | CONTRACT | — | INV-12 impl | no module/contract/test exists | Design gate using audited artifact fields; contract tests only first |
| GAP-02 | Durable market-observation store absent | INV-02 | CRITICAL | ARCHITECTURE | — | INV-12 B/A replay; full UI-11 | `MarketObservation` Pydantic-only; no table | Additive immutable observation store with `as_known_at` + hashes |
| GAP-03 | Durable portfolio-snapshot store absent | INV-03 | HIGH | ARCHITECTURE | GAP-02 | INV-12; point-in-time portfolio proof | hash-only on recommendation | Additive immutable snapshot table (payload + hash) |
| GAP-04 | Retention/deletion policy absent | INV-12/ops | CRITICAL | POLICY | — | Multi-user production; INV-12 retention slice | open product-security blocker | Product/security approval |
| GAP-05 | Replay semantics ambiguous in roadmap | INV-12 | HIGH | CONTRACT | GAP-01 | INV-12 contract | roadmap lists A–E without choosing | Product decision: C+D+E first, B/A gated |
| GAP-06 | Canonical security/universe master absent | INV-01/UI-09 | HIGH | CONTRACT | — | real discovery; UI-10 security selector; identity consistency | only bundled `sp500_symbols.json` + holdings | Separate master source contract (future) |
| GAP-07 | Model/methodology version registry absent | INV-07/09 | MEDIUM | CONTRACT | — | INV-12 D replay | version strings embedded only | Registry when INV-12 is designed |
| GAP-08 | Calibration methodology/cohort undefined | INV-12 | MEDIUM | CONTRACT | — | INV-12 calibration slice | deliberately gated | Product definition, min-sample rules |
| GAP-09 | Duplicate baseline engine: `risk_scenarios.py` vs `portfolio_intelligence.py` with divergent identity semantics (one claims RESOLVED from symbol+type, the other UNRESOLVED) | UI-11/INV-03 | HIGH | ARCHITECTURE | — | identity consistency across surfaces | both consume Account/Holding independently; different `security_id`/state | Extract one shared holding→identity + baseline function; document resolution rule |
| GAP-10 | `/portfolio` not in UI-12 certifiable set (407px overflow) | UI-12/portfolio | HIGH | UX/PERFORMANCE | — | UI-12 cert for 11th route | measured 407 vs 390 | Responsive remediation (portfolio-owned) |
| GAP-11 | `/portfolio` mutation controls inside read-only boundary | UI-12/portfolio | MEDIUM | ARCHITECTURE | — | UI-12 separation | add/import/refresh controls present | Gate/separate mutation flows from read-only cert set |
| GAP-12 | `/portfolio` client-side authoritative arithmetic (totals, allocation %, gain %) | portfolio | MEDIUM | SECURITY/ARCHITECTURE | — | browser-authority principle | grep of `page.tsx` reduce/toFixed | Move to server projection or label as display-only (not investment-authoritative) |
| GAP-13 | Populated owner-data proof missing | UI-12 | MEDIUM | TEST | — | UI-12 populated-route proof | hermetic run used empty DB | Deterministic synthetic owner-data seeding + rerun |
| GAP-14 | CPU interaction budget unmeasured | UI-12 | MEDIUM | PERFORMANCE | — | UI-12 cert | route/payload budgets only | Measure interaction CPU budget |
| GAP-15 | CIO archive decision/impl absent | INV-10 | LOW | DECISION | — | only if consumer exists | deferred | Keep deferred; record decision |
| GAP-16 | Multi-user deletion/orphan semantics unplanned (RESTRICT only) | ops | MEDIUM | OPERATIONAL | GAP-04 | multi-user production | RESTRICT FKs | Policy + migration plan with retention approval |
| GAP-17 | Stale expected-head assertion in `test_forecast_migration.py` (`Z14…` vs `AB16…`) | phase-1 | LOW | TEST | — | hygiene | grep + audit | Bounded test-text correction (out of prior phase scope) |
| GAP-18 | Local-user auto-provisioning in scout routes | UI-10 | LOW | SECURITY | — | multi-user rollout | `get_or_create_local_user` | Revisit tenant model before multi-user |
| GAP-19 | Frontend lint debt repo-wide | UI-wide | LOW | UX | — | hygiene | tracker risk | Scheduled bounded cleanup |

---

## 15. Safe to Implement Now (independent, bounded, no architectural risk)

1. **GAP-10** `/portfolio` 390px responsive overflow fix (layout only).
2. **GAP-11** Separate/gate `/portfolio` mutation controls behind an explicit action mode so the read-only surface is cleanly certified.
3. **GAP-13** Synthetic deterministic owner-data seeding in the hermetic harness + populated-route proof.
4. **GAP-14** CPU interaction budget measurement for the current ten-route set.
5. **GAP-9** Unify holding→security identity + baseline computation between `portfolio_intelligence.py` and `risk_scenarios.py` under one shared server function (pure refactor, same outputs).
6. **GAP-17** Correct the stale migration-head assertion text.
7. **UI-12 certification rerun** for the existing ten-route read-only set once 1–4 are green, with the INV-12 boundary recorded as an explicit deferred limitation (personal-use certification does not need INV-12 implemented).
8. **INV-12 design gate** (contract doc + contract tests only) for the evaluation artifact over frozen artifacts (replay meanings C/D/E).

## 16. Do Not Implement Yet (blocked)

1. **INV-12 implementation** (repository/API/calibration/retention) — blocked by GAP-01/02/03/04/05 (artifact contract, durable observations, durable snapshots, retention policy, replay definition).
2. **INV-12 calibration slice** — blocked by GAP-08 (cohort/methodology).
3. **UI-12 full certification** — blocked until GAP-10/11/13/14 are closed and INV-12 boundary recorded; multi-user production claim additionally blocked by GAP-04/16.
4. **INV-10 durable CIO archive** — do not start without a concrete consumer (GAP-15).
5. **UI-10 discovery/security/portfolio selectors and live external web research** — blocked by GAP-06 and missing bounded adapters; current slice is correctly bounded.
6. **UI-11 historical/advanced portfolio risk (volatility, drawdown history, VaR, FX, scenarios)** — blocked by GAP-02/03 and missing approved methodology; do not start.
7. **Multi-user retention/deletion enforcement** — blocked by GAP-04/16.

---

## 17. Recommended Execution Sequence

```text
1. Close harness/portfolio blockers: GAP-10, GAP-11, GAP-13, GAP-14   (independent, §15)
2. Refactor unify: GAP-09 (shared identity/baseline function)          (independent refactor)
3. INV-12 design gate: GAP-01 contract + GAP-05 replay decision
   (contract tests only; no persistence yet)
4. Add durable observation store (GAP-02) and snapshot store (GAP-03)
   as additive immutable migrations — prerequisite to INV-12 impl
5. Implement INV-12 evaluation artifact + repository/read API over
   frozen artifacts (replay C/D/E), owner-scoped, idempotent, no mutation
6. Record INV-12 boundary in UI-12 audit (already present) and rerun
   UI-12 certification at the ten-route (then eleven-route incl. /portfolio)
   read-only set → UI-12 CERTIFIED (personal-use)
7. Product/security: approve retention/deletion policy (GAP-04/16) →
   INV-12 retention slice → multi-user production gate
8. Optional: CIO archive (GAP-15) only if a concrete consumer appears
9. Optional/future: calibration slice (GAP-08), canonical security master (GAP-06),
   UI-10 expanded selectors, UI-11 advanced risk — each behind its own gate
```

Rationale for each step is the gap register: nothing in step 1–3 touches financial semantics; step 4 is the true architectural prerequisite that must precede INV-12 implementation; step 6 is the earliest honest UI-12 certification; steps 7–9 are policy/future.

## 18. Required Decisions (architecture/product owner)

1. **Replay meaning** for INV-12: C+D+E (frozen artifacts) first, with B/A gated — or explicitly all five with HP-01/02 built first?
2. **Retention/deletion policy** for immutable investment history (durations, account deletion, backups, legal/audit holds) — product/security.
3. **CIO archive**: required for any concrete consumer, or permanently deferred?
4. **UI-12 certification boundary**: certify the read-only set with INV-12 listed as a deferred limitation (recommended), or block UI-12 until INV-12 is fully implemented (stricter)?
5. **Canonical security/universe master**: is a durable master in scope (which source/authority), or is the bounded holdings+S&P500 mode the permanent discovery source?
6. **Identity resolution rule** for holdings: resolve from symbol+type only (current `portfolio_intelligence` behavior) or require a verified master (current `risk_scenarios` behavior) — must be exactly one shared rule (GAP-09).
7. **Multi-user scope**: when does the local-user provisioning and RESTRICT-only orphan model get replaced with a tenant/account deletion model?

## 19. Final Certification Path

Current state → **INV-12 complete → UI-12 certified → investment roadmap complete**:

```text
NOW: ten-route read-only matrix green; /portfolio excluded; INV-12 absent
  │ 1. GAP-10/11/13/14 (portfolio fix, seeded data, CPU budget)
  │ 2. GAP-09 unify
  ├─→ UI-12 CERTIFIED for the read-only set + /portfolio (with
  │     INV-12 boundary explicitly deferred)  ← earliest honest certification
  │
  │ 3. INV-12 design gate (contract + replay decision)
  │ 4. GAP-02/03 durable observation + snapshot stores
  │ 5. INV-12 artifact + repository/read API + focused tests
  ├─→ INV-12 COMPLETE (evaluation/replay over frozen artifacts)
  │
  │ 6. GAP-04/16 retention/deletion policy approval → INV-12 retention slice
  ├─→ INVESTMENT ROADMAP COMPLETE (personal-use)
  └─→ multi-user production enablement (policy-dependent, remains gated)
```

The two independent prerequisites that make or break "complete": the **durable observation/snapshot stores** (architecture) and the **retention/deletion policy** (product/security). Neither can be invented by a UI phase.

## 20. Validation Evidence (all read-only, run during audit)

- `git status --short`, `git branch --show-current`, `git log --oneline -12`, `git rev-list --left-right --count @{upstream}...HEAD`
- `./.venv/bin/alembic heads` → single head `AB16a1b2c3d4e5`; `ls alembic/versions/` → 42 files
- Read: `app/investments/{quant,securities,market_observations,portfolio_intelligence,outcome_tracking,recommendation_contracts,discovery,risk_scenarios,scout,committee_contracts,cio_reports}.py`
- Read: `app/models/{investment_persistence,outcome_evaluation,recommendation,investment_scout}.py`
- Grep: observation/snapshot persistence searches (none found), `build_portfolio_snapshot` references, `risk_scenarios` imports (no `portfolio_intelligence` reuse), `sp500_symbols.json` source, scout provider imports (Finnhub/SEC adapters), Phase 1R/external-source search (none found), route auth/If-Match/Idempotency/outcome-persist searches, `/portfolio` client-side arithmetic greps, UI route/e2e inventory, test-file inventory (26 investment-related backend test files; e2e: assistant/discovery/risk/ui12 + assistant.spec)
- Docs read: tracker `PROJECT_STATUS.json` phases 1750–2095, `CURRENT_HANDOFF.md`, UI-12 audit (590 lines), remaining-phases audit (542 lines), consolidated plan, UI-UX roadmap, UI-11 ADR
- No test suite was executed in this audit (running suites is allowed but not required; the audit relies on recorded evidence and source inspection. All listed evidence is static/read-only.)

## 21. Worktree Integrity

- Worktree was **clean** at audit start (`git status --short` → empty).
- The **only** change produced by this audit is **this report file**: `docs/architecture/ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` (an update of the earlier generated report).
- No application code, schema, migration, test, configuration, roadmap, or ADR file was modified. No stage/commit/push was performed.

---

*End of audit. Nothing was fixed; findings are recorded for subsequent implementation in the order in §17.*
# INV-12 DESIGN GATE — Evaluation, Replay, Historical Evidence & Retention (v2)

> **Source:** INV-12 Design Gate v1 (user prompt) + `ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` (comprehensive cross-phase audit).
> **Purpose of v2:** v1 is a strong generic design-gate skeleton but is **not sufficient** — it lets the next session re-derive (or worse, invent) repository-specific decisions the audit already surfaced. This v2 keeps v1's structure and adds the required reads, forced decisions, delta analyses, and repo conventions so the design output is unambiguous.
> **Every addition is marked `[ADDED]`.** Sections without the marker are v1 text, lightly edited only for consistency.

---

## How to use this document

Run this as a **DESIGN-ONLY** gate. The deliverable is a single design document (recommended path: `docs/architecture/ATLAS-INVESTMENT-INV-12-DESIGN.md`) plus the final report in §33's format. **No production code, no migrations, no API implementation, no UI changes, no commit, no push.** The design document must be the only repository modification other than this prompt file itself.

---

## 0. [ADDED] Changes from v1 — why v1 was not sufficient

| # | v1 gap | Consequence if unaddressed | v2 response |
|---|---|---|---|
| 1 | Did not force a choice between the **two existing recommendation/decision/outcome substrates** (goal/forecast vs investment) | INV-12 could unknowingly mix two ID spaces and two immutability regimes | New mandatory **Decision D-1 — Substrate scope** (§2a) |
| 2 | Did not pin the **security-identity rule** for the new stores | Observation/snapshot stores keyed on `security_id` would inherit the current contradictory derivations (INV-03 `RESOLVED` vs UI-11 `UNRESOLVED` for the same holding) and corrupt uniqueness | New mandatory **Decision D-2 — Identity rule** (§2b), tied to GAP-09 |
| 3 | Let the design invent new tables without a **delta analysis vs existing tables** (`investment_outcome_records` already persists outcomes; evidence packets already freeze payloads) | Second stores/duplicate engines by default | Mandatory **delta-analysis table** for every proposed store (§17a) |
| 4 | Did not force **reuse of the existing evaluation engine** (`evaluate_outcome()` / `RecommendationOutcome/v1`) | New parallel evaluation engine | Mandatory **reuse inventory** (§12a) |
| 5 | No repository persistence conventions (Alembic single-head, RESTRICT FKs, append-only trigger precedent, canonical-hash pattern) | New tables would break the established immutable-record pattern | **§27a repository mechanics** |
| 6 | No evaluation **trigger model** (what starts a run) | Implicit scheduler/UI-trigger risk | **§24a trigger model** |
| 7 | No forced **minimal vertical slice** | "Implementation-ready" contract could still allow a sprawling first build | **§29a vertical slice** |
| 8 | Decisions had no **named owners** and no **pre-frozen list** | Next session still decides | **§24b decision table + §24c do-not-decide list** |
| 9 | No explicit relation to **GAP-09/GAP-10..19** (must not fix, but must not be blocked by) | Scope creep or silent dependency | **§1a boundary table** |
| 10 | Incomplete **failure-mode surface** (currency, adjustment basis, provider restatement, vintages) | Evaluations over new stores could silently misbehave | **§26 additions** |

---

## 1. Hard boundary

### DO NOT
- create production code, migrations, models, APIs, routes, UI
- modify existing contracts, tests, persistence, repositories, services
- add evaluation/replay/retention engines or jobs, deletion behavior
- refactor unrelated code
- **fix GAP-09** (identity divergence) or **GAP-10 through GAP-19**
- certify UI-12
- implement the observation store or the snapshot store

### MAY
- inspect repository, contracts, ADRs, roadmap, tests, migrations, persistence
- run read-only tests/commands
- create contract diagrams, decision tables, implementation plans
- create/update **only** the design document deliverable

### [ADDED] §1a — Relationship to audit gaps (must never be blocked by, never fix)
| Audit gap | INV-12 design action |
|---|---|
| GAP-01 (no evaluation artifact) | This gate designs it. |
| GAP-02 (no durable market-observation store) | This gate designs the minimum store (§9). |
| GAP-03 (no durable portfolio-snapshot store) | This gate designs the minimum store (§11). |
| GAP-04 (retention/deletion policy) | Design defines the decision and its owner; does NOT implement (§20). |
| GAP-05 (replay semantics) | Design chooses exactly one scope (§6). |
| GAP-07 (version strings without registry) | Design chooses minimum versioning (§18). |
| GAP-08 (calibration undefined) | Design defers or scopes precisely (§19). |
| GAP-09 (two identity derivations) | Design **freezes the identity rule** the stores will use (D-2). The shared-function refactor is a separate task, sequenced BEFORE store implementation (§2b, §29). |
| GAP-10..14 (portfolio/UI-12) | Explicitly out of scope; INV-12 design must not depend on them. |
| GAP-15 (CIO archive) | Design resolves "not required" with proof unless a dependency appears (§22). |
| GAP-16 (deletion/orphan semantics) | Design defines minimum requirements only (§21). |
| GAP-17..19 | Out of scope. |

---

## 2. Worktree safety

Start with:
```bash
git status --short
git branch --show-current
git log --oneline -10
```
Record starting state. Do not reset/clean/stash/checkout/stage/commit/push. End with `git status --short` and `git diff --check`, proving the only changes are the design document (and this prompt file if it is new).

---

## 3. Read the audit first

Read `docs/architecture/ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` and independently verify GAP-01, GAP-02, GAP-03, GAP-04, GAP-05, GAP-07, GAP-08, GAP-09, GAP-15, GAP-16 before designing around them.

### [ADDED] §3a — Mandatory read inventory (and what each must confirm)
| File | What the design must confirm |
|---|---|
| `docs/architecture/ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md` (§INV-12) | Its existing minimum artifact field list — **reuse/verify it, do not mute it** |
| `docs/architecture/ATLAS-INVESTMENT-CONSOLIDATED-EXECUTION-PLAN.md` | INV-12 ordering and safety statements |
| `docs/architecture/ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md` (Appendices D/G) | Which INV-12 dependency items UI-12 will record as deferred |
| `docs/adr/ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md` | Precedent for identity/currency fail-closed decisions |
| `app/investments/outcome_tracking.py` | Existing `evaluate_outcome`, `RecommendationOutcome/v1`, `MarketObservation` (duplicate of INV-02's) |
| `app/investments/recommendation_contracts.py`, `committee_contracts.py`, `market_observations.py`, `portfolio_intelligence.py`, `quant.py`, `cio_reports.py` | Contracts INV-12 reads from |
| `app/investments/persistence_repository.py`, `persistence_service.py` | How canonical records are projected (never raw payload_json) |
| `app/models/investment_persistence.py` | Committee/evidence/recommendation/decision/outcome tables (there is **no** snapshot or observation table) |
| `app/models/outcome_evaluation.py`, `app/models/recommendation.py` | Append-only trigger precedent + hash-only evidence precedent (goal substrate) |
| `app/models/investment_scout.py` + `tests/test_investment_scout_migration.py` | Immutability test-suite precedent |
| Migrations `T8a1b2c3d4e5_add_decision_journal_substrate.py` (triggers), `W11a1b2c3d4e5_add_investment_outcomes.py`, `Y13a1b2c3d4e5_add_investment_evidence_links.py`, `Z14a1b2c3d4e5_link_outcomes_to_decisions.py`, `AB16a1b2c3d4e5_add_investment_scout_runs.py` | Table shape + immutability + linkage conventions |
| Tests `test_investment_outcome_tracking.py`, `test_investment_persistence_final.py`, `test_investment_persistence_http.py`, `test_outcome_evaluation_migration.py` | What is already proven about decisions/outcomes |

---

## 2a. [ADDED] Decision D-1 — Substrate scope (mandatory, first decision)

The repository has **two independent recommendation/decision/outcome chains**:

1. **Goal/forecast substrate** (Phase 1–3): `Recommendation`, `DecisionJournalEntry`, `OutcomeEvaluation` — append-only via DB triggers, USD fail-closed, deterministic PKs, linked to `forecast_versions`/`goals`. Outcome evaluation evidence is **hash-only**.
2. **Investment substrate** (INV-08..11): `InvestmentRecommendationRecord`, `InvestmentDecisionRecord`, `InvestmentOutcomeRecord`, `InvestmentCommitteeRun/Finding`, `InvestmentEvidencePacket` — owner+id unique constraints, hash CHECK constraints, RESTRICT FKs, extended by the scout tables.

**The design must select exactly one scope and name it in the artifact contract:**

- (a) Investment substrate only — **recommended**: the roadmap's INV-12 is defined over INV-08/09/11 investment artifacts; `RecommendationOutcome/v1` and `evaluate_outcome()` are the natural engine.
- (b) Goal substrate only — would evaluate Phase-1 personal-finance recommendations; not the roadmap's intent.
- (c) Both — only with two artifact families and two engine paths; **explicitly disallowed in v1 scope unless product requires it**.

Declare the choice, and state that **IDs from one substrate must never appear in the other's artifacts**.

---

## 2b. [ADDED] Decision D-2 — Security-identity rule the stores will use (mandatory)

The observation store and snapshot store key on canonical `security_id`. Today two modules derive identity from the same `Account`/`Holding` row differently:

- `portfolio_intelligence._identity` → `atlas-security:{type}:{SYMBOL}`, `SecurityState.RESOLVED` from symbol+type alone;
- `risk_scenarios._identity` → `atlas-unresolved:{type}:{SYMBOL}`, `SecurityState.UNRESOLVED` (no verified master).

**The design must freeze exactly one derivation rule (namespace + state) for all observations and snapshots stored by INV-12**, and require that the GAP-09 shared-identity refactor be completed **before** the stores are populated (sequence in §29), so stored keys can never be invalidated by a later identity change. The frozen rule must answer: what happens to a holding/observation with no symbol, unsupported type, or ambiguous symbol (exact state + namespace), and how `security_id` equality is enforced for lookups (exact string match, never alias match).

---

## 4. Authoritative requirement sources

Same as v1, plus §3a. Precedence when documents disagree:
1. accepted ADR
2. implementation contract/tests
3. current roadmap
4. planning documents

Record every disagreement in the design document; do not silently resolve.

---

## 5. Define INV-12 precisely

> INV-12 is responsible for __________________.

Break "evaluation/replay/calibration/retention" into **explicit sub-capabilities**, each with: definition, owner phase (INV-12 now vs future), required inputs, and required outputs. Evaluation, replay, retention and calibration must each get their own definition paragraph; the design must state which sub-capabilities are in the initial slice.

---

## 6. Resolve replay semantics

For each meaning fill the table, then **choose one** supported by evidence:

| Meaning | Required? | Why? | Required Data | INV-12 Now? | Future? |
|---|---|---|---|---|---|
| A — Recalculate historical result from historical inputs | | | | | |
| B — Reconstruct what the system knew at analysis time | | | | | |
| C — Reconstruct recommendation from frozen analytical inputs | | | | | |
| D — Reproduce methodology/versioned analytical output | | | | | |
| E — Evaluate historical outcome vs later market/portfolio state | | | | | |

**Evidence you must weigh (verified in audit):**
- C is already mostly supported: recommendations persist `input_hash` + `recommendation_hash` + frozen `payload_json`; committee findings and evidence packets freeze their payloads.
- E is partially supported: `RecommendationOutcome/v1` freezes reference/evaluation prices, returns, and hashes — but only for observations supplied at evaluation time.
- B and A are **not** supported today: no durable observation store (`MarketObservation` is Pydantic-only; `outcome_tracking.py` has a second contract definition) and no durable snapshot store (only `portfolio_snapshot_hash` on recommendations).

**Recommendation to evaluate (but verify): C + D + E = initial INV-12 scope; A + B deferred** until HP-01/HP-02 stores exist and product requires point-in-time reconstruction. If you recommend a different boundary, prove why.

---

## 7. Define the INV-12 evaluation artifact

Design the canonical immutable artifact (name it — `InvestmentEvaluationArtifact` or a name consistent with the repo, e.g. following the `investment-*` ID prefix convention). Use v1's field list as a candidate, then for **every field** state: why it exists, authoritative?, immutable?, participates in the hash?, required or nullable.

### [ADDED] §7a — Mandatory delta analysis vs `InvestmentOutcomeRecord`
`investment_outcome_records` already persists outcome IDs, recommendation link + hash, optional decision link, `evaluation_as_of`, `outcome_hash`, frozen `payload_json`. **Answer explicitly:** is the INV-12 evaluation artifact a new table, an extension of this table (additive migration), or persisted in the existing table with the artifact being a read-projection? Justify. Do **not** create a table that duplicates `investment_outcome_records` unless the delta analysis proves the existing table cannot represent the artifact (e.g., replay metadata, input hashes, evaluation window state).

---

## 8. Define evaluation states

Define the lifecycle. Prefer state values consistent with existing enums (`OutcomeState`, `TrackingStatus`, `RiskDataState`). Do not invent states unnecessarily. Answer whether an artifact is ever mutated (prefer append-only; state transitions that are legitimate lifecycle — e.g., `pending → evaluable → evaluated` — must be represented **inside** the append-only record or as new records, never by rewriting the artifact). Choose the canonical chain:

```text
Recommendation → Evaluation Request → Evaluation Artifact → Outcome
```
or a better-supported chain, and justify.

---

## 9. Define the historical market-observation contract (GAP-02)

Design the minimum durable observation model. v1's field list is the candidate — for every field justify it. Determine whether `MarketObservation/v1` from `app/investments/market_observations.py` is persisted as-is or needs a persistence contract (note there is also a *second* `MarketObservation` in `outcome_tracking.py` — **state which contract wins and why**). Decide: immutable? append-only? unique key? duplicates? correction/restatement? provider replacement? source deletion? ownership? public vs private? retention?

**Hard rule (reaffirmed):** the observation store is **not** a market-data product. It stores only what INV-12 evaluation/replay needs (bounded, server-written, no ingestion UI, no provider beyond existing adapters).

---

## 10. Point-in-time semantics

Formally define `observed_at` / `as_of` / `as_known_at` / `retrieved_at` using the existing contracts' rules as the baseline (e.g., `as_known_at >= observed_at` in `outcome_tracking`; `as_of <= retrieved_at` in `market_observations`). Define the historical-evaluation eligibility predicates (e.g., `as_known_at <= analysis_as_of`, `observed_at <= evaluation_as_of`) and prove they prevent future-information leakage. **Check for vintage semantics:** if the same observed value is later restated with a later `as_known_at` (revision), define which vintage an evaluation at time T must use, and how a later re-play detects that the earlier vintage differed.

---

## 11. Define the portfolio-snapshot store (GAP-03)

Design an immutable historical snapshot record **without a second portfolio ledger**. v1's field list is the candidate — justify each. Decide what the snapshot stores: raw holdings only, or calculated allocation/value? The design should store the **minimal frozen state needed for evaluation provenance** (positions + values + identity + hashes at the snapshot instant) and must **not duplicate** the calculation engines (no re-derivation of weights/gain in the store).

### [ADDED] §11a — Delta analysis vs current snapshot handling
Today: `PortfolioSnapshot/v1` (`build_portfolio_snapshot`, INV-03) is computed on demand and **not persisted**; recommendations store only `portfolio_snapshot_hash`. Answer: (1) does the new store persist the full `PortfolioSnapshot` payload + hash per recommendation/decision/evaluation, (2) is the same builder reused (never a second one), and (3) what happens to the existing hash-only linkage — FK, hash-only, or both (§12)?

---

## 12. Relationship: snapshots ↔ recommendations

Define the linkage: FK vs hash-only vs both; immutability; owner; security; temporal validation; and **missing-snapshot behavior** (recommendation whose snapshot record does not exist must be explicitly `unavailable`, never silently re-derived from current holdings).

### [ADDED] §12a — Reuse inventory (no second engine)
List every existing function/contract INV-12 will call, rather than re-implement:
- `app/investments/outcome_tracking.py: evaluate_outcome()`, `track_recommendation()`, `record_decision()`, `RecommendationOutcome/v1`, `MarketObservation`
- `app/investments/portfolio_intelligence.py: build_portfolio_snapshot()`, `PortfolioSnapshot/v1`
- `app/investments/persistence_repository.py: InvestmentRepository` projections
- `app/investments/quant.py` metric calculations only if evaluation needs them
State for each: called as-is, called with additive parameters, or not used (with reason). **INV-12 must not introduce a parallel evaluation or snapshot engine.**

---

## 13. Relationship: observations ↔ evaluation

Decide whether evaluation stores observation IDs, hashes, copied values, or all three. Requirement: a historical evaluation must remain auditable after provider data changes — so the artifact must be **hash-closed** (copied frozen values + hashes), while the store provides richness for re-runs. Define exactly which of the three the artifact carries and why.

---

## 14. Contract chain INV-08 → INV-09 → INV-11 → INV-12

For each transition (`EvidencePacket → CommitteeFinding → Recommendation → HumanDecision → Outcome → Evaluation`) define: required identifier, hash, timestamp, owner, security, provenance, immutability, temporal constraint. State where INV-12 reads authoritative state — **through `InvestmentRepository`/typed service projections, never by parsing arbitrary `payload_json`** (except exactly where the design documents that a frozen payload is the canonical source, e.g., evidence closure).

---

## 15. Decision relationship

Define whether INV-12 evaluates recommendation performance, decision performance, or both. If both, keep four distinct concepts (`Recommendation / Decision / Outcome / Evaluation`) and never collapse them. State how the optional decision link in `InvestmentOutcomeRecord` is used, and how evaluation treats `no_action`/missing decision.

---

## 16. Outcome relationship

Determine what INV-12 consumes from INV-11's `RecommendationOutcome` without duplicating outcome calculations. Define: what INV-11 owns (the frozen outcome), what INV-12 owns (the evaluation artifact + replay over frozen artifacts), what is immutable, what can be re-evaluated (which historical inputs that requires), and any **additional outcome fields** INV-12 needs — documented as INV-12's artifact fields, not as changes to INV-11.

---

## 17. Hash / integrity model

Define deterministic hashes for observations, snapshots, recommendations, decisions, outcomes, evaluations.

### [ADDED] §17a — Repo hash conventions (must follow)
Use the established pattern: `canonical_payload()` = `json.dumps(model_dump(mode="json", exclude={hash_field}), sort_keys=True, separators=(",", ":"))`; `with_hash()` computes `sha256(canonical_payload)` then validates; hash stored as lowercase 64-hex with a DB CHECK constraint (`length(x)=64 AND x=lower(x)`). Define nested-hash ordering and schema-version inclusion per v1 §17, and prove: same ID + different canonical content → different hash → rejected.

---

## 18. Model / methodology versioning (GAP-07)

Choose between: A) embedded version strings suffice for the bounded scope; B) methodology registry; C) model/methodology manifest. Do **not** build a registry for elegance. Minimum for reproducibility: evaluation artifact must carry `evaluation_methodology_version` and must detect a methodology change (replay with a different version → different artifact or explicit `methodology_changed` state). State the choice and what it costs.

---

## 19. Calibration (GAP-08)

Decide whether calibration is in initial INV-12. **Recommendation to evaluate: explicitly defer** — no cohort, minimum-sample, or success-metric definition exists, and the audit marks it deliberately gated. If deferred, write the deferral and the exact trigger for revisiting. Do not create placeholder calibration infrastructure.

---

## 20. Retention / deletion policy (GAP-04)

Do not implement. Answer v1's questions (durations per record type; deletion behavior; immutable records that cannot be physically deleted; derived data that may be deleted/rebuilt; legal/audit hold; backups; personal vs multi-user). **For every row, mark exactly one of:** `PRODUCT DECISION REQUIRED`, `SECURITY DECISION REQUIRED`, `ARCHITECTURE DECISION (can be defined now)`. Where the answer is a decision required, name the owner (the product owner for this single-user project; security review for deletion/legal hold) — do not invent policy.

---

## 21. Multi-user boundary

Identify minimum INV-12 requirements for owner isolation, tenant isolation, account deletion, retention, orphan prevention, authorization — without redesigning tenancy. Note the existing `get_or_create_local_user` convenience in scout routes as a known multi-user caveat (GAP-18) that INV-12 design must not depend on.

---

## 22. CIO archive (GAP-15)

Trace the actual dependency. Expected result: **NOT REQUIRED** — evaluation operates from canonical recommendation/evidence/decision/outcome records and frozen observations/snapshots; archived CIO reports add nothing to replay. Document the proof. If you find a real dependency, say so and classify the archive as required with justification.

---

## 23. Privacy

Answer v1's privacy questions for historical evaluation: portfolio values, account identifiers, holdings, cost basis, research sources, Scout outputs. Classify into private evaluation artifacts / public security data / internal audit data. Note that observations are **public security data** while snapshots are **owner-private**, and evaluation artifacts embedding portfolio state are **owner-private** — define redaction for any UI projection (future).

---

## 24. API / service boundary

Same as v1 (read endpoints: evaluation-by-recommendation/owner/detail, replay status; **no browser-triggered writes**; server/internal evaluator boundary; auth; owner scope; idempotency; immutability; typed responses; error semantics).

### [ADDED] §24a — Evaluation trigger model
Define what initiates an evaluation run and whether it is in scope now or deferred:
- (a) internal on-demand service call (e.g., when an outcome is recorded / at recommendation review) — recommended for the first slice;
- (b) explicit internal command/repository job;
- (c) scheduled background evaluation — **out of scope** (no scheduler exists; background execution is a project-wide safety boundary).
No browser or user-triggered evaluation writes.

### [ADDED] §24b — Required decision table (every D# with an owner)
The design document must end with a decision table:

| ID | Decision | Options | Recommended | Owner | Status (Freeze / Defer) |
|---|---|---|---|---|---|
| D-1 | Substrate scope | investment / goal / both | investment only | product owner | Freeze before implementation |
| D-2 | Identity rule | (frozen derivation) | per §2b | architecture (product owner here) | Freeze before stores |
| D-3 | Replay semantics | A/B/C/D/E | C+D+E now, A+B deferred | product owner | Freeze |
| D-4 | Artifact storage | new table / extend `investment_outcome_records` | delta-analysis-driven | architecture | Freeze |
| D-5 | Snapshot stores | full payload + hash | per §11a | architecture | Freeze |
| D-6 | Evaluation trigger | internal on-demand | (a) | architecture | Freeze |
| D-7 | Calibration | defer | defer | product owner | Freeze (deferral) |
| D-8 | Retention durations | per §20 | PRODUCT/SECURITY | product/security | Defer (require approval) |
| D-9 | CIO archive | required / not | not required unless dependency | product owner | Freeze |
| D-10 | Versioning | strings / registry | per §18 | architecture | Freeze |

### [ADDED] §24c — What the next Codex session must NOT decide
The design document must include a list of decisions that are **pre-frozen** (all of D-1..D-10 above plus identity, state enums, hash serialization, storage delta analyses, trigger model, vertical slice) so the implementer makes zero architectural choices.

---

## 25. Replay security

Same as v1 plus: replay operates against frozen/validated artifacts only; current provider data may never replace historical observations in a replay; methodology and identity changes are detected, not silently applied.

---

## 26. Failure modes

Same as v1 list, plus [ADDED]:
- observation with **incompatible currency** or missing currency → evaluation `UNAVAILABLE` (reuse UI-11 currency semantics; never silently convert)
- **adjustment-basis mismatch** between baseline and evaluation observations (unadjusted vs split-adjusted) → `NOT_COMPARABLE`, unavailable
- **provider restatement / new vintage** after evaluation → original evaluation unaffected (frozen hashes); new vintage available only for new evaluations
- **duplicate evaluation request** (same inputs) → idempotent single artifact
- **conflicting evaluation request** (same recommendation, different window/methodology) → new distinct artifact, never overwrite
- **missing snapshot record** for stored `portfolio_snapshot_hash` → `unavailable`, never re-derive
All fail closed; every failure has a typed reason code consistent with repo error conventions.

---

## 27. Minimum storage design

v1's table, extended with a **Required Delta vs Existing Table** column:

| Store | Required for INV-12? | Immutable? | Owner-scoped? | Historical? | Minimum Fields | Delta vs existing table | Why |
|---|---|---:|---:|---:|---|---|---|
| MarketObservation store | | | | | | no table exists; `MarketObservation` contract-only (+ duplicate in outcome_tracking) | |
| PortfolioSnapshot store | | | | | | only `portfolio_snapshot_hash` column today | |
| Recommendation | | | | | | exists | |
| Decision | | | | | | exists | |
| Outcome | | | | | | `investment_outcome_records` exists | |
| EvaluationArtifact | | | | | | must delta-analyze vs `investment_outcome_records` (D-4) | |
| EvidencePacket | | | | | | exists | |
| CommitteeRun | | | | | | exists | |
| CIOReport | | | | | | not persisted; NOT REQUIRED unless §22 finds a dependency | |

### [ADDED] §27a — Repository persistence mechanics
Every new store must follow existing conventions:
- Alembic **additive** migration, exactly one head maintained, `upgrade`/`downgrade`/re-upgrade round-trip proven per the scout-migration suite pattern
- append-only enforced via **BEFORE UPDATE / BEFORE DELETE triggers on both SQLite and PostgreSQL** (precedent: `T8a1b2c3d4e5` for recommendations/decision_journal_entries) or service-layer immutability with the same test proof
- owner FK `RESTRICT` to `users`, owner+id unique constraint, lowercase-64-hex hash CHECK constraints, ID-shape CHECK constraints
- ownership trigger pattern where cross-owner linkage must be impossible (precedent: `recommendations_goal_owner`)

---

## 28. What not to build

v1's list, plus [ADDED]: **no second market-data product, no second evaluation engine, no scheduler, no calibration infrastructure, no model registry unless §18 chooses B/C, no UI-triggered ingestion, no CIO archive without a dependency, no backtesting/forecast features**.

---

## 29. Implementation order

Produce the dependency-driven sequence. v1's shape is close; [ADDED] the identity-rule refactor and trigger model.

### [ADDED] §29a — Recommended sequence (evaluate against evidence)
```text
0.  Freeze D-1..D-10 decision table (this gate's output)
1.  Approve replay semantics (D-3) and substrate scope (D-1)
2.  Schedule GAP-09 shared holding→identity refactor (D-2) — BEFORE any store population
3.  Freeze INV-12 contracts (artifact, observation-store contract, snapshot-store contract)
4.  Implement durable observation store (additive, immutable, trigger-enforced)
5.  Implement durable portfolio-snapshot store (additive, immutable)
6.  Implement evaluation artifact storage (per D-4 delta analysis)
7.  Implement evaluation/replay engine **reusing evaluate_outcome()** + typed repository
8.  Implement internal evaluation boundary (server-only, no browser writes)
9.  Deterministic + temporal/provenance/security tests (per §30)
10. Certification per §31
11. Retention/deletion slice — ONLY after policy approval (D-8)
```
For every step state its prerequisite and which D# it depends on.

### [ADDED] §29b — Minimal vertical slice
Define the smallest slice that satisfies §31, e.g.: one owner + one security, one provider fixture → observation store writes → snapshot-store write on recommendation persist → one frozen `RecommendationOutcome` → evaluation artifact + deterministic replay hash → owner-scoped read API test. Every later slice is additive.

---

## 30. Test strategy

v1's list, plus [ADDED]:
- **provider restatement/vintage**: same `observed_at`, later `as_known_at` → earlier replay unaffected, new artifact for new window
- **currency/basis failures**: incompatible currency → `UNAVAILABLE`; basis mismatch → `NOT_COMPARABLE`
- **duplicate/conflicting replay**: identical → single idempotent artifact; conflicting window/methodology → distinct artifact, no overwrite
- **corrupted hash**: tampered artifact/observation hash → rejected
- **missing snapshot** referenced by a fingerprint hash → `unavailable`, not re-derived
- **cross-owner observation/snapshot/artifact reads** → 404 non-enumerating
Design tests now; implement none.

---

## 31. Certification criteria

v1's gates plus: separate **INV-12 implementation complete** (contracts, stores, engine, repo, internal boundary, tests all green) from **INV-12 production/multi-user ready** (retention/deletion policy approved, multi-user deletion semantics, populated multi-owner data proof). State that implementation-complete is reachable without the policy; production-ready is not.

---

## 32. Final GO / NO-GO

Select exactly one. **Strengthened rules:**
- **GO** — all D-1..D-10 frozen with owners, delta analyses complete, §29a dependencies valid, replay meaning is single and evidenced.
- **GO WITH EXPLICIT PRODUCT DECISIONS** — architecture defined but D-8 (retention) and any other product decisions await approval; implementation may begin on everything not blocked by those decisions.
- **NO-GO — FOUNDATIONAL CONTRACT MISSING** / **NO-GO — ARCHITECTURE REQUIRES REVISION** — per v1.

Do not select GO merely because the design can be written. **If in doubt → NO-GO with the named missing contract.**

---

## 33. Required final report

Return the v1 format (§1..§26), plus [ADDED] sections:
- **§2a-2b decisions** (substrate scope, identity rule)
- **§7a delta analysis** outcome-records vs artifact
- **§11a snapshot delta analysis**
- **§12a reuse inventory**
- **§24a trigger model, §24b decision table with owners, §24c do-not-decide list**
- **§29a implementation dependency graph, §29b minimal vertical slice**

## 34. Architectural principles

v1's ten principles, plus [ADDED]:
- **11. No second market-data product** — the observation store is bounded to INV-12 needs.
- **12. No second evaluation engine** — INV-12 calls the existing `evaluate_outcome()`/`RecommendationOutcome` chain, extended by stores, never re-implemented.
- **13. No identity drift** — the frozen D-2 identity rule is the only rule the stores accept.

## 35. Most important rule

Do not write INV-12 implementation code. If the roadmap is underspecified: say so. If a storage layer is genuinely required: define the minimum contract (§9/§11/§27). If retention cannot be determined: stop and name the decision owner (D-8). If replay has multiple meanings: choose one only when supported by evidence (D-3). The output must be strong enough that the next Codex session implements INV-12 **without making architectural decisions on its own** — enforce this with §24b/§24c.

**DESIGN ONLY. NO PRODUCTION CODE. NO MIGRATIONS. NO API IMPLEMENTATION. NO UI CHANGES. NO COMMIT. NO PUSH.**
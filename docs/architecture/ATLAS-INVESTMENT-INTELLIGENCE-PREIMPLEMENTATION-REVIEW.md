# Atlas Investment Intelligence — Pre-Implementation Governance Alignment Review

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Review date:** 2026-08-30  
**Review type:** Documentation/control-plane audit only  
**Implementation status:** No implementation authorized by this review

## Scope and sources reviewed

This review examined the current Investment Intelligence planning set:

- `docs/architecture/ATLAS-INVESTMENT-INTELLIGENCE-AUDIT.md`
- `docs/architecture/ATLAS-OPEN-SOURCE-INVESTMENT-STACK.md`
- `docs/architecture/ATLAS-INVESTMENT-INTELLIGENCE-DOMAIN.md`
- `docs/architecture/ATLAS-INVESTMENT-COMMITTEE.md`
- `docs/superpowers/plans/ATLAS-INVESTMENT-INTELLIGENCE-IMPLEMENTATION.md`

It also compared those documents with:

- `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`
- `docs/09-decisions/ADR-001-SPECIALIZED-AGENTS.md`
- `docs/09-decisions/ADR-002-CANONICAL-FINANCIAL-CORE.md`
- `docs/09-decisions/ADR-004-EVENTED-HISTORY.md`
- `docs/10-roadmap/PROJECT_STATUS.json`
- `docs/10-roadmap/PROJECT_STATUS.md`

The repository status is currently **phase-6 complete**, with no active work, an open external multi-user retention/deletion blocker, and an explicit instruction not to begin Phase 7. The plan’s reference to a future Investment Intelligence program is not itself authorization to start it.

## Executive finding

**READY AFTER DOCUMENTATION CHANGES**

The planning set has the correct architectural direction and strong safety boundaries. It consistently keeps deterministic financial authority in Atlas, treats external projects as bounded dependencies, preserves immutable history, reuses the recommendation/decision lifecycle, and ends at user decision rather than execution.

It is not yet governance-complete for autonomous execution of the whole Investment Intelligence program because:

1. The implementation plan previously used `II-A` through `II-L`, which was ambiguous beside Atlas’s global phase numbering and the existing “do not begin Phase 7” status. The corrected plan now uses `INV-01` through `INV-12`.
2. The plan does not explicitly define one user authorization that permits autonomous advancement through the complete approved Investment Intelligence program without confirmation between normal program phases.
3. It does not clearly separate Investment Intelligence program advancement from global Atlas project phase advancement.
4. The required compact investment data-authority invariants are not stated as a canonical block.
5. Conviction is described as deterministic in the Committee design, but the exact contract location, formula, caps, gates, and ownership are not sufficiently fixed.
6. Evaluation was previously concentrated in the late `II-L` phase. The corrected plan now adds a lightweight grounding/evaluation harness as a prerequisite to production-authoritative Committee output, while retaining full evaluation in `INV-12`.

These are documentation/control-plane gaps, not authorization to implement. The audited documents should be updated in one bounded documentation change before any Investment Intelligence implementation begins.

---

## 1. Findings

### 1.1 Architecture reuse and deterministic authority — PASS

The documents correctly establish that Investment Intelligence extends Atlas’s existing architecture rather than creating a parallel platform. They identify the existing Rules Service, Market Intelligence, forecasts/recommendations, decision journal, outcomes, goals, portfolio surfaces, assistant orchestrator, and bounded provider adapters as extension points.

The domain and Committee designs correctly place financial facts, portfolio calculations, valuation, risk, scoring, policy, persistence, and recommendation identity outside the LLM. The Committee Chair emits a draft; deterministic gates validate it before the existing recommendation lifecycle persists it.

**Assessment:** No substantive correction required.

### 1.2 Human decision and no-trading boundary — PASS

The planning set repeatedly establishes:

```text
Analysis → Recommendation → User decision
```

It explicitly excludes broker credentials, order placement, transfers, settlement, money movement, automatic execution, and autonomous rebalancing. The Committee document states that the process ends at `Recommendation → User decision`; the domain and implementation plan repeat this boundary.

The existing global permissions/autonomy model is also compatible: recommendation is distinct from execution, and high-risk actions require separate authorization. The Investment Intelligence program authorization recommended below must not change this product boundary.

**Assessment:** Control is present and consistent.

### 1.3 Open-source boundary — PASS

The audit and open-source stack correctly characterize external projects as candidates for adapters, data ingestion, bounded analytical computation, research, or compatibility evaluation. They do not grant OpenBB, FinceptTerminal, FinRobot, optimizer libraries, backtest engines, vector stores, or agent frameworks ownership of Atlas’s canonical financial state.

The stack document appropriately warns about AGPL/source-available/Commons-Clause terms, provider data terms, and execution-oriented libraries. The implementation plan also defers adoption until a compatibility and license decision is recorded.

**Assessment:** No substantive correction required; the exact phase naming and authorization language should be added to the dependency policy for clarity.

### 1.4 Immutable history and provenance — PASS WITH CLARIFICATION

The documents consistently require immutable/versioned observations, recommendations, decisions, outcomes, evidence, as-of timestamps, data vintage, hashes, and source/calculation/model versions. They also state that later data must not rewrite what was known at the decision time.

The remaining gap is not the principle but its placement: the implementation plan should make the required investment authority invariants and “known-at” rule a short, discoverable contract in the foundation phase and the future canonical ADR.

### 1.5 Current repository governance — IMPORTANT CONTEXT

The canonical status currently says:

- global phase-6 Scenario Lab is complete;
- overall status is complete;
- active work is empty;
- the next bounded task is local release-candidate operations or an explicitly authorized provider-safety/retention review;
- do not begin Phase 7.

The Investment Intelligence plan correctly says it does not alter status and is not implementation authorization. However, its former `Phase II` naming created avoidable ambiguity with global Atlas phases. The implementation plan now uses `INV-01` through `INV-12`.

---

## 2. Contradictions and ambiguities

### 2.1 Phase naming is ambiguous — REQUIRED CHANGE

The implementation plan formerly used `II-A` through `II-L` and headings such as “Phase II-A.” The global repository already uses `phase-0` through `phase-6`, and the handoff explicitly says not to begin Phase 7. The corrected plan now distinguishes `phase-*` global work from `INV-*` Investment Intelligence workstream phases.

**Recommendation:** Rename the Investment Intelligence program phases to:

```text
INV-01 through INV-12
```

Use the names consistently in the plan, task IDs, dependency references, final vertical slice, and future status entries. Reserve `phase-*` for global Atlas project phases.

Suggested mapping:

| Current label | Required label |
|---|---|
| II-A | INV-01 |
| II-B | INV-02 |
| II-C | INV-03 |
| II-D | INV-04 |
| II-E | INV-05 |
| II-F | INV-06 |
| II-G | INV-07 |
| II-H | INV-08 |
| II-I | INV-09 |
| II-J | INV-10 |
| II-K | INV-11 |
| II-L | INV-12 |

The mapping should be stated once at the top of the revised plan, then all internal references should use `INV-*` only.

### 2.2 Program authorization is not explicit enough — REQUIRED CHANGE

The plan currently says implementation requires “explicit authorization of a new Investment Intelligence phase” and that beginning the work requires explicit authorization. That wording permits a phase-by-phase interpretation and does not establish whether one authorization covers the entire approved program.

The desired governance contract should be explicit:

> An explicit user authorization may approve the complete bounded Investment Intelligence program `INV-01 → INV-12` for autonomous advancement in dependency order. The agent may proceed through normal approved program phases without asking for confirmation between phases.

The authorization must be limited to this program and must not authorize:

- automatic trading, broker order placement, or money movement;
- credential acquisition or provider account creation;
- destructive or irreversible production actions;
- unauthorized personal-data access;
- material architecture changes outside approved ADR boundaries;
- unrelated Atlas product work or global phase advancement;
- bypassing validation, review, security, privacy, financial, or policy gates.

The authorization must also say that a global policy stop condition, blocked dependency, failed acceptance criterion, safety issue, mandatory review gate, or explicit user stop instruction overrides autonomous advancement.

### 2.3 Program advancement versus global phase advancement — REQUIRED CHANGE

The plan says the program is a future phase sequence but does not give a formal distinction. Add a dedicated section:

```text
Global Atlas project phase advancement:
  phase-6 → phase-7 (or later) is controlled only by the canonical Atlas roadmap,
  project status, and SOLO_DEVELOPMENT_POLICY.

Investment Intelligence program advancement:
  INV-01 → INV-12 is a bounded workstream sequence inside its separately
  authorized scope. Completing INV-* does not advance, authorize, or alter
  global Atlas phase-* work.
```

The plan must also state that a program phase completion is a material milestone and may require a status update, but status updates must not imply that the global Atlas phase changed.

### 2.4 Required investment data invariants are incomplete — REQUIRED CHANGE

The implementation plan says that Float holdings are not exact historical truth and that incomplete history must not be overclaimed. The other planning documents discuss stale, missing, estimated, and AI-derived values, but no document presents the full compact invariant block as a canonical rule.

Add this exact block to the domain design and implementation plan’s foundation section, and reference it from the future investment ADR:

```text
Current Holding ≠ Historical Investment Truth
Unknown ≠ Zero
Missing ≠ No Change
Stale ≠ Current
Estimated ≠ Observed
LLM Claim ≠ Financial Fact
```

Then define the operational consequence: each distinction must be represented in schemas, calculations, UI/API status, evidence validation, and tests. In particular, missing data must not be converted into neutral values and unknown exposure must not be silently excluded from denominators.

### 2.5 Deterministic conviction scoring is directionally correct but underspecified — REQUIRED CHANGE

The Committee design correctly states that scoring is deterministic and outside the model. It suggests these dimensions:

- opportunity quality: 0–25;
- evidence quality/coverage: 0–20;
- portfolio fit: 0–20;
- risk acceptability: 0–20;
- valuation support: 0–10;
- catalyst/timing support: 0–5.

This is an adequate design direction but remains labeled “suggested,” and the plan does not establish the authoritative contract location. Without that clarification, an implementation agent could let the LLM produce an arbitrary “conviction 91/100.”

**Required contract location:**

- Conceptual authority: `docs/architecture/ATLAS-INVESTMENT-COMMITTEE.md`, section “Scoring” and “Confidence model.”
- Implementation authority: a deterministic Rules Service module introduced in `INV-09`, proposed as `services/rules-service/app/investments/conviction.py` or an equivalently named module approved by the implementation ADR.
- Contract/schema authority: `services/rules-service/app/investments/recommendation_contracts.py` or the existing recommendation schema extension, with the score, components, caps, blockers, formula version, and input hashes.
- Test authority: `services/rules-service/tests/test_investment_conviction.py` and recommendation-gate tests.
- Governance authority: the future canonical investment ADR and a scoring/calibration ADR if weights or thresholds materially change.

**Required scoring behavior:**

1. The LLM may provide role findings, directional interpretations, assumptions, and evidence references only.
2. Atlas computes component scores from validated deterministic metrics, evidence coverage, portfolio fit, risk results, valuation outputs, and catalyst support.
3. Missing required evidence applies an explicit cap or blocks action; it is not silently scored as neutral.
4. Risk/policy/currency/identity/freshness blockers override the numerical score.
5. The final conviction includes component scores, score version, caps, blockers, drivers, uncertainty, and input hashes.
6. The model may explain the score but cannot choose or alter it.
7. Calibration against outcomes is a later evaluation concern; outcome data must not rewrite historical scores.

The exact weights/thresholds should be finalized in the implementation ADR before `INV-09` becomes actionable. The design must nevertheless establish the owner and prohibit model-authored scores now.

### 2.6 Evaluation arrives too late — REQUIRED CHANGE

The current plan places most evaluation in `II-L`/future `INV-12`, after the Committee and recommendation phases. That is too late if `INV-08` can produce a production-authoritative committee draft or if `INV-09` can persist actionable recommendations.

Keep `INV-12` as the full historical replay/backtesting/calibration capability, but add a lightweight evaluation harness before or alongside `INV-08`:

- **Recommended placement:** `INV-01` foundation contract slice, with minimum executable harness completed before `INV-08` exit; alternatively make it a prerequisite sub-slice of `INV-08`.
- **Suggested task:** `INV-01-05 — Establish pre-authority evaluation harness`.
- **Suggested files:**
  - `services/rules-service/tests/investment_evaluations/`
  - `services/rules-service/tests/fixtures/investment_evaluation_cases_v1.json`
  - `services/rules-service/app/investments/evaluation_contracts.py` if runtime contracts are needed
  - `docs/07-engineering/INVESTMENT_EVALUATION_PROTOCOL.md`
- **Minimum checks:**
  - factual accuracy/grounding;
  - evidence coverage;
  - evidence correctness;
  - citation correctness;
  - calculation-reference correctness;
  - structured-output validity;
  - recommendation consistency under replay;
  - confidence-score reproducibility and calibration placeholders;
  - stale-data detection;
  - hallucination/invented-number detection;
  - Bull/Bear disagreement and dissent preservation;
  - prompt-injection and ownership isolation.

`INV-08` and `INV-09` must not be production-authoritative until the minimum harness passes its documented thresholds. `INV-12` can later add historical datasets, outcome calibration, walk-forward evaluation, and deeper backtesting.

### 2.7 Human boundary wording is consistent but should be canonicalized — OPTIONAL/RECOMMENDED

The boundary is present in all relevant documents, but each uses slightly different wording. Add one canonical block to the implementation plan and reference it from the other Investment Intelligence documents:

```text
Analysis
  → Recommendation
  → User Decision

Never:
  Analysis
    → Recommendation
    → Automatic Execution
```

This is a clarity improvement, not a substantive safety defect.

### 2.8 Open-source wording is consistent but should name the authority rule — OPTIONAL/RECOMMENDED

The open-source document and plan are aligned. Add a short rule to the implementation plan:

> External projects may provide adapters, data, research, or bounded calculations. Atlas validates their outputs and remains the canonical source of user financial truth, portfolio state, recommendation authority, provenance, authorization, and decisions.

This makes the boundary discoverable to coding agents without requiring them to infer it from several documents.

---

## 3. Missing controls

### 3.1 Program authorization record

The planning set needs a defined authorization record, even if its eventual storage remains a project-control-plane concern rather than a production database row. It should identify:

- program name and scope: `INV-01 → INV-12`;
- authorizing user and timestamp;
- allowed repository/worktree scope;
- permitted dependency and provider boundaries;
- explicit no-execution restrictions;
- whether normal phase transitions require no further confirmation;
- global stop conditions that remain in force;
- expiration/revocation behavior;
- relationship to global Atlas phase status.

Do not implement this record in this audit. Define it in the plan and future authorization ADR.

### 3.2 Entry/exit gate for each program phase

The plan lists acceptance criteria, but a program-level autonomous runner needs a uniform gate:

```text
Entry gate:
  dependency phases complete, authorization active, scope unchanged,
  required ADRs approved, blockers clear, fixtures available.

Execution:
  bounded task sequence under the phase’s risk tier.

Exit gate:
  acceptance criteria pass, focused evidence exists, review requirements pass,
  rollback understood, no mandatory stop condition, next phase is approved
  by the program authorization.
```

This does not override the canonical `SOLO_DEVELOPMENT_POLICY`; it operationalizes it for the named workstream.

### 3.3 Stop-condition precedence

The plan should explicitly say:

1. `SOLO_DEVELOPMENT_POLICY.md` is globally authoritative.
2. Security, ownership, financial-correctness, privacy, migration, immutable-history, credential, and execution boundaries cannot be weakened by program authorization.
3. A material architecture change, scope ambiguity, unresolved high-risk blocker, or policy-mandated stop pauses the program.
4. Normal bounded corrections within an authorized outcome remain allowed under the global policy.
5. The user can revoke or narrow program authorization at any time.

### 3.4 Early evaluation gate

Add a named acceptance criterion that the Committee cannot become production-authoritative before the minimum evaluation harness passes. This is distinct from full `INV-12` historical evaluation.

### 3.5 Conviction score caps and blockers

The plan needs an explicit placeholder for deterministic confidence/conviction caps. Examples that should be specified before implementation:

- unresolved security identity: no actionable conviction;
- ambiguous currency: no actionable conviction;
- insufficient portfolio coverage: no portfolio-fit conviction;
- stale required price/fundamentals: capped or blocked by horizon policy;
- missing required evidence: WATCH/abstention or documented cap;
- blocking risk/policy result: no actionable BUY/ADD/REDUCE/SELL;
- unsupported backtest: excluded from score rather than treated as neutral.

Exact thresholds belong in the scoring ADR, but the control must be in the plan.

---

## 4. Required changes

These were the required changes identified by the original audit. They are applied by the documentation correction task; this review remains an audit record and is not itself rewritten as an approval.

1. Rename the Investment Intelligence phase family everywhere from `II-A…II-L` to `INV-01…INV-12` (applied to the implementation plan).
2. Add a program authorization section permitting one explicit authorization for autonomous advancement through the complete approved `INV-01 → INV-12` sequence, without confirmation between normal phases (applied to the implementation plan).
3. Explicitly state prohibited actions and global stop-condition precedence in that authorization section (applied to the implementation plan).
4. Add a formal distinction between global Atlas `phase-*` advancement and Investment Intelligence `INV-*` advancement (applied to the implementation plan).
5. Add the six investment data-authority invariants exactly as specified (applied to the audit, domain, and implementation plan).
6. Add the deterministic conviction ownership contract, including its authoritative future implementation path, score components, caps/blockers, and prohibition on LLM-authored conviction (applied to the Committee design and implementation plan).
7. Add a lightweight evaluation harness before/alongside Committee authority and make it an `INV-08`/`INV-09` entry or exit gate; retain full `INV-12` evaluation (applied to the implementation plan).
8. Add uniform program entry/exit gates and stop-condition precedence referencing, not replacing, `SOLO_DEVELOPMENT_POLICY.md` (applied to the implementation plan).

These are documentation-only changes. They should not alter the current roadmap/status until the user explicitly authorizes the program.

---

## 5. Optional changes

1. Add the canonical `Analysis → Recommendation → User Decision` block to every Investment Intelligence document.
2. Add a one-paragraph external-dependency authority rule to the audit, open-source stack, domain, Committee, and implementation plan.
3. Add a compact glossary distinguishing `phase-*`, `INV-*`, task IDs, analysis runs, recommendation lifecycle states, and user decisions.
4. Add a plan-level dependency graph showing which `INV-*` phases may run in parallel after their entry gates.
5. Add an explicit “documentation set version” and cross-document consistency checklist.
6. Add a separate scoring/calibration ADR placeholder to the implementation plan.

---

## 6. Documents that should remain unchanged

### `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`

Do **not** rewrite, replace, or duplicate this policy. It is the canonical global autonomous-development policy. Investment Intelligence documents must reference it and add only program-specific scope/authorization details.

### `docs/10-roadmap/PROJECT_STATUS.json`

Do not update it for this audit. Current status correctly says global phase-6 is complete, active work is empty, and Phase 7 must not begin. A future authorized program start is a material status event and should update status through the canonical tracker workflow at that time.

### `docs/10-roadmap/PROJECT_STATUS.md`

This generated document should remain unchanged until canonical JSON status changes. Do not manually edit it for planning alignment.

### Existing ADRs

ADR-001, ADR-002, and ADR-004 should remain unchanged. They already establish specialized agents, deterministic financial authority, and immutable history. Add a future Investment Intelligence ADR that references them rather than weakening or rewriting them.

### Implementation code, schemas, migrations, APIs, dependencies

No implementation artifacts should be modified by this audit. The requested corrections belong only in the planning/documentation set after explicit approval to apply them.

---

## 7. Exact recommended edits

The following are proposed text changes for a later documentation-only correction. They are intentionally not applied by this audit.

### 7.1 Plan title and phase vocabulary

Add near the top of `docs/superpowers/plans/ATLAS-INVESTMENT-INTELLIGENCE-IMPLEMENTATION.md`:

```markdown
## Program phase vocabulary

Investment Intelligence uses the independent program phase IDs `INV-01` through
`INV-12`. These IDs are not Atlas global project phases. The global roadmap
continues to use `phase-*` IDs. Completing an `INV-*` phase does not advance or
authorize any unrelated Atlas global phase.

| Program ID | Capability |
|---|---|
| INV-01 | Investment Intelligence foundation |
| INV-02 | Market/security data |
| INV-03 | Portfolio intelligence |
| INV-04 | Fundamental research |
| INV-05 | Technical research |
| INV-06 | Macro intelligence |
| INV-07 | Quant research |
| INV-08 | AI Investment Committee |
| INV-09 | Investment recommendations |
| INV-10 | Daily/weekly/monthly CIO reports |
| INV-11 | Recommendation tracking |
| INV-12 | Backtesting and evaluation |
```

Then replace all `II-*` references in that plan with the corresponding `INV-*` IDs.

### 7.2 Program authorization

Add after the dependency-gates section:

```markdown
## Program-level authorization

A separate, explicit user authorization may approve the complete bounded
Investment Intelligence program `INV-01 → INV-12` for autonomous advancement in
dependency order. Once that authorization is active, the agent may proceed
through normal approved `INV-*` phases without requesting confirmation between
those phases.

This authorization applies only to the approved Investment Intelligence
program. It does not authorize global Atlas phase advancement, unrelated
product work, or any action outside the approved task/file/dependency scope.

It never authorizes:

- automatic trading, broker order placement, rebalancing, or money movement;
- broker/provider credential acquisition or account creation;
- destructive or irreversible production actions;
- unauthorized personal-data access or cross-owner disclosure;
- bypassing financial, security, privacy, ownership, migration, provenance,
  review, validation, or approval gates;
- material architecture changes not approved by an ADR;
- changing the canonical `SOLO_DEVELOPMENT_POLICY.md`.

The global Atlas governance policy remains authoritative. Its mandatory stop
conditions, blocked dependencies, failed safety or acceptance gates, material
scope changes, and explicit user stop/revocation instructions pause or end
program advancement. Normal bounded corrections within the authorized outcome
remain governed by that policy.
```

### 7.3 Data-authority invariants

Add to the foundation/domain-authority sections:

```markdown
## Investment data-authority invariants

Current Holding ≠ Historical Investment Truth
Unknown ≠ Zero
Missing ≠ No Change
Stale ≠ Current
Estimated ≠ Observed
LLM Claim ≠ Financial Fact

These distinctions are mandatory in contracts, calculations, evidence status,
API/UI presentation, and tests. The system must preserve unknown and missing
states rather than silently converting them into zero, neutral, or unchanged
values.
```

### 7.4 Deterministic conviction contract

Add to the Committee design and plan:

```markdown
## Deterministic conviction authority

The LLM never chooses, edits, or reports an authoritative conviction score.
Agents provide grounded findings, evidence references, assumptions, and
uncertainty. Atlas computes conviction deterministically from versioned inputs:

- opportunity quality (0–25);
- evidence quality/coverage (0–20);
- portfolio fit (0–20);
- risk acceptability (0–20);
- valuation support (0–10);
- catalyst/timing support (0–5).

The implementation owner is a Rules Service calculator, proposed at
`services/rules-service/app/investments/conviction.py`, with a versioned
contract in the investment recommendation schemas. It records components,
weights, caps, blockers, drivers, uncertainty, and input hashes. Missing
required evidence, invalid currency/identity, stale required inputs, partial
portfolio coverage, or blocking risk/policy results cap or block conviction;
these states are never treated as neutral evidence. The model may explain the
server-computed result only.
```

### 7.5 Early evaluation harness

Add to the plan’s foundation and Committee sections:

```markdown
## Pre-authority evaluation gate

Before `INV-08` or `INV-09` can become production-authoritative, Atlas must pass
a lightweight evaluation harness covering factual accuracy, evidence coverage
and correctness, citation correctness, calculation-reference correctness,
structured-output validity, replay consistency, confidence reproducibility,
stale-data detection, hallucination/invented-number detection, Bull/Bear
disagreement preservation, prompt-injection resistance, and ownership
isolation. Full historical replay, outcome calibration, and backtesting remain
in `INV-12`.
```

### 7.6 Canonical human boundary

Add to the plan and reference from the other documents:

```markdown
## Human decision boundary

Analysis
  → Recommendation
  → User Decision

Never:
  Analysis
    → Recommendation
    → Automatic Execution
```

### 7.7 Uniform phase gates

Add to the plan:

```markdown
## Program phase gates

Each `INV-*` phase has an entry gate, bounded task sequence, and exit gate.
Entry requires dependencies complete, program authorization active, required
ADRs approved, scope unchanged, blockers clear, and fixtures available. Exit
requires acceptance criteria, focused validation evidence, review requirements,
rollback/recovery understanding, and no mandatory global stop condition.
These gates operationalize the canonical `SOLO_DEVELOPMENT_POLICY.md`; they do
not replace or strengthen it.
```

---

## 8. Final readiness assessment

### Current state

The Investment Intelligence architecture is substantively sound and safe in its core boundaries. The repository’s current global status is also clear: Phase 6 is complete, no active work is tracked, and Phase 7 must not begin.

### Readiness decision

**READY AFTER DOCUMENTATION CHANGES**

Do not begin implementation yet. First apply the required documentation corrections above in one bounded documentation-only change, then rerun a consistency audit. After that, implementation may begin only when the user explicitly authorizes the Investment Intelligence program and the canonical tracker records the material program start.

If the user authorizes the entire program, the agent may autonomously advance through the approved `INV-01 → INV-12` sequence without asking for confirmation between normal phases, subject to the global policy’s mandatory stop conditions, validation/review requirements, blockers, scope limits, and explicit no-trading/no-credential/no-destructive-action boundaries.

The authorization of `INV-*` does not authorize global Atlas phase advancement or unrelated product work. The user remains the final decision-maker for every investment recommendation:

```text
Analysis → Recommendation → User Decision
```

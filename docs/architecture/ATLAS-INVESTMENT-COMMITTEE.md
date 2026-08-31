# Atlas AI CFO — AI Investment Committee Design

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Design date:** 2026-08-30  
**Status:** Architecture design only; no implementation approval  
**Related authority:** `ATLAS-INVESTMENT-INTELLIGENCE-DOMAIN.md`, `ATLAS_AGENT_ARCHITECTURE.md`, `AGENT_OVERVIEW.md`, `INVESTMENT_AGENT.md`, `RISK_AGENT.md`, ADR-001, ADR-002, ADR-004.

> **Hard boundary:** The committee analyzes and recommends. It never places orders, selects a broker, transfers money, or executes trades. The process ends at **Recommendation → User decision**.

## Design decision

Atlas should extend its existing bounded specialist-agent architecture and `assistant_orchestrator`, not introduce an unrelated multi-agent framework. The Investment Committee is an orchestration profile inside Atlas’s existing agent/decision/recommendation boundaries:

```text
User request or scheduled analysis
  → authenticated, owner-scoped analysis context
  → validated evidence packet + deterministic calculations
  → specialist findings
  → bull/bear challenge
  → committee synthesis
  → deterministic policy/evidence gates
  → existing Recommendation lifecycle and decision journal
  → user decision
```

Agents are probabilistic interpreters. Atlas-owned deterministic services remain authoritative for facts, calculations, suitability, policy, persistence, and recommendation identity.

---

## 1. Agent responsibilities

### 1.1 Agent necessity and placement

The requested roles are useful as **responsibilities**, but they should not initially become nine independent long-running services or autonomous personas. Atlas should begin with a small number of bounded specialist passes, using role-specific prompts/contracts and the existing orchestrator. Roles can be combined when inputs and evaluation criteria overlap, while their outputs remain separately attributable.

| Role | Necessary? | Initial responsibility | Authority |
|---|---|---|---|
| Fundamental Analyst | Yes for equity/company analysis | Interpret validated statements, filings, earnings, profitability, balance sheet, cash flow, guidance, valuation outputs, management/capital-allocation evidence, and competitive-position evidence. | Cannot create financial facts or valuation numbers. |
| Technical Analyst | Conditional | Interpret deterministic trend, momentum, volatility, volume, relative-strength, support/resistance, and regime metrics when the requested horizon makes them relevant. | Cannot turn a chart pattern into a guaranteed forecast. |
| Macro Analyst | Conditional | Interpret validated rates, inflation, employment, GDP, liquidity, monetary-policy, yield-curve, regime, and sector-context evidence. | Must disclose timing, uncertainty, and weak causal inference. |
| Quant Analyst | Conditional, later | Interpret validated factor signals, historical behavior, risk-adjusted metrics, correlations, and leakage-controlled backtest outputs. | Cannot treat backtests as proof or bypass portfolio fit. |
| Portfolio Analyst | Required for every portfolio-affecting recommendation | Answer what the proposed exposure does to this user’s portfolio, goals, liquidity, concentration, diversification, risk, and existing holdings. | Uses deterministic portfolio-impact calculations; does not recompute them in prose. |
| Risk Analyst | Required for every actionable recommendation | Identify downside, concentration, thesis failure, tail, liquidity, valuation, data-quality, and implementation risks. | Has veto/escalation power over unsafe or unsupported action drafts, but cannot authorize execution. |
| Bear Analyst | Required for actionable recommendations and challenges | Attack the thesis, identify contrary evidence, hidden assumptions, failure modes, and reasons to HOLD/WATCH/REDUCE/SELL instead. | Must cite evidence or label a concern as a hypothesis/question. |
| Bull Analyst | Required when a positive action is considered; useful for all reviews | Build the strongest evidence-backed case, identify catalysts, upside conditions, and what would make the opportunity fit the portfolio. | Cannot omit material contrary evidence. |
| Committee Chair | Required | Reconcile findings, preserve dissent, state uncertainty, select a recommendation action only after deterministic gates, and produce the structured user-facing synthesis. | Cannot override policy, evidence, authorization, or no-trading boundaries. |

### 1.2 Recommended initial profiles

To minimize duplicated calls and inconsistent conclusions, the first implementation should expose these logical profiles:

1. **Fundamental profile:** Fundamental Analyst; optionally incorporates Macro context.
2. **Market profile:** Technical Analyst; optionally incorporates Quant signals once available.
3. **Portfolio/Risk profile:** Portfolio Analyst and Risk Analyst as distinct outputs because portfolio fit and risk refusal need separate evaluation.
4. **Adversarial profile:** Bull Analyst and Bear Analyst in a controlled pair/debate pass.
5. **Chair profile:** Committee Chair, invoked only after all required evidence and calculations are present.

This is a logical decomposition, not a commitment to separate processes, models, or queues. The existing orchestrator may invoke profiles sequentially or in bounded parallelism when isolation, tracing, and cost controls are satisfied.

### 1.3 Existing Atlas agents

The Investment Committee extends, rather than replaces, the existing:

- **Investment Agent:** portfolio alignment, allocation, diversification, performance, risk, fees, tax-aware context, and rebalancing candidates.
- **Risk Agent:** concentration, liquidity, debt, unusual activity, stale data, policy violations, and tail-risk escalation.
- **Wealth Agent:** goals, forecasts, retirement probability, and long-term financial impact.
- **Opportunity Agent:** candidate discovery and opportunity framing, subject to evidence and policy gates.
- **Orchestrator:** context assembly, agent selection, finding merge, conflict handling, and response composition.

The specialist analyst roles in this document should be implemented as bounded capabilities within these established ownership boundaries unless later evaluation proves a separate role is needed.

---

## 2. Agent inputs

Every committee run receives an immutable, owner-scoped `InvestmentCommitteeContext` assembled by deterministic Atlas services:

```text
InvestmentCommitteeContext
  ├─ run_id and schema/policy versions
  ├─ owner scope and authorized account scope
  ├─ task: security review | holding review | portfolio review | challenge
  ├─ subject Security/Company/Portfolio reference
  ├─ portfolio_snapshot_id/hash and as_of timestamp
  ├─ goal, horizon, liquidity, risk-capacity, and policy context references
  ├─ validated evidence packet IDs/hashes
  ├─ deterministic analytics and calculation references/results
  ├─ data freshness, coverage, currency, and reconciliation status
  ├─ prior recommendation/decision/outcome references, if authorized
  ├─ allowed read-only tools and call/time budgets
  ├─ prohibited actions
  └─ model/prompt/persona/version metadata
```

### 2.1 Input rules

- Agents receive validated facts and bounded excerpts, not unrestricted database access.
- Account identifiers, tax-lot details, and raw transactions are minimized and exposed only when required by the role and authorized.
- External filings, news, transcripts, and web content are treated as untrusted data, never as instructions.
- Client-supplied prices, holdings, evidence, or recommendation IDs cannot override canonical Atlas context.
- Missing, stale, ambiguous, conflicting, or incomplete inputs are explicit fields in the context.
- The orchestrator records the exact input hashes used by each role.

### 2.2 Required context by role

| Role | Required inputs |
|---|---|
| Fundamental | Security/company identity; validated statements/facts; filings; earnings; valuation calculations; source quality and period/vintage metadata. |
| Technical | Point-in-time price/volume history; benchmark; calculated indicators; window; corporate-action and stale-data status. |
| Macro | Macro series and event observations; effective/as-known-at timestamps; sector/benchmark context; source quality. |
| Quant | Versioned factor signals; return/risk/correlation data; point-in-time dataset; backtest metadata, leakage checks, baselines, and solver status. |
| Portfolio | Immutable portfolio snapshot; holdings/positions; exposure classifications; deterministic portfolio analytics; goals, liquidity, and policy constraints. |
| Risk | All relevant evidence and calculations, including omissions, conflicts, data quality, liquidity, concentration, and policy results. |
| Bull/Bear | Prior validated findings and evidence packet; assumptions; deterministic valuation/risk/portfolio outputs; no ungrounded external research. |
| Chair | All specialist outputs, evidence coverage, conflicts, deterministic gates, portfolio/goal impact, and prior decision context. |

---

## 3. Agent outputs

All outputs are strict, versioned structured objects. Free-form text is an explanation field, not an authority source.

### 3.1 Common finding contract

```text
AgentFinding
  ├─ finding_id / run_id / role / agent_version
  ├─ subject reference
  ├─ conclusion_type
  ├─ claim: concise statement
  ├─ claim_class: observed_fact | calculated_metric | assumption | interpretation | uncertainty
  ├─ direction: supports | contradicts | neutral | unknown
  ├─ magnitude/metric reference, if applicable
  ├─ evidence_refs[]
  ├─ calculation_refs[]
  ├─ assumptions[]
  ├─ limitations[]
  ├─ confidence: calibrated score + qualitative band
  ├─ requested_calculations[]
  ├─ conflicts[]
  └─ abstained: boolean + reason
```

A role may return multiple findings, but each material claim must be independently traceable. The agent must identify when it lacks sufficient evidence rather than fill gaps.

### 3.2 Role-specific outputs

- **Fundamental:** quality/growth/profitability/balance-sheet/FCF/valuation findings, evidence gaps, and thesis drivers.
- **Technical:** trend/momentum/volatility/volume/regime interpretation, signal validity, and invalidation levels as referenced calculations—not invented prices.
- **Macro:** regime/context findings, transmission assumptions, affected sectors, and uncertainty.
- **Quant:** signal findings, historical/risk metrics, backtest limitations, robustness, and whether the result is admissible as evidence.
- **Portfolio:** baseline and hypothetical impact references, diversification/concentration effects, goal/liquidity fit, and recommendation direction.
- **Risk:** risk register with severity, likelihood band, exposure basis, evidence, mitigation, and action-blocking status.
- **Bull/Bear:** strongest supporting/contradicting case, assumptions, catalysts or failure conditions, and evidence coverage.
- **Chair:** `RecommendationDraft` or `Abstention`, never a directly persisted recommendation.

### 3.3 Structured recommendation draft

The chair’s draft must contain:

```text
RecommendationDraft
  ├─ subject security/portfolio reference
  ├─ action: BUY | ADD | HOLD | REDUCE | SELL | WATCH
  ├─ conviction/confidence and drivers
  ├─ time horizon
  ├─ price/reference context and as_of basis
  ├─ thesis
  ├─ bull case
  ├─ bear case
  ├─ catalysts
  ├─ risks
  ├─ invalidation conditions
  ├─ deterministic valuation summary
  ├─ expected return/risk ranges with method and assumptions
  ├─ portfolio impact
  ├─ goal impact
  ├─ evidence references and coverage
  ├─ dissenting opinions
  ├─ data gaps and uncertainty
  ├─ review/expiry conditions
  └─ proposed next calculation or user question, if needed
```

The orchestrator validates this draft, runs deterministic gates, and only then delegates to the existing recommendation application/lifecycle service. A model response alone cannot become an `InvestmentRecommendation`.

---

## 4. Evidence requirements

### 4.1 Evidence classes

The committee reuses the domain evidence model:

- canonical portfolio/transaction/position state;
- deterministic portfolio, valuation, performance, risk, and quantitative calculations;
- market observations;
- financial facts/statements;
- SEC filings and other primary records;
- earnings events/results;
- news and transcripts;
- analyst/consensus information;
- prior Atlas recommendations, user decisions, and outcomes.

### 4.2 Claim discipline

Each claim must be classified as:

1. **Observed fact:** directly supported by a source record and timestamp.
2. **Calculated metric:** produced by a named deterministic calculation over identified inputs.
3. **Assumption:** explicit scenario or modeling assumption.
4. **Interpretation:** analyst synthesis grounded in cited facts/metrics.
5. **Uncertainty:** missing data, conflict, model limitation, or confidence limitation.

Agents must never present an assumption or interpretation as an observed fact. A material numerical claim without an evidence or calculation reference is invalid.

### 4.3 Evidence gate

Before chair synthesis, the orchestrator verifies:

- every required evidence category for the requested action is present or explicitly omitted;
- all citations resolve to the supplied packet and exact source/version;
- calculations are finite, currency-valid, reproducible, and tied to the same portfolio snapshot;
- freshness and as-of rules pass;
- source conflicts are surfaced;
- portfolio coverage is sufficient for portfolio claims;
- point-in-time rules pass for historical/quantitative evidence;
- no external text has been interpreted as an instruction;
- evidence does not include credentials or unauthorized user data.

A failed gate produces an abstention, unavailable analysis, or `WATCH` with a concrete evidence requirement. It must not be silently repaired by the model.

---

## 5. Orchestration

### 5.1 Normal review flow

```text
1. Receive authenticated user request or approved analysis trigger.
2. Resolve subject and owner/account scope.
3. Build immutable portfolio, goal, policy, and evidence context.
4. Run deterministic calculations and quality/freshness checks.
5. Select only necessary analyst profiles for the subject and horizon.
6. Invoke independent specialist analyses with bounded context.
7. Validate schemas, citations, claim classes, and output limits.
8. Merge findings by subject and claim; preserve provenance and conflicts.
9. Invoke Bull/Bear debate when an actionable or materially disputed result is possible.
10. Invoke Committee Chair with the merged packet.
11. Run deterministic recommendation, suitability, risk, currency, freshness, and coverage gates.
12. Persist only a valid recommendation through the existing immutable lifecycle.
13. Present evidence, assumptions, dissent, risks, and review conditions.
14. Await a separate user decision; do not execute.
```

### 5.2 Parallelism and ordering

Fundamental, Market, Macro, Portfolio, and Risk profiles can be independent after context assembly. Bull/Bear must receive the same frozen packet and should not silently fetch divergent facts. The Chair runs after specialist validation and challenge outputs. Parallel execution is optional and must respect provider budgets, tracing, deterministic replay, and bounded latency.

### 5.3 Existing Atlas integration

The committee belongs behind the existing `assistant_orchestrator`/agent boundary and above deterministic services. The existing assistant currently uses an allowlisted tool registry and local Ollama client; investment tools should follow the same principle but must be read-only and evidence-returning. Existing recommendation, decision journal, history, and outcome services remain authoritative. No agent writes canonical facts or recommendation records directly.

### 5.4 Run identity and replay

A run is identified by owner, task, subject, frozen context hashes, prompt/persona versions, model version, and policy version. Identical inputs should be idempotently replayable. Changed market data, portfolio state, evidence, model, or policy produces a new run and potentially a superseding recommendation; it never mutates the prior record.

---

## 6. Conflict resolution

### 6.1 Conflict taxonomy

Conflicts must distinguish:

- source disagreement;
- stale versus current observation;
- period/vintage mismatch;
- calculation/method mismatch;
- unsupported interpretation;
- genuine analyst disagreement;
- missing evidence mistaken for negative evidence.

### 6.2 Resolution order

1. Validate identity, ownership, timestamps, units, currency, and source integrity.
2. Prefer canonical Atlas portfolio state for user holdings and positions.
3. Prefer validated deterministic calculations over model arithmetic.
4. Prefer primary filings/official records for material company facts, subject to restatement/vintage rules.
5. Reconcile equivalent observations only through a versioned deterministic policy.
6. Preserve irreconcilable conflicts rather than averaging them away.
7. Ask the Chair to synthesize uncertainty and select `WATCH`/abstention when conflict affects action suitability.

### 6.3 Chair constraints

The Chair may select a recommendation only when:

- required evidence and calculations pass;
- no blocking risk or policy violation remains;
- the action is semantically consistent with the portfolio state;
- dissent and material contrary evidence are disclosed;
- confidence reflects evidence quality and agreement;
- the result is within the no-execution contract.

The Chair cannot resolve a failed deterministic gate by majority vote. Risk has a blocking escalation for unsafe actionable drafts; it does not have execution authority.

---

## 7. Scoring

Scoring is deterministic and performed outside the model. The committee produces inputs and interpretations; Atlas computes the final score from validated dimensions.

### 7.1 Suggested score dimensions

```text
Opportunity quality       0–25
Evidence quality/coverage 0–20
Portfolio fit             0–20
Risk acceptability        0–20
Valuation support         0–10
Catalyst/timing support   0–5
Total                    0–100
```

The exact weights require fixtures and an ADR before implementation. They must be configurable by version, not hidden in prompts.

### 7.2 Action mapping

A score does not mechanically determine an action. It is one input to policy-gated action semantics:

- **BUY:** sufficient opportunity and fit for a new exposure; no position or explicitly new exposure.
- **ADD:** positive incremental case with acceptable concentration and marginal risk.
- **HOLD:** maintain exposure where evidence supports no change or action is not justified.
- **REDUCE:** risk, concentration, fit, valuation, or liquidity case supports decreasing exposure.
- **SELL:** exit case is strong or thesis is invalidated, subject to tax/liquidity caveats.
- **WATCH:** material candidate or concern exists but evidence, confidence, suitability, or trigger confirmation is insufficient.

A failed gate overrides score and yields `WATCH`, abstention, or no recommendation.

### 7.3 Dissent and score integrity

Store component scores, missing-data penalties, risk blockers, specialist direction, and dissent. Do not hide disagreement in one confidence number. A high score with poor evidence coverage must not become a high-conviction recommendation.

---

## 8. Confidence model

Confidence is a calibrated statement about the reliability of the analysis under its stated assumptions, not the probability that a price target will be achieved.

### 8.1 Confidence inputs

Atlas should calculate confidence from:

- evidence coverage and source quality;
- freshness and point-in-time validity;
- portfolio completeness and reconciliation status;
- deterministic calculation validity;
- agreement/disagreement among independent findings;
- model calibration on historical evaluation cases;
- sensitivity to assumptions;
- risk and uncertainty severity;
- subject/horizon suitability.

### 8.2 Confidence rules

- Missing required evidence caps confidence and may force `WATCH`.
- Unresolved currency, identity, portfolio, or policy ambiguity blocks actionable output.
- Strong analyst agreement cannot compensate for stale or low-quality evidence.
- A numerical confidence score must include drivers and limitations.
- Confidence must be stored with model, calculation, policy, and evidence versions.
- Confidence should be evaluated against later outcomes, but outcome results must not rewrite the original confidence.

Recommended bands are `LOW`, `MEDIUM`, and `HIGH`, with numeric calibration retained internally. User-facing language should avoid false precision and state the principal uncertainty.

---

## 9. Challenge workflow

### 9.1 User-triggered challenge

The recommendation UI should expose:

**Challenge this recommendation**

This creates a new immutable challenge run linked to the original recommendation. It does not edit, delete, or silently downgrade the original record.

```text
Recommendation
  → user clicks Challenge
  → freeze original recommendation/context
  → collect changed user question or challenge reason
  → rebuild/verify current evidence packet
  → run Risk + Bear first
  → run Bull response against the bear case
  → run affected specialists again where evidence changed
  → Chair reconsideration
  → deterministic gates
  → new recommendation, supersession, or explicit reaffirmation
  → user decision
```

### 9.2 Challenge prompts and scope

The challenge may ask:

- What evidence would make this recommendation wrong?
- What is the strongest bear case?
- What risks are underweighted?
- What happens if the portfolio is already concentrated?
- What changes under a longer/shorter horizon?
- What if the user does nothing?

The user may provide a concern, but cannot inject canonical facts through prompt text. User-provided facts are hypotheses until validated through normal data pathways.

### 9.3 Challenge output

The result must show:

- original thesis and recommendation;
- new evidence and changed data as-of;
- bear findings and bull responses;
- changed assumptions/calculations;
- reaffirmed or changed action;
- dissent and unresolved uncertainty;
- what would invalidate the revised view;
- relationship to the original record.

A challenge that finds no safe actionable conclusion may produce `WATCH` or abstention. Reaffirmation still creates a new immutable analysis record with its own evidence and run hashes.

---

## 10. Failure handling

| Failure | Required behavior |
|---|---|
| Security identity unresolved | Stop security-specific analysis; expose identity issue; do not infer from ticker text. |
| Missing or partial portfolio | Block portfolio-wide claims; disclose omitted holdings; downgrade or abstain. |
| Stale/ambiguous market data | Label the basis; use only allowed prior-close context or block. Never claim live data. |
| Mixed/unknown currency | Fail closed for affected calculations and recommendations. |
| Missing lots/cost basis | Do not make tax-sensitive SELL/REDUCE claims; disclose limitation. |
| Provider outage/rate limit | Return degraded/unavailable state; do not fabricate replacement data. |
| Conflicting sources | Preserve conflict and synthesize uncertainty or abstain. |
| Malformed agent output | Reject the output, log sanitized diagnostics, and retry only within a bounded policy; otherwise abstain. |
| Missing citations | Reject affected finding/draft. |
| Prompt injection in external content | Treat content as data; do not execute instructions or expose tools. |
| Quant/backtest leakage or invalid solver | Reject result as recommendation evidence. |
| Risk blocker/policy failure | No actionable recommendation; use WATCH/abstention with reason. |
| Chair overreach or unsupported number | Reject draft and return validated calculations/uncertainty. |
| Unauthorized scope | Apply existing owner-scoped authorization and indistinguishable not-found behavior. |
| Model/provider unavailable | Preserve run status and return safe retry/offline behavior; no false completion. |
| Duplicate/replayed run | Return or reference the immutable existing result when hashes match. |
| Outcome not yet measurable | Keep pending state; do not infer success or failure. |

Retries must be bounded, idempotent, observable, and unable to bypass gates. A failed specialist should be represented as unavailable; the Chair must not silently assume its conclusion.

---

## 11. Cost/latency considerations

### 11.1 Tiered analysis

Not every request needs every analyst:

- **Portfolio monitoring:** deterministic analytics + Portfolio/Risk; add Technical or Macro only when relevant.
- **Existing holding review:** Fundamental + Portfolio/Risk; add Market and Macro based on horizon/data availability.
- **New security candidate:** Fundamental + Portfolio/Risk + Bull/Bear; add Technical/Macro/Quant conditionally.
- **High-impact or disputed recommendation:** full committee, challenge pass, and stronger evaluation requirements.

### 11.2 Cost controls

- Prefer deterministic calculations and cached, immutable evidence packets before model calls.
- Use one frozen packet for all agents; avoid repeated provider retrieval.
- Bound evidence size, tool calls, model tokens, retries, and total wall-clock time.
- Use the existing local-first Ollama path where it satisfies quality and latency requirements.
- Record model, prompt, token, tool, and latency metadata without logging sensitive content unnecessarily.
- Feature-gate expensive full committee runs and scheduled analysis; default external access remains off.
- Do not parallelize at the cost of duplicated facts, race conditions, or untraceable context.

### 11.3 Latency tiers

The implementation should define target budgets by analysis tier, but not promise real-time recommendations until provider freshness and operational behavior are proven. A partial result must clearly say which analysts/evidence were unavailable.

---

## 12. Evaluation framework

### 12.1 Deterministic evaluation

Test:

- evidence packet identity, ownership, freshness, currency, and coverage;
- exact portfolio and valuation calculations;
- action semantics and suitability/policy gates;
- score and confidence reproducibility;
- immutable run/recommendation identity and supersession;
- challenge linkage and no mutation;
- failure, abstention, and retry behavior.

### 12.2 Agent evaluation

Use versioned golden cases with known evidence packets to measure:

- citation fidelity;
- observed-fact versus interpretation classification;
- no invented facts/numbers;
- correct use of deterministic calculations;
- evidence omission disclosure;
- bull/bear completeness;
- risk discovery and blocker respect;
- portfolio-fit reasoning;
- invalidation-condition quality;
- conflict reporting;
- confidence calibration;
- schema adherence;
- prompt-injection resistance;
- privacy and ownership isolation;
- consistency across replayed inputs.

### 12.3 Committee evaluation

Measure:

- recommendation consistency under identical inputs;
- action appropriateness against expert-labelled cases;
- false-positive and false-negative rates;
- abstention quality;
- calibration by action and horizon;
- downside/risk omission rate;
- evidence coverage of material claims;
- challenge effectiveness, including changed recommendations when warranted;
- user comprehension and decision-quality signals;
- latency, cost, provider failure, and retry rates.

Evaluation must distinguish recommendation quality from investment performance. A later market outcome does not by itself prove that the committee’s reasoning was correct or that the user followed it.

### 12.4 Outcome learning

Existing decision journal and outcome infrastructure should record whether the user accepted, rejected, or deferred and later measurable outcomes. Outcome data may improve calibration and prompts through a governed process, but must not silently rewrite historical recommendations or become an execution policy.

---

## 13. Human approval boundary

The committee produces a recommendation for review. The user remains the final decision-maker.

```text
Validated evidence
  → deterministic analytics
  → specialist findings
  → committee recommendation
  → user review
  → user accept / reject / defer / challenge
```

The recommendation is not financial execution, an order, or an authorization. In this phase:

- no broker credentials are accepted by committee agents;
- no order, transfer, settlement, or money-movement tool is allowlisted;
- no agent can call an execution integration;
- no assistant response may claim that a trade occurred;
- user acceptance records a decision only through existing decision-journal semantics;
- any future execution phase would require a separate ADR, permissions model, authentication/approval design, audit controls, and explicit product authorization.

The user may correct data or provide context, but canonical facts must be validated through Atlas data pathways. A user decision cannot mutate the evidence used to generate the recommendation.

---

## 14. Example end-to-end analysis

### Scenario

The user owns an existing position in `Security-A` and asks: “Should I add to this holding for a five-year goal?” Atlas has a complete portfolio snapshot, validated market data, recent filings, and a goal context, but quant backtest data is unavailable.

### Step 1 — Context and calculations

Atlas resolves `Security-A` to a stable identity and freezes:

- owner-scoped portfolio snapshot and as-of time;
- current weight, sector/issuer concentration, liquidity, and cost-basis availability;
- five-year goal horizon, funding gap, risk capacity, and cash needs;
- validated price/fundamental/filing/earnings evidence;
- deterministic valuation range, volatility, drawdown, correlation, and hypothetical ADD impact;
- explicit omission: no admissible backtest evidence.

### Step 2 — Specialist findings

- **Fundamental:** filings and statements support improving margins and cash flow; valuation is within the deterministic range but sensitive to growth assumptions. Cites filing and calculation references.
- **Market:** trend is positive over the selected window, but volatility is elevated. States the observation window and does not predict a guaranteed price path.
- **Macro:** rates and sector conditions create uncertainty for the valuation multiple. Cites the macro snapshot and labels interpretation.
- **Portfolio:** adding would increase issuer and sector concentration beyond the preferred band; the hypothetical impact worsens portfolio risk modestly and does not materially improve the goal projection.
- **Risk:** concentration and valuation sensitivity are blocking concerns for ADD at the requested size; liquidity is acceptable. Recommends either a smaller bounded exposure review or no increase.

### Step 3 — Bull/bear challenge

- **Bull:** strongest case is durable cash-flow growth, reasonable valuation range, and positive operating trend; catalyst is the next earnings update if validated guidance persists.
- **Bear:** concentration, multiple compression, and growth disappointment could impair the five-year goal path; invalidation includes deteriorating cash flow or breach of portfolio risk limits.

Both outputs cite the same frozen packet. Neither invents a target price or treats missing quant data as neutral evidence.

### Step 4 — Chair draft and gates

The Chair writes:

- **Action:** `HOLD` or `WATCH`, not `ADD`.
- **Conviction:** medium-low because fundamental evidence is supportive but portfolio fit and valuation sensitivity are unfavorable; quant evidence is unavailable.
- **Thesis:** the company may remain fundamentally attractive, but increasing this existing exposure does not improve the user’s portfolio enough to justify additional concentration under the current goal/risk context.
- **Bull case:** operating improvement and valuation support if assumptions hold.
- **Bear case:** concentration and valuation downside can damage the goal path.
- **Catalyst:** validated earnings/guidance evidence at the next review.
- **Risks:** concentration, multiple compression, growth miss, stale/missing quant coverage.
- **Invalidation/review:** portfolio weight returns within policy band, valuation sensitivity improves, or new evidence changes cash-flow/growth assumptions.
- **Evidence:** links to portfolio snapshot, calculations, filings, market/macro observations, and specialist findings.
- **Dissent:** Bull supports the security’s quality; Portfolio/Risk oppose adding now.

The deterministic gates confirm that no actionable ADD is suitable. Atlas persists only the valid recommendation through the existing lifecycle, or emits a bounded WATCH if the review trigger is the appropriate outcome.

### Step 5 — User decision

The UI presents the recommendation, evidence, uncertainty, dissent, and “Challenge this recommendation.” The user may accept, reject, defer, or challenge. Atlas records that decision; it places no order and performs no trade.

---

## Final recommendation

**Proceed with a bounded design and implementation spike, not full autonomous committee rollout.**

First establish the canonical investment context, evidence packet, deterministic portfolio/valuation/risk calculations, and typed specialist contracts. Then add Portfolio/Risk plus Fundamental and Bear/Bull passes, reuse the existing orchestrator and recommendation lifecycle, and expand to Technical/Macro/Quant only when data quality and evaluation fixtures justify them.

The committee must remain an evidence-grounded analysis capability. Models propose; deterministic systems validate; policy gates authorize presentation; the user decides; no agent executes.

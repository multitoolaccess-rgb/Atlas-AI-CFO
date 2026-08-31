# Atlas Investment Intelligence — Domain Design

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Design date:** 2026-08-30  
**Status:** Architecture/domain design only; not an implementation plan approval  
**Authoritative inputs:** `ATLAS-INVESTMENT-INTELLIGENCE-AUDIT.md`, `ATLAS-OPEN-SOURCE-INVESTMENT-STACK.md`, existing Atlas ADRs and architecture documents.

> **Product boundary:** Investment Intelligence analyzes and recommends. The user makes the final decision. This design contains no automatic trading, brokerage order submission, execution, transfer, or money movement.

## 1. Domain model

### 1.1 Design principles

## Investment Data Authority Invariants

```text
Current Holding ≠ Historical Investment Truth
Unknown ≠ Zero
Missing ≠ No Change
Stale ≠ Current
Estimated ≠ Observed
LLM Claim ≠ Financial Fact
```

These distinctions are mandatory domain rules. A current holding describes a current state and cannot establish historical lots, cost basis, or performance. Unknown must remain distinct from zero so exposure and coverage are not silently understated. Missing data is not evidence of no change. Stale observations cannot be presented as current. Estimates require explicit assumptions and cannot be labeled observed facts. LLM claims are interpretations that require validated evidence and can never become canonical financial facts. Contracts, calculations, provenance, API/UI status, and tests must preserve these distinctions.

1. **Atlas owns the decision context.** External projects and providers supply data or computation primitives; they do not own Atlas’s canonical financial truth or recommendation authority.
2. **Facts precede findings.** A provider observation is not automatically a canonical fact. Atlas validates identity, currency, timestamps, freshness, completeness, and provenance before using it.
3. **Deterministic authority, AI interpretation.** Financial mathematics, valuation, portfolio analytics, scoring, optimization, and policy gates are deterministic services. AI may synthesize validated results and explain trade-offs but cannot invent or authorize them.
4. **As-of correctness.** Every material conclusion references the portfolio state, market/evidence state, calculation versions, and time basis used to produce it.
5. **History is preserved.** Corrections create new versions/events; they do not rewrite prior forecasts, recommendations, decisions, or measured outcomes.
6. **Abstention is a valid result.** Unknown identity, ambiguous currency, stale/insufficient evidence, unresolved reconciliation, or unsuitable context produces `unavailable`, `WATCH`, or no recommendation rather than fabricated certainty.
7. **Portfolio fit is first-class.** Security quality is not enough. The relevant question is whether a proposed action improves the user’s portfolio and goals within risk, liquidity, tax, and constraint boundaries.
8. **No hidden execution.** Recommendation actions describe a decision for user review. They do not represent orders or imply that Atlas performed an action.

### 1.2 Object classification

The requested objects are deliberately divided into **canonical entities**, **immutable observations**, **derived projections**, and **recommendation/decision records**. Not every concept requires a top-level table or model.

| Object | Classification | Initial decision | Purpose and authority |
|---|---|---|---|
| `Security` | Canonical entity | **NEW** | Stable Atlas instrument identity; ticker is an attribute, not identity. Holds identifiers, instrument type, issuer/company link, currency, exchange/venue, and effective-dated classification references. |
| `Company` | Canonical entity | **NEW, possibly shared by Security** | Issuer/legal entity identity separate from tradable securities. A company may issue multiple share classes/securities. Provider profile data is evidence used to enrich it, not unconditional truth. |
| `MarketSnapshot` | Immutable observation | **NEW** | As-of market state for prices, benchmark/index observations, rates/curves, macro series, and provider/freshness metadata. Do not use a mutable “current market” row for historical conclusions. |
| `FinancialFact` | Immutable normalized observation | **NEW** | One bounded, source-cited value/concept with period, unit, currency, filing/source date, as-known-at/vintage date, and provenance. Useful for ratios and statement construction. |
| `FinancialStatement` | Immutable normalized projection/aggregate | **NEW** | A versioned company statement assembled from validated facts, with statement type, period, restatement/vintage, calculation version, and source links. Not raw SEC JSON. |
| `Filing` | Immutable source/evidence entity | **NEW** or extension of `SecFilingEvent` | SEC/EDGAR filing identity, form, accession, dates, company/CIK, source URL/hash, and extraction status. Existing `SecFilingEvent` is a strong normalized contract to reuse. |
| `NewsEvent` | Immutable source/evidence entity | **EXTEND** existing `CompanyNewsItem`/`MarketNewsItem` | Source-cited news item with publication/retrieval time, security/company/market scope, sanitized text, provider, and relevance/materiality. Avoid treating sentiment as fact. |
| `EarningsEvent` | Immutable source/evidence entity | **EXTEND** existing `EarningsEvent`/`EarningsResult` | Scheduled or reported earnings event with period, actual/estimate fields, dates, source, and freshness. Existing Market Intelligence contracts are the starting point. |
| `ResearchFinding` | Derived finding | **NEW** | Structured specialist or deterministic finding: subject, claim type, direction, evidence references, assumptions, confidence, conflicts, validity window, and requested calculations. It is not a recommendation. |
| `InvestmentThesis` | Derived AI-assisted projection | **NEW** | Versioned synthesis of validated findings: thesis, bull/bear cases, catalysts, risks, invalidation conditions, valuation summary, horizon, confidence, and cited evidence. Never canonical fact. |
| `InvestmentSignal` | Derived deterministic value | **NEW** | Versioned signal output such as momentum, quality, value, growth, trend, volatility, or factor exposure; includes input window, formula/model version, data quality, and no implied action. |
| `RiskAssessment` | Derived deterministic/structured finding | **NEW** | Subject-level and portfolio-level risk assessment with risk type, severity, exposure, measurement basis, confidence, mitigations, and as-of state. |
| `InvestmentRecommendation` | Recommendation record | **EXTEND** existing `Recommendation` | Security/portfolio action recommendation using existing immutable recommendation, decision journal, history, and outcome lifecycle. Add investment-specific versioned contract rather than a parallel lifecycle. |
| `PortfolioImpact` | Derived calculation | **NEW** | Deterministic estimate of current/proposed portfolio impact: allocation, concentration, risk, liquidity, expected range, goal effect, tax flags, turnover, and assumptions. Stored as versioned output or embedded by hash/reference in recommendation payload. |
| `RecommendationEvidence` | Evidence linkage record/value object | **EXTEND** existing provenance/evidence references | Links a recommendation to specific portfolio snapshot, calculations, market/fundamental/filing/news/earnings/quant sources, with evidence role, hash, timestamp, freshness, and coverage. |
| `RecommendationOutcome` | Outcome record | **EXTEND** existing `OutcomeEvaluation` | Reuse append-only outcome evaluation; add investment-specific measured metrics through a versioned result contract, never rewrite the recommendation. |

### 1.3 Recommended minimal implementation model

The first implementation should not create every requested object. The minimum coherent domain is:

1. `Security` + identifier/classification records.
2. Immutable investment transactions/lot events and position snapshots.
3. Immutable valuation/market observations.
4. `PortfolioSnapshot` and deterministic `PortfolioImpact`/analytics outputs.
5. Extensions to existing Market Intelligence normalized evidence contracts.
6. `ResearchFinding`, `RiskAssessment`, and `InvestmentThesis` as structured/versioned analysis outputs.
7. An investment extension of existing `Recommendation`.
8. Existing decision journal/history/audit/outcome records.

`Company`, `FinancialFact`, `FinancialStatement`, and `Filing` can be introduced incrementally, with `SecFilingEvent`, `CompanyProfile`, `EarningsEvent`, and `EarningsResult` serving as initial wire contracts.

### 1.4 Domain vocabulary

- **Instrument:** tradable object, including equity, ETF, mutual fund, bond, option, cash equivalent, crypto, or other supported asset.
- **Security:** Atlas-stable instrument identity; may have multiple symbols over time and provider identifiers.
- **Company:** issuer/legal entity; not every security has a company.
- **Position:** quantity/exposure of a security in an account at an as-of time.
- **Lot:** acquisition/disposal unit used for cost basis and tax-aware analysis.
- **Portfolio snapshot:** immutable, owner-scoped view of positions, cash, valuation basis, data quality, and hashes at one as-of boundary.
- **Evidence:** externally or internally sourced material that supports a finding or calculation.
- **Finding:** a bounded observation/interpretation, not an action.
- **Thesis:** coherent argument assembled from findings, cases, catalysts, risks, and invalidation conditions.
- **Recommendation:** a user-facing action proposal that passed deterministic quality/suitability gates.
- **Outcome:** later measurement of what happened relative to the recommendation’s stated expectation.

## 2. Entity relationships

### 2.1 Conceptual relationship map

```text
User ──owns──► InvestmentAccount ──contains──► PositionSnapshot
   │                  │                         │
   │                  └──has──► InvestmentTransaction ──creates──► TaxLot
   │                                                    │
   └──has goals/preferences/policy                         └──references──► Security
                                                                         │
                                                                         └──issued by──► Company

Security ──has effective-dated──► SecurityIdentifier / Classification
Security ──receives──► MarketSnapshot / CorporateAction / FinancialEvidence
Company ──has──► FinancialFact ──assembled into──► FinancialStatement
Company/Security ──has──► Filing / NewsEvent / EarningsEvent

PortfolioSnapshot ──contains──► PositionSnapshot + ValuationObservation
PortfolioSnapshot ──feeds──► PortfolioAnalytics / PortfolioImpact / RiskAssessment

Evidence + PortfolioAnalytics + GoalContext + PolicyContext
  └──feeds──► ResearchFinding ──synthesized into──► InvestmentThesis
                                               │
                                               └──feeds──► InvestmentRecommendation

InvestmentRecommendation ──links──► RecommendationEvidence
InvestmentRecommendation ──links──► Goal(s), PortfolioSnapshot, PortfolioImpact, Risks
InvestmentRecommendation ──enters──► existing DecisionJournal / DecisionHistory
DecisionJournal ──may produce──► RecommendationOutcome / OutcomeEvaluation
```

### 2.2 Ownership and temporal rules

- Every user-owned investment record carries owner/account scope; household visibility remains role-controlled.
- A `Security` may be globally reusable metadata, but user-specific annotations/preferences remain owner-scoped.
- Market/evidence observations are immutable and timestamped. Corrections or restatements create new observations with a new as-known-at/vintage context.
- Position snapshots are immutable; current views select the latest valid snapshot rather than mutating history.
- Transactions and lot events are append-only. Reconciliation corrections are compensating events or new source versions.
- Recommendations link to the exact portfolio snapshot and evidence/calculation hashes used at generation.
- Decisions and outcomes use existing append-only contracts and ownership checks.

### 2.3 Relationships that should not be direct

- AI agents must not directly write `Security`, `FinancialFact`, `PositionSnapshot`, `MarketSnapshot`, or `InvestmentRecommendation` records.
- `Holding` should not become the direct parent of `FinancialFact`, `Filing`, or recommendation identity; it is a transitional compatibility input.
- A ticker string must not be used as a foreign-key substitute for `Security`.
- A `NewsEvent` or sentiment score must not directly imply a recommendation action.
- `InvestmentThesis` must not be treated as a canonical financial fact.

## 3. Recommendation model

### 3.1 Investment recommendation as an extension

Atlas should extend the existing immutable `Recommendation` model/lifecycle rather than create a second recommendation system. The existing model already provides:

- owner and goal linkage;
- immutable/idempotent identity;
- forecast/input-state hash linkage;
- expected-impact range;
- confidence;
- assumptions, risks, freshness, and provenance JSON;
- derived/expiration timestamps;
- decision journal integration;
- outcome evaluation linkage.

Investment recommendations need a versioned typed payload or extension containing:

```text
InvestmentRecommendation
  ├─ existing recommendation identity / owner / goal / lifecycle linkage
  ├─ action: BUY | ADD | HOLD | REDUCE | SELL | WATCH
  ├─ subject: Security or Portfolio scope
  ├─ rationale / why_now
  ├─ thesis_id or thesis snapshot hash
  ├─ portfolio_snapshot_hash
  ├─ portfolio_impact_reference/hash
  ├─ evidence references and coverage summary
  ├─ valuation summary and method/version
  ├─ expected-return range (not a promise)
  ├─ expected-risk/downside range
  ├─ time horizon
  ├─ confidence and confidence drivers
  ├─ bull case / bear case / catalysts
  ├─ risks and invalidation conditions
  ├─ alternatives / “if ignored” comparison
  ├─ suitability/policy result
  ├─ required user review/approval
  ├─ expires_at / next_review_at
  └─ analytics/provider/agent/policy versions
```

Use opaque references/hashes for sensitive or large evidence payloads where the existing privacy model requires it. The user-facing response may include bounded explanations and citations, but never credentials, raw provider payloads, or unnecessary account identifiers.

### 3.2 Precise action semantics

#### BUY

A proposal to establish a new position in the specified security for a specified portfolio/account context where the user currently has no position or the recommendation explicitly treats the action as a new exposure. It must include rationale, target exposure/range or bounded amount guidance, suitability, liquidity, risk, and alternatives. It is **not** an order and does not authorize execution.

#### ADD

A proposal to increase an existing position or exposure. It must distinguish ADD from BUY, show current and proposed exposure, concentration impact, incremental risk, expected portfolio impact, and why increasing exposure is suitable. An ADD must not be emitted if the proposed action breaches concentration or policy limits.

#### HOLD

A recommendation to maintain the current position/exposure and refrain from increasing or reducing it for the stated horizon. HOLD requires a reasoned balance of evidence and an explicit review/invalidating condition; it is not a claim that the security is risk-free or guaranteed to outperform.

#### REDUCE

A proposal to decrease exposure without necessarily exiting the position. It must state the concentration/risk/fit/tax/liquidity rationale, expected impact, remaining-exposure assumptions, and alternatives. It is not an instruction to sell a specific lot or quantity unless a future approved contract explicitly adds that capability.

#### SELL

A proposal to exit the position or remove the security exposure from the relevant portfolio/account scope. It must state the evidence, invalidation/thesis change, risks of exiting, tax/liquidity caveats, replacement alternatives if relevant, and confidence. It is not order submission.

#### WATCH

A non-execution monitoring recommendation: evidence is material or a candidate action is worth review, but the system lacks sufficient confidence, suitability, coverage, freshness, or trigger confirmation for BUY/ADD/HOLD/REDUCE/SELL. WATCH must specify the trigger, evidence to monitor, review date, and what would promote or invalidate it.

### 3.3 Recommendation invariants

1. Exactly one action and one subject scope per recommendation.
2. A recommendation must identify whether it is security-level, portfolio-level, or watch-level.
3. BUY/ADD/REDUCE/SELL require a passed suitability/policy gate; HOLD/WATCH may still be blocked or downgraded by data-quality gates.
4. No action recommendation may be generated from a single uncorroborated AI claim.
5. Every recommendation links to an immutable portfolio snapshot and evidence/calculation versions.
6. Expected return is a bounded estimate/range with method, horizon, assumptions, and uncertainty—not a promise.
7. A recommendation cannot specify an execution destination, broker, order type, or automatic action in this phase.
8. A superseding recommendation creates a new immutable record and explains the changed evidence; it does not update the old record.
9. Replays with identical canonical inputs are idempotent; changed inputs/versions create a new recommendation identity.
10. User decision is separate from recommendation generation and cannot be inferred from display or model output.

## 4. Recommendation lifecycle

### 4.1 Reuse existing lifecycle

The investment lifecycle should be a specialization of Atlas’s existing:

```text
Candidate → Validated → Ranked → Presented
  → Accepted | Rejected | Deferred | Expired
  → Measured / Outcome evaluated
```

No separate investment lifecycle is justified.

### 4.2 Investment-specific states and gates

Investment candidates may carry internal non-user-facing states before the existing recommendation is persisted:

```text
Researching
  → Evidence assembled
  → Analytics calculated
  → Candidate generated
  → Quality/suitability gated
  → Ranked
  → Persisted recommendation
  → Presented to user
  → User decision
  → Review/expiry
  → Outcome evaluation
```

A candidate that fails a gate is not persisted as an actionable recommendation unless it is explicitly represented as a bounded `WATCH`/unavailable finding with the reason.

### 4.3 Supersession and review

- New market/portfolio data does not mutate a prior recommendation.
- A changed portfolio snapshot, material evidence change, policy change, or expiry creates a new derivation.
- The new record may reference the prior recommendation as a superseded/similar item through an append-only relation.
- A HOLD/WATCH must carry a review-by or trigger condition.
- Outcome evaluation measures the recommendation’s stated horizon and target, not a hindsight-chosen window.

### 4.4 User decision boundary

The user can:

- view evidence and assumptions;
- accept, reject, or defer through existing decision journal APIs;
- record a rationale or correction where the existing contract permits;
- mark a WATCH item for review.

The user cannot cause a recommendation response to mutate canonical market/portfolio facts. There is no broker action in this lifecycle.

## 5. Evidence model

### 5.1 Evidence categories

Reuse and extend the existing Market Intelligence evidence categories:

- **Market:** quote, adjusted price history, volume, benchmark/index, rates, yield curve.
- **Fundamental:** normalized financial facts/statements, ratios, balance sheet, cash flow, profitability, growth, quality.
- **Filing:** SEC filing identity, form, filing date, extracted section/fact, accession/source.
- **Earnings:** schedule, actual/estimate, surprise, management/earnings material where licensed.
- **News:** source-cited, publication-time-bounded company/market news.
- **Analyst:** consensus counts, price targets, recommendation changes; explicitly external opinion.
- **Quantitative:** deterministic signals, historical behavior, risk statistics, backtests, factor outputs.
- **Portfolio:** owned positions, cost basis/lot data, allocation, concentration, liquidity, performance, risk, and goal impact.
- **Decision history:** prior Atlas recommendation, user decision, and measured outcome.

### 5.2 RecommendationEvidence structure

A recommendation evidence item should contain:

```text
RecommendationEvidence
  ├─ evidence_id / hash
  ├─ evidence_role: supporting | contradicting | contextual | portfolio_state | calculation
  ├─ subject: security/company/portfolio/goal
  ├─ category
  ├─ source/provider/library
  ├─ source_url or opaque source reference
  ├─ retrieved_at
  ├─ published_at / observed_at / effective_at where applicable
  ├─ freshness and price/data basis
  ├─ source record/version hash
  ├─ exact claim or bounded metric reference
  ├─ calculation/model/version reference
  ├─ coverage/omission status
  └─ confidence/quality annotation
```

Raw URLs may be returned only when safe under existing source URL rules. Raw provider payloads, credentials, query tokens, and unnecessary personal data must not cross the boundary.

### 5.3 Evidence sufficiency

The recommendation engine should compute a deterministic sufficiency result:

- required categories present for the action and subject;
- minimum portfolio coverage met;
- portfolio state current enough for the horizon;
- market/fundamental evidence fresh enough;
- source conflicts disclosed;
- valuation/risk calculations reproducible;
- missing data and omissions visible;
- user policy/risk/goal context available.

Insufficient evidence must produce `WATCH`, an unavailable finding, or no recommendation according to severity.

### 5.4 Evidence hierarchy

For material numerical claims:

1. Atlas canonical portfolio/transaction/valuation records.
2. Validated deterministic calculations over those records.
3. Primary filings and official source records.
4. Provider-normalized market/earnings/news records.
5. Secondary analyst opinions and sentiment.
6. AI interpretation.

Lower-level evidence cannot override higher-level canonical facts without a new validated reconciliation process.

## 6. Deterministic calculation boundaries

### 6.1 Atlas-owned deterministic services

Atlas must own the contracts and validation around:

- security identity and identifier resolution;
- transaction/lot/position reconstruction;
- current and historical portfolio snapshots;
- cost basis and realized/unrealized calculations;
- prices, currencies, conversions, and rounding;
- allocation, concentration, sectors, industries, geography, market cap, and factor exposure;
- time-weighted and money-weighted performance;
- volatility, correlation, drawdown, beta, tracking error, tail risk, liquidity;
- valuation ratios and valuation ranges from validated facts/market inputs;
- portfolio impact and goal impact;
- suitability, restrictions, risk capacity, horizon, liquidity, tax flags;
- evidence coverage/freshness and recommendation quality gates;
- ranking/scoring and confidence calibration;
- recommendation identity, immutability, and idempotency;
- backtesting dataset boundaries and leakage controls.

### 6.2 Open-source library role

External libraries such as Riskfolio-Lib, skfolio, PyPortfolioOpt, QuantLib, NumPy/SciPy/pandas, and EdgarTools may perform bounded sub-computations. Their output is untrusted until Atlas validates:

- input identity and window;
- units/currency and numerical finiteness;
- dataset vintage and corporate-action treatment;
- constraints and solver status;
- formula/model/version;
- reproducibility and expected bounds;
- tax/liquidity/policy implications;
- output mapping to the exact Atlas security/portfolio snapshot.

### 6.3 Valuation boundary

Valuation methods must be explicit and versioned:

- market-based price/market-cap;
- ratio/multiple comparison;
- discounted cash flow or dividend discount;
- asset/fundamental value;
- scenario/range valuation.

An AI-generated valuation narrative cannot create a valuation number. The number must come from a deterministic calculator over validated facts, with assumptions, data vintage, method, and uncertainty recorded.

### 6.4 Quant/backtesting boundary

Backtests are research evidence, not proof of future performance. Atlas must require:

- point-in-time data;
- no look-ahead or survivorship leakage;
- corporate-action adjustments;
- fees, slippage, turnover, and tax assumptions where relevant;
- out-of-sample/walk-forward evaluation;
- benchmark and baseline comparison;
- sample size and confidence limitations;
- exact code/data/model versions.

No backtest may directly produce a user-facing BUY/SELL without portfolio-fit and policy gates.

## 7. AI boundaries

### 7.1 Allowed AI responsibilities

AI may:

- synthesize validated findings;
- draft an investment thesis;
- explain bull/bear cases and trade-offs;
- summarize filings, earnings, and news that already passed source/sanitization boundaries;
- compare deterministic scenarios;
- identify contradictions or missing evidence;
- ask for clarification;
- suggest WATCH triggers;
- produce a human-readable explanation of a deterministic recommendation;
- participate in a bounded committee discussion where each conclusion cites structured inputs.

### 7.2 Prohibited AI responsibilities

AI must not:

- invent prices, holdings, shares, returns, financial facts, filing facts, or macro values;
- calculate authoritative portfolio metrics in free text;
- choose or silently alter a canonical security identity;
- override freshness, coverage, currency, suitability, risk, or policy gates;
- turn sentiment or analyst consensus into a recommendation without deterministic checks;
- write canonical records directly;
- create an execution request, broker order, trade, transfer, or money movement;
- claim a recommendation was accepted, executed, or profitable without a recorded user decision/outcome;
- suppress contradictory evidence or uncertainty;
- retrieve cross-user or unauthorized portfolio data;
- treat untrusted article/news/filing text as instructions.

### 7.3 Agent input/output contract

Every investment agent run should receive a bounded context envelope:

```text
InvestmentAgentContext
  ├─ owner/task scope
  ├─ portfolio_snapshot_hash and as_of
  ├─ goal/policy/risk context references
  ├─ validated evidence packet IDs/hashes
  ├─ deterministic analytics references/results
  ├─ allowed tools and time budget
  ├─ prohibited actions
  └─ schema/model/policy versions
```

Every output should be typed as one of:

- `ResearchFinding`;
- `InvestmentThesis`;
- `RiskAssessment`;
- `RequestedCalculation`;
- `ConflictReport`;
- `Abstention`;
- `RecommendationDraft` (not yet authorized/persisted).

The orchestrator validates the output, checks citations against supplied evidence, runs deterministic gates, and only then invokes the existing recommendation application service.

## 8. Portfolio integration

### 8.1 Transitional integration with existing holdings

The current `Account` + `Holding` model remains a compatibility source for imported/manual positions. A migration adapter should:

1. read the current user-owned holdings;
2. resolve each symbol to a `Security` or create an explicit unresolved-identity state;
3. convert Float values only through a documented, reviewed normalization boundary;
4. retain original import/source references and data-quality warnings;
5. create an immutable initial position snapshot with a migration provenance/version;
6. avoid claiming that historical lots or exact performance were reconstructed when they were not;
7. leave legacy routes/UI usable during a staged migration.

No recommendation should silently treat an unresolved or Float-derived record as investment-grade data.

### 8.2 Portfolio snapshot contract

A portfolio snapshot should contain:

- owner and included account scope;
- as-of timestamp and valuation timestamp;
- positions/security IDs, quantities, currencies, and values;
- cash and unknown/unclassified positions;
- cost-basis availability status;
- currency authority/status;
- reconciliation status/conflicts;
- valuation source/freshness/basis;
- coverage and omitted holdings;
- canonical snapshot hash;
- calculation/schema/version metadata.

The snapshot is immutable and is the required input to portfolio analytics and recommendations.

### 8.3 Portfolio impact

For a proposed action, deterministic `PortfolioImpact` should compare baseline and hypothetical bounded state:

- current/proposed weight;
- absolute and relative value;
- issuer/sector/industry/geography/factor exposure;
- volatility/correlation/drawdown/risk contribution changes;
- liquidity and cash impact;
- turnover and fee estimates;
- tax-lot/tax flags where available;
- goal/forecast effect;
- assumptions and unmodeled risks;
- expected impact range and confidence.

The hypothetical state is a calculation input, not a mutation or order.

## 9. Goals integration

### 9.1 Existing Atlas goal relationship

Existing recommendations require goal linkage, and the goal/forecast/scenario systems are authoritative for current financial planning. Investment Intelligence should add portfolio-specific calculations to that context rather than create an investment-only goal system.

### 9.2 Goal-fit inputs

A recommendation may use:

- goal target/date/priority and current trajectory;
- required liquidity and cash reserve;
- horizon and funding schedule;
- risk capacity and acceptable drawdown;
- planned contributions/withdrawals;
- account/tax-location constraints;
- current portfolio risk and concentration;
- expected impact on goal probability or funding gap.

Unknown, stale, or Float-risk goal inputs must be represented in confidence/gates. The existing `Goal.target_amount` Float risk remains relevant until its canonical exact-value path is resolved.

### 9.3 Goal-fit output

Portfolio fit should answer:

- Which goal(s) does this action support?
- Does it improve or reduce projected goal resilience?
- What liquidity or timing trade-off does it introduce?
- What happens if the user does nothing?
- Which assumptions drive the result?
- Is the action suitable for the goal horizon and risk capacity?

A security can be attractive in isolation and still receive HOLD/WATCH/REDUCE because it worsens portfolio/goal fit.

## 10. Data provenance

### 10.1 Provenance requirements

Every material fact, calculation, finding, thesis, recommendation, and outcome must be traceable to:

- source/provider/library/model;
- source record or opaque hash;
- retrieval/publication/observation/effective/as-known-at times;
- currency and unit;
- freshness/data basis;
- transformation/calculation/model version;
- input snapshot/evidence hashes;
- owner/scope authorization;
- confidence/quality/coverage status.

### 10.2 Point-in-time and revisions

Financial statements and macro data can be revised. Store both:

- the period the value describes; and
- the time/version at which Atlas could have known it.

Backtests, historical recommendations, and outcome evaluations must use the as-known-at version appropriate to the decision date. Later restatements may inform a new analysis but must not rewrite the historical recommendation’s evidence.

### 10.3 Provenance versus privacy

- Public source URLs may be retained when credential-free and safe under existing contracts.
- Sensitive portfolio/account/transaction identifiers should be represented by owner-scoped internal IDs or hashes in recommendation/evidence envelopes as required.
- Never log provider tokens, raw statement content, credentials, or unnecessary personal holdings.
- Evidence retrieval must authorize ownership before querying/displaying relevant private context.

## 11. Failure modes

| Failure | Detection | Required behavior |
|---|---|---|
| Unknown/unresolved security | Identifier resolver cannot establish stable identity | Do not calculate security-specific recommendation; expose unresolved data quality and optionally WATCH only for identity correction. |
| Unsupported instrument | Provider/analytics contract does not support asset type | Omit explicitly with reason; do not infer equity semantics. |
| Ambiguous/mixed currency | Currency evidence missing/conflicting or conversion unavailable | Fail closed for affected material calculations/recommendations. |
| Stale quote/market snapshot | Session/freshness policy fails | Use only an explicitly accepted prior-close basis; otherwise downgrade/block. Never label stale data live. |
| Partial portfolio coverage | Holdings omitted or unvalued | Disclose omitted scope; block portfolio-wide claims when coverage threshold is not met. |
| Import/reconciliation conflict | Transactions and holdings disagree | Preserve both evidence states, mark unresolved, and block cost-basis/performance-dependent actions. |
| Missing tax lots | Cost basis/lot history incomplete | Do not make tax-sensitive REDUCE/SELL claims; expose tax uncertainty and use WATCH/HOLD where appropriate. |
| Provider unavailable/rate limited | Existing normalized failure classes | Return degraded/unavailable state with safe recovery; never fill with fabricated data. |
| Conflicting evidence | Specialist/provider findings disagree | Record conflict; synthesize uncertainty or abstain. Do not average unsupported claims. |
| Insufficient fundamentals | Required statements/facts absent or restated | Downgrade confidence; do not present valuation as precise. |
| Quant/backtest leakage risk | Dataset/vintage/validation checks fail | Reject signal as recommendation evidence; retain only internal diagnostic if safe. |
| AI malformed/un-grounded output | Schema/citation/claim validation fails | Discard draft, log sanitized failure, and return deterministic evidence or abstention. |
| Prompt injection in external text | Sanitization and instruction/data separation | Treat text as untrusted data; do not execute embedded instructions or tools. |
| Missing risk/goal context | Suitability inputs absent/stale | Block actionable recommendation; WATCH or request user data. |
| Recommendation replay/conflict | Idempotency/hash mismatch | Return existing immutable row for same inputs; raise sanitized conflict for divergent reuse. |
| Unauthorized ownership scope | Owner/role check fails | Same safe not-found/authorization contract as existing Atlas boundary; no disclosure. |
| User rejects/defers | Existing decision route | Record append-only decision; no action occurs. |
| Outcome not measurable | Window open or evidence missing | Persist pending/not-yet-measurable outcome state under existing contract; never infer success. |
| Provider credential/configuration risk | Settings/local config inspection | Keep external access default-off; do not activate automatically. |

## 12. Security/privacy considerations

### 12.1 Threat model

Investment Intelligence combines highly sensitive holdings with untrusted external content and potentially costly model/provider calls. Threats include:

- cross-user portfolio disclosure;
- provider credential leakage;
- prompt injection in filings/news/transcripts;
- model hallucination or overconfidence;
- malicious/malformed market data;
- stale or revised data presented as current;
- unauthorized recommendation/decision mutation;
- poisoning of memory or outcome calibration;
- hidden execution drift.

### 12.2 Required controls

- Authenticate every API request and authorize owner/account/household scope before retrieval and before display.
- Keep provider credentials server-side; never expose them to frontend or models.
- Keep external provider calls behind existing adapter controls, bounded contracts, rate pacing, cache, retries, and normalized failures.
- Sanitize text and source URLs; preserve source identity without allowing source content to become agent instructions.
- Validate every model output using strict Pydantic schemas; reject unknown fields and unsupported actions.
- Enforce financial policy outside the model.
- Require immutable recommendation/decision/outcome persistence and audit events.
- Do not add trading, brokerage, execution, or money movement routes in this phase.
- Maintain explicit retention/deletion policy before broader multi-user rollout.
- Keep provider/generation/scheduler/email flags default-off and never auto-enable local credentials.

### 12.3 Sensitive data minimization

Agents should receive the minimum portfolio context needed for the task. Prefer aggregate/exposure references over raw account numbers and transactions. Tax-lot detail should be exposed only to a tax-scoped calculation/agent when necessary and authorized.

## 13. Testing strategy

### 13.1 Domain and numeric tests

- Security identifier normalization, symbol changes, share classes, unsupported instruments.
- Exact Decimal quantity/price/value/cost-basis arithmetic and rounding.
- Transaction-to-lot reconstruction and reconciliation conflicts.
- Corporate-action transformations and immutable snapshot continuity.
- Currency authority, conversion, mixed-currency fail-closed behavior.
- Portfolio snapshot canonical hashes and deterministic replay.
- TWR/MWR, dividends, fees, deposits/withdrawals, benchmarks, partial periods.
- Allocation, sector/geography/market-cap/factor look-through.
- Volatility, correlation, drawdown, liquidity, and risk contribution fixtures.
- Valuation methods, ranges, assumption sensitivity, and invalid data.
- Goal/portfolio impact with scenario fixtures.

### 13.2 Provider and evidence contract tests

Reuse existing Market Intelligence patterns:

- no-network synthetic transports;
- provider failure normalization;
- rate-limit/retry/cache behavior;
- freshness/session/price-basis rules;
- source URL credential rejection;
- bounded text and collection sizes;
- coverage omissions and partial evidence;
- SEC CIK/form/source validation;
- news/earnings/analyst deduplication;
- provider/library version metadata.

### 13.3 Recommendation/policy tests

- exact action semantics and invalid combinations;
- BUY/ADD/REDUCE/SELL blocked by failed suitability/policy gates;
- HOLD/WATCH trigger/review semantics;
- no recommendation on stale/ambiguous/unresolved state;
- evidence sufficiency and contradictory evidence;
- idempotency and immutable re-derivation;
- ownership isolation and indistinguishable cross-user responses;
- decision accept/reject/defer lifecycle;
- supersession without mutation;
- outcome measurement windows and no causal overclaiming.

### 13.4 AI/agent evaluations

Use golden structured cases for:

- citation fidelity;
- fact grounding;
- no invented numbers;
- correct calculation-tool use;
- abstention behavior;
- conflict reporting;
- bull/bear completeness;
- invalidation-condition quality;
- policy compliance;
- prompt injection resistance;
- cross-user privacy;
- output schema adherence;
- calibration and confidence wording;
- consistency between deterministic inputs and narrative.

### 13.5 Quant/backtest tests

- point-in-time/vintage data;
- no look-ahead/survivorship leakage;
- corporate actions;
- fees/slippage/turnover/tax assumptions;
- walk-forward/out-of-sample results;
- seeded reproducibility;
- benchmark and naïve baseline comparisons;
- solver failure and infeasible-constraint behavior.

## 14. Migration strategy

### 14.1 Principles

- Additive, reversible, and vertical-slice migration.
- Existing portfolio UI/import routes remain usable during transition.
- No destructive rewrite of current holdings or transaction history.
- Every migrated record carries source/provenance and quality status.
- Never claim precision or historical completeness that the source cannot support.
- Preserve existing recommendation/decision history unchanged.

### 14.2 Migration stages

#### Stage A — contract and authority

- Approve the investment authority boundary between Finlynq and Rules Service.
- Record an ADR for the investment domain.
- Define exact numeric/currency/history/retention contracts.
- Define `Security` identity and unresolved states.

#### Stage B — additive security and observation foundation

- Add security/instrument identity and provider identifier mapping.
- Add immutable import/source events and reconciliation status.
- Add position and valuation snapshots.
- Build a compatibility projection from existing `Holding` rows.
- Keep Float legacy fields read-only or explicitly marked transitional; do not use them as new recommendation authority.

#### Stage C — canonical portfolio analytics

- Normalize current portfolio into exact values where evidence supports it.
- Add deterministic portfolio snapshot, allocation, concentration, performance, and risk contracts.
- Add fixtures for migrated and incomplete histories.
- Expose data-quality and coverage status in UI/API.

#### Stage D — evidence and finding layer

- Extend existing Market Intelligence contracts for evidence packets and company/fundamental facts as needed.
- Add findings, risk assessments, and thesis versions as derived records.
- Keep provider calls default-off and synthetic in tests.

#### Stage E — recommendation extension

- Extend existing `Recommendation` with investment action payload and portfolio/evidence/calculation references.
- Reuse existing decision journal/history/outcome routes and persistence.
- Replace static frontend recommendation content with server-owned data only after the new contract is proven.

#### Stage F — incremental agent/Copilot integration

- Add read-only investment tools to the existing assistant boundary.
- Introduce specialist roles only with typed inputs/outputs, run metadata, permissions, and evaluations.
- Do not add a framework until the current architecture’s gap is demonstrated.

### 14.3 Rollback/recovery

- New tables/contracts should be additive and feature-gated.
- Existing `Holding` import/read flows remain available until parity is demonstrated.
- Failed identity/normalization records remain unresolved rather than being deleted.
- Recommendation derivation can be disabled without deleting evidence/history.
- Migrations must preserve immutable historical records and follow existing SQLite/PostgreSQL parity tests.

## 15. API boundaries

### 15.1 Existing boundaries to reuse

- Existing authenticated account/transaction/goal/holding APIs for compatibility.
- Existing Market Intelligence routes/contracts for research and evidence.
- Existing forecast/recommendation routes for immutable recommendation reads.
- Existing decision journal/history/outcome routes for user decisions and learning.
- Existing assistant/Copilot route as a presentation/orchestration boundary, not financial authority.

### 15.2 Proposed future resource boundaries

These are design-level boundaries, not APIs to implement now:

```text
/api/v1/investments/securities
/api/v1/investments/accounts/{account_id}/transactions
/api/v1/investments/portfolio-snapshots
/api/v1/investments/portfolio-analytics
/api/v1/investments/securities/{security_id}/evidence
/api/v1/investments/research-findings
/api/v1/investments/theses
/api/v1/investments/recommendations
/api/v1/investments/recommendations/{id}
/api/v1/investments/recommendations/{id}/decisions
/api/v1/investments/recommendations/{id}/outcomes
```

Prefer extending existing `/api/v1/recommendations` semantics over introducing a second decision endpoint. The exact route shape should be chosen during the implementation ADR after the canonical model exists.

### 15.3 API rules

- Read APIs are owner-scoped, paginated/bounded, and include schema version, as-of, freshness, coverage, and provenance references.
- Generation APIs accept task scope and bounded analysis controls, not client-supplied authoritative portfolio values, evidence, prices, or recommendation identity.
- Material writes require idempotency keys and immutable append semantics.
- Recommendation generation and user decision are separate requests.
- No endpoint accepts or emits broker order instructions in this phase.
- Errors distinguish validation, authorization, stale/unavailable data, policy rejection, and provider failure without leaking sensitive details.
- External content is never accepted as a direct tool instruction or canonical state mutation.

## Human decision boundary

```text
Research → Analysis → Recommendation → User Decision

Never: Research → Analysis → Recommendation → Automatic Execution
```

External/open-source projects may provide adapters, data sources, analytical engines, or research tools. Atlas validates their outputs and remains the canonical source of user financial truth, portfolio state, provenance, recommendation authority, authorization, decisions, and outcomes.

## Final domain decision

Investment Intelligence should be a **first-class Rules Service intelligence domain that extends the existing Market Intelligence, forecast/recommendation, goal, decision-journal, and outcome architecture**. It should introduce a canonical investment data layer and deterministic portfolio analytics, then place AI synthesis above those validated boundaries.

The requested object list should not become a one-to-one table explosion. `Security`, `Company`, transactions/lots, snapshots, and valuations are canonical foundations; Market/Filing/News/Earnings objects are immutable evidence; findings, signals, theses, risk assessments, and portfolio impact are versioned derived values; and InvestmentRecommendation/RecommendationEvidence/RecommendationOutcome extend existing recommendation and decision infrastructure.

The user remains the final decision-maker. BUY/ADD/HOLD/REDUCE/SELL/WATCH are recommendation semantics only. No automatic trading or execution is part of this design.

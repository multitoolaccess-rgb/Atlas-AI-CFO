# Atlas Investment Intelligence — INV-08 AI Investment Committee

**Status:** Implemented, bounded analysis foundation
**Methodology:** `investment-committee/v1`
**Scope:** Typed, evidence-first committee analysis; no recommendation lifecycle or execution

## 1. Objective

INV-08 turns validated Atlas investment evidence into a structured committee conclusion. It is an analysis layer for later recommendation, reporting, tracking, and evaluation phases. The LLM is an interpreter of supplied evidence; Atlas contracts and deterministic validators remain authoritative.

```text
Frozen Atlas evidence packet
  -> bounded specialist context
  -> strict specialist payload
  -> evidence/temporal validation
  -> attributed specialist finding
  -> Bear + Bull challenge findings
  -> strict Chair payload
  -> deterministic confidence
  -> CommitteeFinding
```

No canonical security, market, fundamental, macro, quant, portfolio, recommendation, or decision record is overwritten.

## 2. Implemented files

- `services/rules-service/app/investments/committee_contracts.py`
- `services/rules-service/app/investments/evidence_validator.py`
- `services/rules-service/app/investments/confidence.py`
- `services/rules-service/app/investments/committee_adapters.py`
- `services/rules-service/app/investments/committee_orchestrator.py`
- `services/rules-service/app/investments/committee_evaluation.py`
- `services/rules-service/tests/test_investment_committee.py`

## 3. Specialist architecture

The implementation uses bounded logical roles, not independent agent services:

- **Fundamental:** receives fundamental, filing, and earnings evidence.
- **Technical:** receives technical and market evidence.
- **Macro:** receives macro and market evidence.
- **Quant:** receives quant, market, and calculation evidence.
- **Portfolio:** receives portfolio and calculation evidence only.
- **Risk:** receives all relevant evidence categories for risk review.
- **Bear:** receives the same frozen analytical packet and attacks assumptions and contrary evidence.
- **Bull:** receives the same frozen packet and develops the strongest supporting case.
- **Chair:** receives the packet plus sanitized prior specialist findings and produces a view/thesis.

The default flow invokes the six core roles, then Bear, Bull, and Chair. The model receives bounded references, excerpts, canonical numeric values, hashes, and timestamps. It does not receive a database handle, credentials, unrestricted user profile, raw provider payload, or unrelated account data.

## 4. Contracts

`committee_contracts.py` defines strict frozen Pydantic contracts with forbidden extra fields and bounded collections/text:

- `EvidenceItem` and immutable `EvidencePacket`;
- `CommitteeContext` with owner, subject, `analysis_as_of`, input hashes, and context hash;
- `ModelFindingPayload` and `ModelChairPayload` for model output;
- `AgentFinding` and `CommitteeFinding` with server-attributed role/model metadata;
- `ConfidenceAssessment` with server-computed score and methodology;
- `CommitteeRun` with status and sanitized failure state;
- `ResearchFinding`, `RiskAssessment`, `InvestmentThesis`, `RecommendationDraft`, and `Abstention` handoff contracts.

`RecommendationDraft` is intentionally `analysis_only` or `abstain` and has no action enum, broker, order, execution, transfer, or money-movement field. The INV-09 recommendation lifecycle remains separate.

All analysis timestamps require timezone-aware UTC values. Numeric claims are finite Decimal strings. Model metadata includes provider, model, model version, and prompt-template version, but no credentials or raw prompts.

## 5. Evidence validation

`evidence_validator.py` validates:

- packet hash and evidence-reference identity;
- packet/context owner and security scope;
- packet/context `analysis_as_of` equality;
- source retrieval ordering;
- future evidence rejection;
- missing/unknown evidence rejection;
- stale evidence disclosure requirements;
- citations restricted to the frozen packet;
- numeric claims equal to canonical packet numeric values;
- observed-fact claims use source evidence;
- calculated-metric claims use calculation evidence;
- finding scope, run identity, and timestamps.

Failures are rejected or converted to an explicit abstained run. The validator does not repair, search for, or invent citations.

## 6. Point-in-time and revisions

A committee run has one immutable `analysis_as_of`. Evidence references whose `as_of` is later than that boundary are rejected. The packet carries source IDs, source hashes, evidence state, and timestamps from the earlier INV-01 through INV-07 contracts. Revised source data must arrive as a new packet/context hash; the committee does not overwrite prior runs.

Technical and quantitative lookbacks remain governed by their canonical INV-05/INV-07 projections. The committee consumes their references rather than recalculating them or admitting future observations.

## 7. Bull/Bear challenge and Chair

Bear and Bull are separate attributed findings and are both retained on `CommitteeRun`. Bear is invoked before Bull. The Chair receives the validated specialist findings and must cite packet evidence for a non-insufficient conclusion. Supporting and contradicting evidence, risks, uncertainties, disagreement, and invalidation conditions remain separate fields.

A challenge uses `challenge_committee`, requires a new run ID, preserves owner and security scope, links `original_run_id`, and recalculates the new run hash. The original run object is not mutated. There is no recommendation supersession lifecycle in this phase.

## 8. Confidence methodology

Confidence is an analysis-reliability score, not a probability of return and not a recommendation conviction score. The model cannot provide it. `confidence.py` computes versioned `committee-confidence/v1` from:

- packet evidence coverage: 50%;
- observed evidence quality: 30%;
- agreement among non-abstained specialist directions: 20%.

The result records score, band, component fractions, drivers, limitations, and methodology. Missing, stale, unavailable, conflicting, or incomplete evidence lowers the inputs or causes abstention; no unavailable value is converted to zero evidence silently. Historical calibration remains INV-12 scope.

## 9. Model/provider boundary

`CommitteeModel` is a small provider-neutral protocol. `FixtureCommitteeModel` is deterministic and is used for all tests. `OllamaCommitteeModel` is an optional adapter over Atlas's existing `app.services.llm_client` and is never selected automatically by this domain module. No live LLM call is required for INV-08 validation.

The adapter frames external excerpts as untrusted data. It receives only a role projection and returns JSON-compatible data that must pass strict Pydantic parsing and evidence validation. Malformed output, unavailable model output, unsupported citations, future evidence, or unsupported numeric claims produce a safe failure state.

## 10. Prompt-injection defense

Provider excerpts are sanitized bounded strings and remain data. They are never parsed as instructions, tool calls, or policy. The committee adapter has no execution tools and no access to the assistant's financial tool registry. Tests include instruction-like external text and verify it remains inert context rather than changing authority or exposing data.

## 11. Privacy and ownership

`CommitteeContext` is owner-scoped. The orchestrator can validate a caller owner before consuming context. Packet items cannot contain another owner or security. Role projections omit `owner_id`, account IDs, credentials, and raw provider responses. Public security analysis and private portfolio context remain separate at the packet-construction boundary.

No public API was added in INV-08, so existing authentication and route envelopes are unchanged. A future read-only route must validate ownership before returning a run and must never accept client-authored canonical financial facts.

## 12. Persistence and API boundary

The implementation is intentionally in-memory/domain-level. `CommitteeRun` is an immutable value contract; persistence and read-only analysis-run routes were not added because the bounded slice does not require speculative tables or API surface. Future persistence must be additive, append-only, owner-scoped, and preserve packet/context/finding hashes. A challenge must always create a new record.

No recommendation, decision, outcome, notification, report, or tracking persistence was changed. Those belong to INV-09 through INV-12.

## 13. Evaluation harness

`committee_evaluation.py` provides the minimum offline pre-authority checks for:

- factual grounding and context hash;
- evidence coverage and citation correctness;
- strict completed-run structure;
- run-hash replay consistency;
- deterministic confidence reproducibility;
- stale-data detection;
- numeric invented-number detection;
- Bull/Bear preservation;
- prompt-injection resistance at the contract boundary;
- owner isolation.

The test suite uses deterministic fixture responses, so it requires no network, credentials, or live model. This harness does not claim historical outcome calibration, investment-performance validation, walk-forward replay, or full backtesting; those remain INV-12 responsibilities.

## 14. Failure states

The run contract supports `complete`, `abstained`, and `failed` semantics with typed failure codes including insufficient data, invalid evidence, stale context, temporal violation, specialist failure, schema failure, evidence failure, unresolved conflict, and model unavailability. Failed/abstained runs never contain a Chair finding.

The current orchestrator returns an abstained run for model/schema/evidence failures rather than retrying indefinitely or producing a best-effort conclusion. Any future retry policy must be bounded and idempotent.

## 15. Safety and non-goals

INV-08 does not:

- create BUY, SELL, HOLD, ADD, REDUCE, or WATCH recommendation lifecycle records;
- modify existing recommendations, decisions, holdings, accounts, or portfolio state;
- call a broker or brokerage API;
- place orders or transfer money;
- access or introduce credentials;
- activate SEC, FRED, Treasury, BLS, BEA, news, market, or brokerage providers;
- create migrations, scheduled ingestion, or public APIs;
- implement reports, tracking, notifications, or historical backtesting;
- implement production UI;
- permit the LLM to author financial facts, calculations, evidence IDs, or confidence scores.

The Chair produces a typed analytical view such as constructive, neutral, cautious, mixed, or insufficient evidence. It is not an executable instruction and is not an INV-09 recommendation.

## 16. Dependencies and provider evaluation

No dependency was added. The repository already provides Pydantic contracts and an Ollama client abstraction. Large agent frameworks, embedded Fincept/OpenBB/QuantConnect components, brokerage libraries, and provider-specific UI were not adopted. Existing Atlas deterministic research contracts remain authoritative. Fixture-based validation is sufficient for this phase because no live provider is required by the approved INV-08 scope.

## 17. Rollback

Rollback is additive: stop calling the committee service or feature-gate future callers while retaining any immutable run values that have been produced. Existing assistant behavior, deterministic portfolio/research calculations, recommendations, decisions, and outcomes remain unchanged. No destructive migration or history rewrite is needed.

## 18. Validation

Focused validation for this implementation:

```text
../../.venv-rules/bin/python -m pytest -q tests/test_investment_committee.py
15 passed

../../.venv-rules/bin/python -m pytest -q \
  tests/test_investment_foundation_contracts.py \
  tests/test_investment_market_data.py \
  tests/test_portfolio_intelligence.py \
  tests/test_investment_fundamentals.py \
  tests/test_technicals.py \
  tests/test_investment_macro.py \
  tests/test_investment_quant.py \
  tests/test_market_intelligence_foundation.py \
  tests/test_routes_holdings.py
112 passed

../../.venv-rules/bin/python -m pytest -q \
  tests/test_routes_assistant.py \
  tests/test_assistant_streaming.py \
  tests/test_market_intelligence_foundation.py \
  tests/test_routes_holdings.py
81 passed

../../.venv-rules/bin/python -m compileall -q app/investments
passed

git diff --check
passed
```

The broader repository contains unrelated dirty dashboard/backend/UI work and previously documented dashboard period-validation failures. Those files were not changed or included in this phase.

## 19. Relationship to INV-09

INV-09 owns actionable recommendation semantics, deterministic suitability/policy gates, conviction authority, existing recommendation lifecycle integration, decision capture, and user-facing recommendation UI. INV-08 supplies typed findings, evidence coverage, Bull/Bear dissent, a Chair view, and a non-actionable analysis-only handoff. INV-08 does not begin INV-09 or make the committee production-authoritative without the evaluation thresholds and later gates approved by the program architecture.

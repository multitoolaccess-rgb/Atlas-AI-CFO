# Atlas Investment Intelligence — Consolidated Execution Plan

**Status:** Active execution plan — documentation and INV-PERSIST-03 repair underway
**Authority:** Existing INV-01–INV-HARDEN-01 implementation records, UI/UX architecture and roadmap, canonical project tracker, and repository tests
**Scope:** Safe completion of the investment application boundary, followed by gated UI delivery

## Executive decision

Atlas has validated investment-domain foundations through INV-11 and a partially implemented UI investment roadmap. The remaining architectural gap is the durable, owner-scoped, server-owned application boundary between canonical investment contracts and future UI consumers.

The immediate priority is to complete INV-PERSIST-03. UI-08 must remain blocked until a fresh readiness gate proves that the server can provide recommendation, committee, evidence, decision, and outcome projections without browser reconstruction.

```text
INV-01–07 canonical evidence and research
        ↓
INV-08 committee finding
        ↓
INV-09 investment recommendation
        ↓
INV-PERSIST-03 trusted repository/application boundary
        ↓
owner-scoped typed APIs
        ↓
UI-08 recommendation review
        ↓
INV-11 decision/outcome history
        ↓
INV-12 evaluation and trust review
```

## Current repository state

- Main branch remains the repository integration branch.
- The project tracker reports the bounded personal-use Phase 6 product roadmap complete.
- The worktree contains unrelated dirty backend, dashboard, settings, cash-flow, and UI changes. These are immutable for this work and must not be staged or modified.
- INV-PERSIST-03 partial files are staged or locally modified and require repair before commit.
- UI-08 is not started.

## Phase assessment

### INV-01 — Security identity

Complete bounded foundation. Stable provider-neutral identities and explicit unresolved, unsupported, ambiguous, and inactive states remain authoritative. Persistence must reference canonical security identity and never derive identity from holding/account/owner IDs.

### INV-02 — Market and security observations

Complete bounded foundation. Observation, as-of, known-at, retrieval, currency, adjustment basis, quality, freshness, and deterministic hashes remain authoritative. Historical outcomes must persist observation identity/hash rather than reconstruct current observations.

### INV-03 — Portfolio intelligence

Complete bounded foundation. Existing holdings/accounts remain the portfolio source. The persistence boundary stores server-computed portfolio context and snapshot hash; it does not create a second ledger or recalculate portfolio impact.

### INV-04 — Fundamental research

Complete bounded foundation. Decimal facts, filing dates, known-at semantics, revisions, and source provenance remain authoritative. Evidence packets preserve source references without duplicating calculations.

### INV-05 — Technical research

Complete bounded foundation. Adjustment-basis isolation, deterministic indicators, insufficient-history states, and observation hashes remain authoritative. No indicator calculation moves into persistence or UI.

### INV-06 — Macro intelligence

Complete bounded foundation. Units, geography, release dates, vintages, revisions, and known-at semantics remain authoritative. Macro evidence remains bounded and point-in-time validated.

### INV-07 — Quant research

Complete bounded foundation. Returns, volatility, drawdown, Sharpe, beta, explicit benchmark identity, and zero-price fail-closed behavior remain authoritative. Outcome persistence stores canonical results and does not recalculate them.

### INV-08 — AI Investment Committee

Complete bounded domain layer. Committee runs/findings and frozen evidence packets are typed, evidence-linked, point-in-time validated, and deterministic. The missing application responsibility is immutable durable storage and owner-scoped retrieval.

### INV-09 — Investment recommendations

Complete bounded domain layer. `BUY`, `ADD`, `HOLD`, `REDUCE`, `SELL`, and `WATCH` are canonical action values, separate from lifecycle status. Conviction, thesis, risks, invalidation, committee linkage, portfolio context, and recommendation hash are server-owned. The missing responsibility is a trusted repository projection and durable application boundary.

### INV-10 — CIO reporting

Complete bounded in-memory projection. Report persistence, archive, delivery, and scheduling remain future work. INV-PERSIST-03 must preserve report-compatible hashes and references but must not expand into a new report subsystem.

### INV-11 — Decision and outcome tracking

Complete bounded domain layer, incomplete durable application boundary. Human decisions use `accept`, `reject`, `defer`, `modify`, and `no_action`. Outcomes may evaluate a recommendation without a decision or explicitly reference a human decision. Decision linkage must be explicit, optional, owner-scoped, and immutable.

### INV-HARDEN-01

Complete and authoritative. Security identity, point-in-time, evidence provenance, benchmark identity, zero-price safeguards, and future-data rejection must survive persistence and retrieval.

## UI assessment

### UI-01

Architecture/planning checkpoint complete. It governs Atlas-native shell reuse, evidence-first presentation, server-owned authority, explicit uncertainty, accessibility, responsiveness, and no-execution semantics.

### UI-02

Investment navigation is implemented. Keep route compatibility and do not activate new data surfaces before their contracts are ready.

### UI-03

Daily Brief is implemented over existing Market Brief infrastructure. Keep it separate from full CIO-report persistence and do not fabricate recommendations from Market Brief data.

### UI-04

Portfolio Intelligence is implemented over existing account/holding APIs. Preserve partial and unknown states; richer historical portfolio intelligence requires a future dedicated projection.

### UI-05

Security Research is implemented with existing server-mediated projections and explicit unavailable research lenses. Do not fill unavailable INV-02–08 projections with client-derived values.

### UI-06

Financial visualization adapter is complete and validated. Retain Recharts and require server-owned normalized chart payloads with source, timestamps, units, freshness, and table fallback.

### UI-07

EvidenceDrawer is complete and reusable. It must consume the future bounded investment evidence packet directly, without React assembling provenance.

### UI-08

Blocked pending INV-PERSIST-03 readiness. It may begin only after recommendation, committee, evidence, decision, and outcome APIs pass owner, temporal, lifecycle, hash, idempotency, and semantic-isolation gates.

### UI-09

Not started. Requires a bounded security universe, explainable filters/ranking, comparison basis, pagination, and explicit separation from recommendation authority.

### UI-10

Not started. Requires typed INV-08 context, bounded evidence citations, prompt-injection defenses, and read-only assistant tools.

### UI-11

Not started. Requires stable INV-03 risk and scenario contracts, explicit hypothetical labeling, and no portfolio mutation.

### UI-12

Not started. It is a cross-route trust, privacy, accessibility, performance, evidence, and execution-boundary gate—not a catch-all implementation phase.

## Immediate workstream: INV-PERSIST-03 finalization

### 1. Worktree and ownership control

- Preserve all unrelated dirty files.
- Remove the historical PERSIST-01 implementation document from final staging unless repository history explicitly requires it as a clearly marked blocked record.
- Keep one authoritative PERSIST-03 document.
- Stage only persistence models, repository/service, routes, schemas, migrations, focused tests, and the authoritative implementation document.

### 2. Trusted repository projection

Add a dedicated `InvestmentRepository` responsible for owner-scoped loading and validation of canonical persisted objects.

Required methods:

- `get_recommendation(owner_id, recommendation_id)`
- `get_committee_run(owner_id, run_id)`
- `get_committee_finding(owner_id, finding_id)`
- `get_evidence_packet(owner_id, recommendation_id=None, finding_id=None)`
- `get_decision(owner_id, decision_id)`
- `list_decisions(owner_id, recommendation_id)`
- `get_outcome(owner_id, outcome_id)`
- `list_outcomes(owner_id, recommendation_id)`

Routes must never deserialize recommendation JSON directly. The repository must validate schema version, first-class columns, owner/security/linkage, canonical hash, temporal fields, and explicit evidence relationships before returning domain objects.

### 3. Explicit relationships

Add first-class relationships:

```text
CommitteeRun → EvidencePacket
CommitteeFinding → EvidencePacket
Recommendation → EvidencePacket
Outcome → Recommendation
Outcome → optional HumanDecision
```

Do not use recommendation payload JSON or security-based fallback lookup to resolve evidence membership.

### 4. Decision/outcome contract

Keep `RecommendationOutcome.decision_id` optional:

- absent means recommendation-level evaluation;
- present means evaluation of a specific human decision.

Add a nullable database foreign key from outcome to investment decision. Validate owner, recommendation, hash, and temporal compatibility when present.

### 5. Decision safety

Decision POST accepts only decision type and rationale. The server derives recommendation identity, owner, hash, lifecycle, security, and timestamps. Require `If-Match` and `Idempotency-Key`. Use a durable request fingerprint and unique owner-scoped idempotency constraint. Recover unique-constraint races by rollback and fresh winner lookup.

### 6. Immutability

No update/delete application methods exist for committee, evidence, recommendation, decision, or outcome records. Canonical identity collisions with divergent payload/hash fail. Database trigger claims must be verified against supported dialects; documentation must not overstate cross-dialect guarantees.

### 7. Typed APIs

Use explicit Pydantic response models for:

- recommendation list/detail;
- committee run/finding;
- evidence packet/items;
- decisions and decision envelopes;
- outcomes and outcome lists;
- typed errors where the API convention supports them.

No raw ORM objects or unrestricted persistence JSON is returned.

### 8. HTTP validation

Add real TestClient coverage for:

- owner isolation on every read/write path;
- active/superseded/expired/withdrawn lifecycle behavior;
- If-Match mismatch;
- malformed decision commands;
- sequential and simulated concurrent idempotency;
- evidence ownership, packet membership, role separation, provenance, and future-data rejection;
- recommendation/outcome/decision linkage;
- zero-price and look-ahead behavior;
- semantic isolation from goal/forecast records.

### 9. Migration validation

Maintain the existing merge migration if it is the valid graph repair. Add one linear additive migration for explicit relationship columns, outcome decision linkage, missing first-class recommendation temporal/hash fields, and request fingerprint if required. Verify one head, importability, upgrade/downgrade behavior, and supported-dialect constraints.

## Required validation gates

### Persistence and application

- canonical domain ingestion;
- invalid linkage/hash/temporal rejection;
- immutable identity behavior;
- explicit relationship resolution;
- outcome decision linkage;
- owner-scoped repository methods.

### API

- typed response models;
- owner isolation;
- no raw ORM leakage;
- lifecycle and If-Match behavior;
- idempotent retries and conflicts;
- evidence and outcome routes.

### Regression

- INV-08 committee tests;
- INV-09 recommendation tests;
- INV-11 outcome/decision tests;
- INV-HARDEN-01 tests;
- existing goal/forecast recommendation/decision/outcome tests;
- broader Rules Service suite where practical.

### Static and database

- Python compilation;
- relevant lint/type checks;
- Alembic one-head/import/round-trip checks;
- `git diff --check`;
- execution-boundary import scan;
- staged ownership review.

## Completion gate for INV-PERSIST-03

INV-PERSIST-03 is complete only when UI-08 can consume:

```text
InvestmentRecommendation
        ↓
CommitteeFinding
        ↓
bounded EvidencePacket
        ↓
HumanDecisionRecord
        ↓
RecommendationOutcome history
```

without browser-side reconstruction, provider calls, current-time substitution, goal/forecast API reuse, or fabricated values.

## Future sequencing after INV-PERSIST-03

1. Rerun the UI-08 contract-readiness gate.
2. Implement UI-08 recommendation review and human decision, without execution controls.
3. Complete any required INV-10 report archive boundary only if UI-03/UI-12 needs it.
4. Implement UI-09 discovery/comparison from separate screening contracts.
5. Implement UI-10 contextual Scout from typed read-only context.
6. Implement UI-11 risk/scenario presentation from server-owned hypothetical projections.
7. Implement INV-12 evaluation/calibration/replay and retention policy.
8. Implement UI-12 integration/trust certification.

## Safety and non-goals

This plan adds no:

- broker integration;
- order creation;
- trading;
- execution;
- transfers;
- money movement;
- portfolio mutation;
- automatic rebalancing;
- autonomous scheduling;
- browser-side financial calculations.

## Rollback

All implementation should remain additive and feature-gated. Disable the investment persistence flag and remove future route activation without altering existing goal/forecast records, portfolio holdings, Market Briefs, or historical investment snapshots. Never roll back by deleting immutable analytical or decision history.

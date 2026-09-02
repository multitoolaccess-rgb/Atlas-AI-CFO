# INV-PERSIST-03 — Investment Persistence Boundary

## Scope

This phase completes the additive server-owned persistence boundary for the validated INV-08 committee, INV-09 recommendation, and INV-11 decision/outcome contracts. It does not implement UI-08 or alter the separate goal/forecast workflow.

## Architecture

`canonical domain object → InvestmentPersistenceService validation/linkage → immutable SQLAlchemy snapshot → owner-scoped typed API projection`.

The existing partial INV-PERSIST-01/02 models and routes were retained only as the additive investment namespace; outcome persistence was completed with `investment_outcome_records`. The trusted service remains the ingestion path for canonical records. Client-facing decision POST accepts only decision type and rationale, while recommendation identity, owner, hash, security, and lifecycle are loaded server-side.

## Durable records

- `investment_committee_runs`
- `investment_committee_findings`
- `investment_evidence_packets`
- `investment_recommendation_records`
- `investment_decision_records`
- `investment_outcome_records`

Canonical payload snapshots retain typed domain JSON, hashes, timestamps, evidence linkage, methodology, and portfolio snapshot references. Outcome rows are separate from recommendation rows.

## APIs

The additive routes are:

- `GET /api/v1/investments/recommendations`
- `GET /api/v1/investments/recommendations/{recommendation_id}`
- `GET /api/v1/investments/committee/findings/{finding_id}`
- `GET /api/v1/investments/recommendations/{recommendation_id}/evidence`
- `GET /api/v1/investments/recommendations/{recommendation_id}/decisions`
- `POST /api/v1/investments/recommendations/{recommendation_id}/decisions`
- `GET /api/v1/investments/recommendations/{recommendation_id}/outcomes`

All queries derive owner scope from the authenticated JWT subject. No goal/forecast recommendation table or route is used.

## Trust, security, and immutability

`InvestmentPersistenceService` accepts validated Pydantic domain objects for analytical ingestion and validates owner, security, linkage, temporal ordering, and identity conflicts before flush. Historical analytical records, decisions, and outcomes have no update/delete application paths and are protected by immutable identity checks; the database migration adds identity and owner-scoped uniqueness constraints. Decision writes require `If-Match` and `Idempotency-Key`, use a unique owner-scoped idempotency hash, and append one decision record. Integrity conflicts are caught by the trusted service and mapped to an explicit conflict envelope.

The API never accepts client-authored action, conviction, committee, evidence, portfolio snapshot, or canonical timestamps. It never imports execution, broker, order, transfer, or portfolio mutation services.

## Point-in-time and provenance

Canonical `analysis_as_of`, recommendation `as_of`, evidence packet timestamps, decision timestamps, outcome evaluation timestamps, evidence state, methodology, source references, and hashes are persisted in the domain payload without replacement by request/render time. The domain outcome evaluator remains responsible for baseline selection and look-ahead protection; the persistence service stores the resulting validated outcome and does not recalculate metrics.

## Validation

- Dedicated final boundary suite: 28 passed.
- Affected INV-08/09/11, hardening, outcome, decision, and route suites: 130 passed.
- `python -m compileall -q app`: passed.
- Alembic script graph: one head (`X12a1b2c3d4e5`); investment revisions import successfully.
- `git diff --check`: passed.
- Execution-boundary scan: no broker/order/trade/transfer/execution imports or calls.

## Known limitations

The repository's current application has no production ingestion caller wired from an investment scheduler/analysis job into `InvestmentPersistenceService`; records must be supplied by a trusted server-side caller. Portfolio context remains the canonical payload supplied by INV-09. The API exposes bounded typed envelopes; analytical ingestion remains internal and has no public mutation route by design.

## UI readiness

The boundary supplies UI-08 with server-owned recommendation, committee, bounded evidence, decision-history, and outcome-history paths without React reconstruction. UI-08 remains not implemented in this phase.

## Explicit non-goals

No new intelligence, scoring, financial calculations, provider integration, broker integration, order creation, execution, money movement, portfolio mutation, automatic rebalancing, goal/forecast semantic reuse, or UI work.

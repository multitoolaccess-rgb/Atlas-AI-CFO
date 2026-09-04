# INV-PERSIST-01 — Investment Intelligence Persistence Boundary

## Scope

This phase adds a separate persistence namespace for validated INV-08/09/11
investment records. It does not modify the existing goal/forecast recommendation
workflow and does not implement UI-08.

## Records

The additive models are:

- `InvestmentCommitteeRun`
- `InvestmentCommitteeFinding`
- `InvestmentEvidencePacket`
- `InvestmentRecommendationRecord`
- `InvestmentDecisionRecord`

Each record carries an owner relationship, canonical identifiers, timestamps,
hashes where supplied by the domain, and bounded JSON snapshots. Investment
recommendation actions remain `BUY`, `ADD`, `HOLD`, `REDUCE`, `SELL`, and `WATCH`.
Human decisions remain `accept`, `reject`, `defer`, `modify`, and `no_action`.

## APIs

When `ATLAS_INVESTMENT_PERSISTENCE_ENABLED` is enabled, the additive routes are:

- `GET /api/v1/investments/recommendations`
- `GET /api/v1/investments/recommendations/{recommendation_id}`
- `GET /api/v1/investments/committee/findings/{finding_id}`
- `GET /api/v1/investments/recommendations/{recommendation_id}/evidence`
- `GET /api/v1/investments/recommendations/{recommendation_id}/decisions`
- `POST /api/v1/investments/recommendations/{recommendation_id}/decisions`

The route layer only presents persisted snapshots and does not calculate
investment metrics or recommendation semantics.

## Security and immutability

Queries derive owner identity from the authenticated JWT subject and constrain
all lookups by owner. The migration adds database triggers rejecting update and
delete operations on all five tables. Foreign keys and owner indexes support
bounded lookup and fail-closed access.

## Temporal and provenance behavior

Canonical timestamps and hashes are stored separately from serialized payloads;
the API returns the persisted values without replacing them with request or
browser time. Evidence packets are linked by owner, security, and packet ID.
The payload is bounded JSON and does not expose provider credentials or raw
provider objects.

## Decisions

Decision writes require both `Idempotency-Key` and `If-Match`. The precondition
must match the persisted recommendation hash. Idempotency keys are stored only
as SHA-256 digests. A repeated key replays the existing decision, and decisions
never mutate recommendations or portfolio records.

## Explicit limitations

This phase currently establishes the durable schema and read/write transport,
but does not add a trusted ingestion adapter from the INV-08/09/11 domain
orchestrators into these tables. Such an adapter must validate canonical domain
objects before persistence and must be wired by the investment application
owner before production data is written. Outcome-history projection is not yet
exposed because no investment-specific durable outcome table exists.

## Non-goals

- UI-08 or any later UI phase
- goal/forecast recommendation migration or reinterpretation
- new investment calculations or AI analysis
- broker, order, execution, transfer, or portfolio mutation capability

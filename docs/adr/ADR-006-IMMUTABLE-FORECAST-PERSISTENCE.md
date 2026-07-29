# ADR-006: Immutable Forecast Persistence and Versioned Read APIs

- **Status:** Proposed
- **Date:** 2026-07-26
- **Scope:** Phase 1 forecast persistence and read APIs
- **Related:** ADR-004, ADR-005, issue #3

## Context

ADR-005 made Rules Service authoritative for deterministic projections and
deferred forecast storage and APIs. Phase 1 must persist reproducible results
without migrating the UI, changing projection mathematics, introducing
probabilities, or pretending that the current single-user authorization model
is household tenancy.

The current service has one Alembic head (`Q5h1i2j3k4l5`), supports SQLite in
local development and CI, and is designed for PostgreSQL. Goals are scoped by
`user_id`; their existing `target_amount` uses a legacy `Float`. The Phase 0
projection module accepts explicit Decimal-compatible strings and returns
immutable dataclasses with deterministic scenario outputs.

## Decision

### Stable forecast identity and goal linkage

A `forecast` is a stable logical series, not one calculation. Its public ID is
an application-generated UUID encoded as a lowercase canonical string. A
forecast is uniquely identified by:

- transitional `user_id`;
- `goal_id`;
- `forecast_kind` (`goal_projection` in Phase 1); and
- `currency`.

The database enforces that tuple as unique. The goal link is fixed for the
life of the forecast. Goal archive does not remove forecasts, and foreign keys
use restrictive deletion semantics so history cannot disappear implicitly.
Phase 1 supports one goal per forecast. Multi-goal forecasts require a later
ADR because they change calculation and conflict semantics.

`forecasts.lifecycle_state` is a mutable lifecycle field on the stable identity
row (initially `active` only). It is deliberately separate from the immutable
reasoning, assumptions, outputs, and provenance in `forecast_versions`. Phase
1 supplies no lifecycle mutation route; later lifecycle behavior must not
rewrite a version row.

### Immutable versions

Each calculation creates a `forecast_version` beneath the stable forecast.
Versions have a UUID, a monotonically increasing integer `version_number`, and
unique `(forecast_id, version_number)`. Version rows are never updated or
deleted by application code. Database-level update and delete guards protect
them on supported dialects; the migration removes those guards before an
explicit schema downgrade.

The mutable forecast identity row may advance `latest_version_number` inside
the same transaction that inserts a version. Historical versions remain
addressable and retain their original goal, input, assumption, output,
freshness, and provenance snapshots.

### Decimal money and currency

No Phase 1 persistence or API field accepts or emits binary floating-point
money.

- Python uses `Decimal`.
- The canonical input/hash envelope encodes component and contribution money as
  bounded, exact, unrounded canonical Decimal strings. Its v1 scale limit is
  defined below; it is not a fixed-scale display contract.
- Queryable monetary columns use `NUMERIC(38, 2)` through SQLAlchemy
  `Numeric(..., asdecimal=True)` and are checked by cross-dialect round-trip
  tests.
- Every snapshot and response carries an uppercase ISO 4217 currency code.
- Phase 1 accepts only `USD`, matching ADR-005. It does not infer currency
  from user preferences or source accounts.
- Persisted outputs are quantized to cents with `ROUND_HALF_EVEN`.

The legacy goal `Float` is not silently rewritten in this phase. Its value is
converted with `Decimal(str(value))`, validated, and recorded without a claim
of restored precision in the immutable input snapshot with
`source_representation: "float"`,
`conversion: "Decimal(str(value))"`, and `precision_restored: false`.
Conversion cannot restore precision that the legacy Float already lost, and
Phase 1 must not present a Float-derived amount as exact. Contract fixtures
must cover Float-to-canonical-string boundary cases. A canonical Goal Decimal
migration remains a separate reviewed change.

Rates, inflation, and other fractional assumptions are not stored in
`NUMERIC(38, 2)`. Their authoritative representation is an unrounded canonical
Decimal string in the immutable assumption and input snapshots. If a later
queryable fractional column is justified, it must use `NUMERIC(38, 18)` or a
reviewed higher scale, with an explicit precision contract.

### Versioned snapshots and calculation identity

Every version stores:

- `snapshot_schema_version`;
- `hash_schema_version`;
- `model_version`, identifying the forecast contract;
- `calculation_version`, copied from the projection module's
  `MODEL_VERSION`;
- canonical normalized input snapshot;
- complete assumption snapshot;
- complete output and driver snapshot;
- source-data freshness snapshot;
- provenance references; and
- `calculated_at`, `data_as_of`, `created_at`, and currency.

The four required version labels are bounded printable-ASCII database strings.
They must be nonempty and contain no whitespace; the persistence boundary
rejects rather than normalizes them.

Snapshots are deterministic canonical JSON: UTF-8, sorted keys, no
insignificant whitespace, ISO dates/timestamps, and Decimal values encoded as
canonical strings. They do not contain raw transactions, uploaded statements,
credentials, or tokens.

All instants in snapshots, APIs, and observability use timezone-aware UTC
RFC 3339 timestamps with a `Z` suffix. Date-only projection inputs retain
their documented date semantics and are not silently converted to local-time
instants. Hashing uses the canonical unrounded Decimal strings required to
reproduce a calculation; output or display rounding is not an input to the
hash.

The persisted target-status decision is sourced from an explicit unrounded
decision basis in the calculation result and is stored with its canonical
Decimal operands: `unrounded_ending_balance` and
`unrounded_target_amount`, compared by `greater_than_or_equal` for the `base`
scenario. `atlas-target-decision/v1` records that basis and the resulting
boolean. A UI or API display amount must never recompute or alter that boolean
after rounding. The Phase 1 contract tests must include a rounding-boundary
case that proves the displayed value cannot change the stored target status.

### Input-state hashing and idempotent generation

`input_state_hash` is lowercase SHA-256 over the canonical normalized input,
validated `atlas-projection-assumptions/v1` snapshot, freshness, and provenance
snapshot. Hash construction is versioned by `hash_schema_version`; the
assumption-schema identifier is included in its canonical bytes. Calculation
and model versions are separate columns, so the same financial state under a
new calculation or contract creates a new version.

The database enforces uniqueness on:

`(forecast_id, input_state_hash, model_version, calculation_version)`.

The sole Phase 1 write action is authenticated forecast generation. It
requires an `Idempotency-Key`; only its SHA-256 digest is stored. Repeating the
same key and request returns the existing result. Reusing the key for a
different input hash returns HTTP 409 `idempotency_conflict`. A different key
with identical normalized state and versions resolves to the existing version
rather than creating a duplicate.

### Data freshness and provenance

Generation preserves the Phase 0 freshness validation before any write. The
snapshot records the calculation date, source `data_as_of`, permitted maximum
age, actual age, source type, source stable identifier or aggregate identifier,
source update timestamp, and a source-state hash.

Rules Service receives explicit canonical state. It does not query
Finlynq-owned tables directly. Provenance references describe inputs without
copying user statements or transaction histories into forecast rows.

### Canonical projection-state envelope

Finlynq owns ingestion and canonical financial state. A typed adapter or
application-service boundary produces `atlas-projection-state/v1`; Rules
Service consumes that envelope and owns forecast calculation and persistence.
The adapter is the only sanctioned bridge between the services for Phase 1.
This contract prevents Rules Service from coupling to Finlynq database tables.

The envelope has these bounded fields:

- `schema_version` and `canonicalization` metadata, including canonical JSON
  and hash-algorithm versions;
- transitional `user_id` and `goal_id` identifiers;
- `as_of_timestamp` in UTC and a three-letter explicit currency;
- typed `current_value_components`, each with a bounded component kind,
  canonical Decimal amount string, source reference, and observed timestamp;
- typed contribution or investable-cash-flow inputs needed by the projection;
- freshness policy and observed age;
- bounded provenance references containing source-system identifier, stable
  record or aggregate identifier, timestamp, count, and hash;
- missing-data indicator codes; and
- deterministic confidence or reconciliation state enums when available.

It excludes raw statements, raw transactions, uploaded files, credentials,
unbounded free-form source payloads, and unnecessary personal information. A
source-state hash covers the bounded provenance and normalized components;
Rules Service stores that hash and references, not the source records.
Contract-boundary validation surfaces only sanitized field locations and stable
error categories. Raw Pydantic validation errors are internal and must never
cross the boundary. Caller-facing locations contain only bounded schema-owned
field names and safe indices; unknown client fields use the fixed
`<extra-field>` token without echoing their key text.

For `atlas-projection-state/v1`, component and contribution money strings are
bounded, exact, unrounded canonical Decimal strings with at most 38 digits
excluding sign and decimal point, at most 18 fractional digits, and at most 40
encoded characters (sign and decimal point included). These are input/hash
bounds, not persisted fixed-scale or display rounding: no value is rounded or
truncated to fit. Queryable monetary columns and output/display values use a
fixed scale only where their later contract explicitly requires it. Fractional
assumptions are not accepted in this v1 envelope; their distinct unrounded
representation remains part of the later approved assumption-snapshot slice.

All v1 envelope collections are order-insensitive and canonicalized before
hashing. Current-value and contribution entries sort by `(kind,
source_reference, observed_at)`; provenance entries sort by `(source_system,
reference_id, observed_at)`; missing-data codes sort lexically. Duplicate
identity keys are rejected rather than resolved arbitrarily. No v1 envelope
collection has financial meaning in its input order.

### Transitional ownership and authorization

Phase 1 retains `forecasts.user_id -> users.id`. Every generation and read
query first resolves the authenticated JWT subject to the local user and then
filters by `user_id`. A missing or cross-user forecast returns 404 to avoid
confirming another user's resource.

`user_id` remains transitional. No field, route, or index is named or
documented as permanent household scope, and Phase 1 performs no household
backfill or dual-read migration.

### Trusted generation boundary

The end-user generation route is `POST /api/v1/goals/{goal_id}/forecasts`.
Its only sanctioned execution path is:

```text
authenticated request
  -> server-derived user identity
  -> server-loaded, user-authorized goal
  -> trusted canonical-state adapter
  -> atlas-projection-state/v1
  -> deterministic projection
  -> immutable forecast persistence
```

The route has no client-supplied financial-state request body in Phase 1. The
only client control inputs are the required `Idempotency-Key` and the
conditional `If-None-Match` or `If-Match` headers; the repository's established
correlation header may be accepted solely for observability. `forecast_kind` is
fixed as `goal_projection`. The server selects the approved, versioned
assumption profile and records it in the immutable assumption snapshot.
User-selected assumption profiles or field-level overrides are not accepted in
Phase 1; a later reviewed contract must enumerate any allowed fields, bounds,
canonicalization, and separate `user_selected_assumptions` snapshot before they
can be introduced.

Strict request validation rejects unknown JSON fields rather than ignoring
them. In particular, a client cannot provide `user_id`, `household_id`,
balances or net worth, financial-state-derived contributions, canonical
snapshot content, account-derived currency, freshness timestamps, source
identifiers, provenance, transaction or statement data, reconciliation state,
an input-state hash, or model/calculation versions. The client neither supplies
nor signs `atlas-projection-state/v1`.

Authentication derives transitional user scope, and goal authorization occurs
before the adapter is invoked; a missing or cross-user goal returns 404 without
canonical-state retrieval. The trusted adapter obtains authoritative state from
the sanctioned Finlynq boundary, creates the versioned envelope, and generates
provenance only from server-side source references. Rules Service validates the
envelope and freshness, then server code computes the input-state hash. No
separate trusted service-generation API is introduced in Phase 1. The bounded
`shadow_validate` command uses this same adapter path.

### API contract

The bounded API surface is:

- `POST /api/v1/goals/{goal_id}/forecasts`
- `GET /api/v1/forecasts`
- `GET /api/v1/forecasts/{forecast_id}`
- `GET /api/v1/forecasts/{forecast_id}/versions`
- `GET /api/v1/forecasts/{forecast_id}/versions/{version_number}`

The POST is the persistence command, not mutable forecast CRUD. There are no
PUT, PATCH, or DELETE forecast routes. Read collections use stable cursor
pagination and deterministic ordering. Responses include schema version,
currency, freshness, provenance, model/calculation versions, canonical money
strings, links, and an ETag derived from forecast ID and latest version.

Generation accepts `If-Match` for an existing forecast and
`If-None-Match: *` for first creation. A stale expected version returns HTTP
409 with stable code `forecast_version_conflict`, the current ETag and latest
version number, and no financial payload. Constraint races are translated to
the same stable contract after the transaction is rolled back and current
state is re-read.

### Transaction and concurrency model

Generation runs in one database transaction:

1. authorize and load the user-owned goal;
2. normalize, validate, hash, and calculate outside any long-held write lock;
3. get or create the stable forecast;
4. lock or otherwise serialize the forecast identity row;
5. re-check idempotency and `If-Match`;
6. allocate the next version number;
7. insert the immutable version and advance the latest pointer; and
8. commit.

PostgreSQL uses row locking. SQLite uses a short write transaction plus unique
constraints and conflict retry. A unique-race loser re-reads the winning row;
it returns that row if idempotent, otherwise HTTP 409.

### Pre-enable shadow validation

Phase 1 uses an explicitly invoked, bounded operator command rather than
synchronous request-path shadowing. The planned command is:

`python -m app.forecasts.shadow_validate --user-id <id> --goal-id <id> --limit 1 --dry-run`

It requires one explicitly scoped user and goal, requires an explicit limit no
greater than one in Phase 1, invokes the canonical-state adapter, generates a
proposed forecast, and compares it with the selected reference when supplied.
`--dry-run` is the default and produces no persistence. The command never
enables, overrides, or bypasses default-off persistence flags; a non-dry write
mode is unavailable until separately authorized and the relevant flag is
enabled.

Its structured observability output contains only stable user/goal/forecast
identifiers, adapter and snapshot schema versions, source-state and
input-state hashes, calculation/model versions, freshness outcome, comparison
outcome, flag state, correlation ID, and elapsed time. It excludes raw
financial payloads, money values, statements, credentials, and tokens. It is
not invoked by a read request and adds no user-facing latency. Scheduled or
background validation is deferred until this bounded validation has succeeded
and is separately approved.

### Migration, retention, and rollback

One Phase 1 Alembic revision follows `Q5h1i2j3k4l5` and creates the forecast
identity table before the version table, indexes, uniqueness constraints, and
immutability guards. It contains no backfill and does not modify existing
goals, recommendations, or financial tables.

Normal application rollback disables generation, disables new read routes,
and deploys the previous application while leaving the additive tables intact.
Schema downgrade is permitted only when the forecast tables are empty or an
approved export and deletion procedure has run. Downgrade removes immutability
guards, then the version table, then the forecast table.

Forecast versions are retained immutably during development and default-off
validation. Phase 1 has no user-facing purge endpoint, no administrative
deletion behavior in the contract-test slice, and no cascade that can silently
remove a historical version. The schema retains user/subject scope so a future
approved deletion process can locate all applicable forecasts.

This is a provisional rollout gate, not a permanent retention policy:
persistence must not be enabled for external multi-user production use until
retention and user-deletion policy is approved. Legal hold, account deletion,
backup deletion, and household migration remain deferred decisions.

### Feature flags and rollout

Two server-side flags default off:

- `ATLAS_FORECAST_PERSISTENCE_ENABLED`
- `ATLAS_FORECAST_READ_API_ENABLED`

Rollout order is migration with both flags off, explicitly invoked bounded
operator validation, read API enablement for authorized test users, persistence
enablement, and measured expansion. The production UI does not consume these
routes in Phase 1. Rollback first disables generation and then reads. External
multi-user production enablement is blocked by the provisional retention gate.

## Consequences

- Forecast history becomes reproducible and independently readable.
- Storage grows append-only and requires explicit retention policy later.
- The current user-scoped authorization boundary remains visible and tested.
- SQLite/PostgreSQL Decimal and concurrency behavior need explicit parity
  tests.
- The existing goal `Float` can limit source precision even though persisted
  forecast snapshots never use floats or claim to restore that precision.
- ADR-005's forecast schema/API deferral is resolved by this ADR when accepted;
  all other ADR-005 deferrals remain.

## Non-goals

- UI migration
- Recommendation models
- Decision journal
- Household migration
- Monte Carlo probability
- Autonomous execution
- Dependency modernization
- Legacy product-name cleanup

## Deferred decisions

- A permanent retention, legal-hold, account-deletion, backup-deletion, and
  household-migration policy.
- Any scheduled or background shadow-validation design after bounded operator
  validation succeeds.
- A reviewed canonical Goal Decimal migration.

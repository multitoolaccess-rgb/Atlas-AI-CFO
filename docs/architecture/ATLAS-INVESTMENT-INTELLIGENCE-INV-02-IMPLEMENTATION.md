# INV-02 Market & Security Data — Implementation Record

**Status:** Complete — contract, adapter, normalization, and validation boundary implemented; no provider activation or persistence migration.

## Architecture decision

INV-02 extends the existing `market_intelligence` adapter and provenance
architecture conceptually, while keeping the new provider-neutral identity and
observation contracts in `services/rules-service/app/investments/`. No external
library was added. Existing Finnhub/SEC adapters remain the only provider
implementations and remain server-gated/default-off.

The new contracts are immutable Pydantic values. Security IDs are derived from
an explicit namespace/value pair; symbol and exchange are aliases, not identity.
Observations preserve observation, as-of, and retrieval timestamps, currency,
source, source identifier, freshness/data state, adjustment basis, quality, and
a deterministic content hash.

## Implemented scope

### Adapter and normalization pipeline

```text
Fixture or external provider payload
  → SecurityDataProvider interface
  → provider adapter DTO boundary
  → deterministic normalization
  → canonical SecurityIdentity / MarketObservation validation
  → provenance and content hash
```

`SecurityDataProvider` exposes only security lookup, current observation, and
historical observation capabilities. `FixtureSecurityDataProvider` proves the
interface offline. `normalize_security` and `normalize_observation` are the
only paths from provider-shaped dictionaries to canonical contracts; they
normalize symbols, exchanges, instruments, currencies, Decimal values, UTC
timestamps, freshness, adjustment basis, and source identifiers. Provider
field names and payload objects do not enter canonical models.

- Explicit security states: resolved, unresolved, unsupported, ambiguous,
  inactive.
- Instrument classification including equity, ETF, mutual fund, index, ADR,
  cash, and unknown.
- Effective-dated provider/exchange identifiers.
- Exchange-aware stable identity derivation.
- Immutable observation contract with finite Decimal-safe values.
- Explicit observed, estimated, stale, missing, and unknown data states.
- Point-in-time ordering and future-as-of validation.
- Invalid observations rejected before canonical use.
- Deterministic observation hashing.
- Provider-neutral `SecurityDataProvider` interface and offline fixture provider.
- Sanitized malformed-payload failures for numeric, currency, timestamp,
  instrument, provenance, and future-as-of errors.
- Freshness derived from observation versus retrieval time using a bounded
  one-day policy; explicit estimated/missing/unknown states are preserved.

## Provenance and quality

Canonical observations preserve provider/source, provider record identifier,
normalization version, observed/as-of/retrieval timestamps, currency, data
state, adjustment basis, quality, and deterministic hash. Invalid or ambiguous
provider data is rejected rather than converted into a usable observation.
Historical payloads can be passed through the same interface without rewriting
point-in-time metadata; adjusted and unadjusted observations remain distinct.

## Provider and dependency decision

No new external dependency is required for INV-02. Existing Atlas
`market_intelligence` adapters, bounded cache, pacing, normalized failures, and
source metadata remain the integration infrastructure for live providers. The
new provider boundary is provider-neutral and can wrap those adapters later.
No provider credentials, subscriptions, network calls, or scheduled ingestion
were added.

## Intentionally deferred

- SQL persistence and migrations.
- New HTTP routes.
- Live provider calls or scheduled ingestion.
- Corporate-action processing beyond the adjustment-basis contract.
- Automatic identity resolution or silent ticker matching.
- Broker, order, trading, transfer, or money-movement functionality.

These remain bounded follow-up work only after lifecycle, ownership, indexing,
retention, and migration review.

## Validation

Focused INV-02, adapter, normalization, and adjacent provider/holding regression tests:

```text
89 passed
```

Static validation:

```text
../../.venv-rules/bin/python -m compileall -q app/investments
```

passed.

The repository still contains two known unrelated dashboard baseline failures:
`test_dashboard_flows_rejects_malformed_period_query` and
`test_dashboard_breakdown_rejects_malformed_period_query`. They were not
modified by INV-02.

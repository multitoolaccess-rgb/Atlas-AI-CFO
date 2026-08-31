# INV-06 Macro Intelligence — Implementation Record

## Status

This record documents the bounded INV-06 macro foundation. It does not claim live macro ingestion, persistence, APIs, or recommendation logic.

## Architecture and authority

Macro data follows the Atlas evidence boundary:

```text
Provider payload → adapter → normalization → strict validation → MacroObservation → deterministic derived metric
```

`MacroObservation`, `MacroDerivedMetric`, and `MacroContext` are Atlas-owned contracts in `app/investments/macro.py`. `MacroDataProvider` and `FixtureMacroProvider` in `macro_adapters.py` keep provider payloads outside the canonical model. No LLM is involved.

## Canonical observation model

Each observation preserves:

- indicator identity;
- geography;
- explicit value and unit;
- daily, weekly, monthly, quarterly, annual, or event frequency;
- observation period;
- release and effective dates;
- `as_known_at` and retrieval timestamps;
- initial, revised, estimated, or derived status;
- explicit data state;
- source evidence reference;
- optional revision linkage.

Values are finite Decimal text. Units are not inferred, missing values are not converted to zero, and geography is never silently substituted.

## Implemented transformation

The current bounded transformation is the 10-year minus 2-year Treasury yield spread. It requires matching percent-denominated, observed, as-known-at-valid observations and retains both source observation IDs. No BUY/SELL/HOLD/ADD/REDUCE/WATCH mapping or investment conclusion is produced. Regime classification is not enabled in this slice.

## Point-in-time and revision handling

An observation cannot claim to be known before its release date or retrieval time. Historical consumers filter observations by `as_known_at`, preventing later releases from leaking into earlier analysis. Revisions are represented as new observation IDs with `revised` status and `revision_of`; originals remain immutable.

## Provider/dependency strategy

No new dependency was added, no FRED/Treasury/BLS/BEA provider was activated, and no network call or credential was introduced. The fixture adapter proves the boundary offline. Future live integration must reuse Atlas provider controls and undergo source-term, rate-limit, freshness, and provenance review.

## APIs and persistence

No API or migration was added. The contract-only implementation is additive and can be removed or feature-gated without changing existing Atlas history.

## Testing

Focused tests cover values, units, geography, release dates, as-known-at vintage, revision linkage, provider normalization, invalid numeric/unit input, deterministic yield spread, and exclusion of later observations from historical context. Static compilation and relevant investment/Market Intelligence suites are required before commit.

## Security and execution boundary

External macro content is treated as data. Inputs are bounded and sanitized by strict contracts. No portfolio data is included. No broker, order, trade, transfer, money movement, recommendation, portfolio mutation, or execution capability exists.

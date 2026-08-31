# INV-04 Fundamental Research — Implementation Record

## Status

This record documents the bounded INV-04 foundation implemented in the Rules Service. It does not claim that live SEC ingestion, persistence, APIs, or a complete valuation engine exist.

## Architecture and authority

Fundamental data follows the Atlas boundary:

```text
Provider payload → adapter → normalization → strict validation → canonical fact → deterministic metric
```

The canonical objects are `FundamentalFact`, `FundamentalMetric`, and `FundamentalResearch` in `app/investments/fundamentals.py`. Provider-specific payloads are accepted only by `fundamental_adapters.py`; they do not enter the canonical model. Security identity is reused from INV-02.

Atlas remains authoritative for normalized facts, provenance, timestamps, currency, and derived calculations. An LLM is not involved and cannot create or modify facts.

## Implemented facts

`FundamentalFact` supports a bounded initial vocabulary: revenue, gross profit, operating income, net income, EPS, cash, debt, assets, liabilities, equity, operating cash flow, capital expenditures, and shares outstanding.

Each fact preserves:

- security identity;
- unit and original currency;
- annual, quarterly, TTM, or instant period basis;
- period start/end;
- filing date;
- `as_known_at` and retrieval timestamps;
- reported, estimated, restated, or derived status;
- source evidence reference;
- optional revision linkage.

Values are canonical finite Decimal text. Unknown or missing values are not converted to zero. Currency is preserved and no FX conversion is performed.

## Deterministic metrics

`derive_metrics` currently calculates a minimal margin set from matching, non-estimated facts:

- gross margin;
- operating margin;
- net margin;
- operating-cash-flow margin.

Metrics preserve source fact IDs, period basis, as-of timestamp, formula version, and `derived` versus `unknown` state. Incompatible periods/currencies and zero denominators produce unavailable/unknown metrics rather than fabricated values.

## Provider strategy

`FundamentalDataProvider` is provider-neutral. `FixtureFundamentalProvider` supplies deterministic offline records for tests. No live provider, SEC credential, network call, dependency, migration, or scheduled ingestion was added. EdgarTools was not adopted; the existing Atlas SEC adapter remains the future integration point and should be evaluated before adding a parser dependency.

## Restatements and point-in-time correctness

Facts are immutable contract values. A restatement uses a new fact ID, `restated` status, and `revision_of` link; the original fact remains available. A fact cannot be known before its filing date, and all timestamps require timezone-aware UTC values. This prevents later filings from leaking into earlier historical analysis.

## Privacy and execution boundary

The current foundation contains public/company-level fact contracts only. It does not expose owner holdings, account IDs, cost basis, or portfolio weights, and it adds no routes. No broker, order, trade, transfer, money movement, portfolio mutation, or execution capability exists.

## Testing and rollback

Focused tests cover Decimal normalization, invalid/non-finite values, currency preservation, reporting and knowledge dates, restatement linkage, provider normalization, provenance retention, deterministic margins, denominator failure, and no-network behavior. The additive contract-only change can be removed or feature-gated without migration or historical rewrite.

## Not implemented

The following remain future work: SEC filing/fact live adapters and persistence, company profiles, statement assembly, annual/quarterly trend services, valuation ranges, estimates/guidance contracts, API exposure, and recommendation integration. These must be implemented only with additional provenance and financial-correctness fixtures.

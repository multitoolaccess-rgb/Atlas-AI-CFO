# INV-05 Technical Research — Implementation Record

## Status

This record documents the bounded technical-research foundation implemented for INV-05. It does not claim prediction, recommendation, persistence, or trading functionality.

## Architecture

Technical research consumes INV-02 `MarketObservation` contracts:

```text
Canonical market observations → same-basis price series → validation → deterministic indicators → technical research
```

`PriceSeriesPoint`, `TechnicalSignal`, and `TechnicalResearch` are Atlas-owned contracts in `app/investments/technicals.py`. No provider-specific type or LLM output enters the canonical technical model.

## Series and validation

`build_price_series` deterministically orders observations, rejects duplicate timestamps, rejects missing/unknown observations, requires a single explicit adjustment basis, preserves currency, and carries each source observation hash. No calendar dependency or external technical-analysis library was added; existing Atlas market-calendar/provider infrastructure remains the source boundary for future session-aware ingestion.

## Indicators implemented

The current bounded set is:

- trailing simple moving average (`SMA`), default lookback 5;
- RSI, default period 14;
- rolling close-to-close volatility, default lookback 5.

Indicators use only observations through the series’ final timestamp. Insufficient history returns `insufficient_history` with no fabricated numeric value. Constant prices produce zero volatility. The implementation intentionally does not include EMA, MACD, ATR, Bollinger Bands, prediction, or action mapping.

## Provenance and determinism

Every signal includes security-independent source observation hashes, lookback, as-of timestamp, adjustment basis, calculation version, and state. The research projection includes all input hashes and a deterministic research hash. Identical canonical inputs produce identical output.

## Numerical and data-quality policy

Price and volume boundary values use finite Decimal text. Missing, stale, unknown, or invalid observations do not become zero or current data. Adjusted and unadjusted observations cannot be mixed. Technical states are evidence states only and never imply BUY, SELL, HOLD, REDUCE, ADD, or WATCH.

## Dependencies and provider status

No dependency was added. No provider was activated, no credentials were introduced, no network calls were made, and no scheduled ingestion was enabled. TA-Lib/pandas-ta were evaluated as unnecessary for this initial auditable slice; any future adoption must remain behind an Atlas adapter and undergo license, numerical, and data-quality review.

## APIs, persistence, and rollback

No API or database migration was added. The contract-only implementation is additive and can be removed or feature-gated while retaining INV-02 observations and all prior history. Future read APIs must follow existing authentication/ownership and response conventions.

## Testing

Focused tests cover deterministic ordering and hashes, duplicate timestamps, adjustment-basis isolation, missing observations, SMA, RSI insufficiency, constant-price volatility, source provenance, and reproducibility. Static compilation and relevant INV-01 through INV-04, Market Intelligence, and holdings tests are required before the phase commit.

## Safety boundary

This is read-only technical evidence. It adds no prediction engine, broker, order, trade, transfer, money-movement, portfolio mutation, or execution capability.

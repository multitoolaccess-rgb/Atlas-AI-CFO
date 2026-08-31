# INV-07 Quant Research — Implementation Record

## Status

This record documents the bounded INV-07 quantitative research foundation. It does not claim portfolio optimization, full backtesting, prediction, recommendations, or execution.

## Architecture

Quant research consumes INV-05 canonical `PriceSeriesPoint` values, which already enforce a single explicit adjustment basis, currency, ordering, and source observation hashes:

```text
Canonical price series → Decimal returns/risk calculations → versioned QuantMetric → QuantResearch
```

Atlas-owned `QuantMetric` and `QuantResearch` contracts live in `app/investments/quant.py`. No provider-specific or LLM types enter the canonical result.

## Calculations implemented

The bounded initial set includes:

- cumulative simple return: `P_last / P_first - 1`;
- trailing mean simple return;
- trailing population volatility;
- maximum drawdown from running peak;
- Sharpe ratio only when an explicit risk-free rate is supplied;
- beta only when an explicitly supplied benchmark series is timestamp-aligned and has non-zero variance.

The methodology is price-return based, not total-return based. Dividend treatment is therefore not inferred. Annualization is not applied in this slice; frequency remains explicit as the source observation frequency.

## Safety and data quality

Missing or insufficient observations produce explicit states. Risk-free rates are never assumed to be zero. Benchmarks are never silently selected. Mixed adjustment bases are rejected upstream by INV-05. Metrics retain lookback, price basis, as-of timestamp, methodology version, and source observation hashes.

## Point-in-time correctness

Calculations use only the supplied series through its final timestamp. Future observations cannot influence the result. Historical universe survivorship is not modeled by this contract-only slice and remains an explicit limitation for future dataset/backtest work.

## Dependencies and providers

No external dependency was added. PyPortfolioOpt, Riskfolio-Lib, skfolio, vectorbt, Backtrader, and LEAN were not embedded because optimization and full backtesting are outside this bounded phase. No provider, credentials, network call, migration, API, or scheduled job was added.

## Testing and rollback

Focused tests cover deterministic returns, volatility, drawdown, insufficient history, explicit risk-free-rate requirements, benchmark alignment and failure, and timezone validation. Compilation and relevant INV-01 through INV-06 suites are required before commit. The additive contract layer can be removed or feature-gated without changing prior observations or history.

## Safety boundary

Quantitative outputs are evidence only. They do not map to actions, recommendations, portfolio mutations, broker orders, trades, transfers, money movement, or execution.

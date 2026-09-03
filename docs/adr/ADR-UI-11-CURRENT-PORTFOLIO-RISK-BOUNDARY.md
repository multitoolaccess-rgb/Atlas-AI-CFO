# ADR: UI-11 Current-Only Portfolio Risk Boundary

- **Status:** Accepted
- **Date:** 2026-09-03
- **Scope:** UI-11 first slice

## Decision

UI-11 uses a separate server-owned read/projection boundary with two typed contracts:

```text
owned accounts and holdings
  -> InvestmentPortfolioBaseline/v1
  -> InvestmentRiskScenario/v1 preview
  -> authenticated typed API
  -> read-only UI
```

The first slice is explicitly:

- current-only owner-scoped portfolio baseline;
- descriptive position count, observed value, total value, and data-quality metrics;
- single-currency aggregation only when all contributing values are complete and compatible;
- bounded, on-demand hypothetical position-value delta preview;
- deterministic canonical hashes and stable position ordering;
- explicit unavailable, unknown, unsupported, and incompatible states.

The browser supplies bounded intent only. Owner scope, positions, financial values, timestamps, source identifiers, source hashes, baseline identity, and result hashes are derived or validated by the server.

## Deliberate exclusions

UI-11 does not define or calculate a portfolio risk score, probability, VaR, expected shortfall, optimizer, target allocation, volatility aggregate, covariance, correlation, drawdown history, liquidity, sector/geography risk, FX normalization, or investment recommendation.

Goal/forecast Scenario Lab records remain goal-scoped and are not reused as portfolio-risk identity or methodology. Investment recommendations, committee findings, decisions, outcomes, and execution state remain separate and read-only.

No scenario result persistence or migration is required for this slice because the preview is reconstructed on demand from the current owner-scoped source rows. Historical reconstruction is unavailable and cannot be requested through this boundary.

## Source and temporal rules

Accounts and holdings are current source rows. Every baseline is marked `current_only`. Source timestamps are preserved in the typed projection; future-dated account or holding timestamps fail closed. The service does not assign a historical meaning to a caller-supplied `as_of`.

Only USD account values are currently aggregateable. Unknown or mixed currencies leave total value and exposure-derived aggregation unavailable. Unresolved or unsupported holding identities remain visible with explicit state and omission reasons.

## Security and recovery

The authenticated JWT subject resolves the local owner before loading accounts or holdings. Public responses omit the internal owner ID and account identifiers. Cross-owner or missing position references use the route's non-enumerating not-found behavior. Preview requests do not write any database rows.

The feature is behind the existing server-owned investment read/persistence gate. Disabling that gate makes the API unavailable; no browser field can enable it.

## Consequences

This decision makes a trustworthy bounded UI-11 surface available without inventing historical or advanced risk semantics. Advanced metrics, a canonical security-master adapter, historical portfolio snapshots, FX/classification/liquidity sources, and persisted scenarios require separate contracts and decisions before implementation. UI-12 and INV-12 remain unstarted.

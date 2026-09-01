# Atlas Investment UI/UX - UI-06 Implementation

**Status:** Implemented
**Scope:** Financial visualization adapter

## Purpose

UI-06 standardizes presentation of server-owned financial time-series data without creating a second calculation engine in the browser. It provides a reusable chart shell with explicit units, as-of context, source, freshness/data state, loading and empty handling, and an accessible data-table fallback.

## Component

`ui/components/charts/FinancialTimeSeriesChart.tsx` accepts a normalized, already-calculated time-series payload:

- timestamped points
- series labels and colors
- unit
- as-of timestamp
- source label
- canonical freshness/data state

It composes the existing Atlas `ChartLine` and `ChartWrapper` primitives. Existing Recharts remains the charting dependency. No new library was added.

## Canonical data boundary

The adapter is presentation-only. It does not calculate returns, volatility, drawdown, margins, portfolio exposure, benchmark statistics, indicators, or recommendation states. Callers must supply canonical server-owned values and preserve the source contract's timestamp, adjustment basis, omissions, provenance, and methodology metadata.

The adapter does not perform timestamp filtering or repair invalid data. Point-in-time selection remains a backend responsibility. Missing, unknown, stale, unavailable, and insufficient-history states remain explicit.

## Accessibility and responsive behavior

Charts include a semantic region label, a screen-reader summary, explicit units and dates, and an optional semantic table containing the same observations. The data table supports keyboard access and horizontal scrolling for dense datasets. Controls have visible focus states and touch-sized targets. Color is not the sole carrier of financial meaning.

## Performance

The component reuses the existing Recharts wrapper and renders the table only when requested, limiting initial DOM work. No additional state-management framework, chart library, or provider SDK was introduced.

## Testing and validation

Focused tests cover canonical metadata, table fallback, explicit insufficient-history handling, empty data, and the no-execution boundary. UI-02 through UI-05 route regressions, typecheck, ESLint, production build, and `git diff --check` are required validation gates.

## Security and human boundary

No broker, order, trade, execution, transfer, money movement, rebalance, or portfolio mutation capability exists in this adapter. It renders analytical data only.

## Limitations and future handoff

UI-06 does not introduce an OHLCV/zoom/pan library. Lightweight Charts remains a future compatibility and accessibility spike. UI-07 owns the fuller evidence/provenance experience, while later UI phases own recommendation review, comparison, risk, and outcome workspaces.

## Rollback

Stop using `FinancialTimeSeriesChart` and retain the existing Atlas chart primitives. No persistence, API, or backend changes are required to roll back.

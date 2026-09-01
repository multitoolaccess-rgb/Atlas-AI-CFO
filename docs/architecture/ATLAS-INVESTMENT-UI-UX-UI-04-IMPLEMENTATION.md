# Atlas Investment UI/UX - UI-04 Implementation

**Status:** Implemented
**Route:** `/portfolio/intelligence`

## Scope

UI-04 adds a dedicated, read-only Portfolio Intelligence workspace. It complements the existing `/portfolio` holdings-management route rather than replacing it. The workspace answers what is held, how much is observed, which positions are incomplete, and where value is concentrated.

The Daily Investment Brief remains owned by UI-03. UI-04 does not duplicate that executive experience.

## Data sources

The route uses the existing `rulesService` client and existing Atlas API contracts:

- `DashboardSummary` for server-reported portfolio value and synchronization context.
- `Account[]` for owner-scoped account labels and account filtering.
- `Holding[]` for canonical position rows, quantities, values, symbols, prices, cost basis, and instrument types.

No frontend investment calculations are introduced. The page only displays server-owned values and derives presentation-only filtering and sorting. It does not calculate exposure, returns, volatility, Sharpe, beta, drawdown, or recommendation semantics.

## Information architecture

1. Portfolio context header with scope and server synchronization timestamp.
2. Compact KPI strip for portfolio value, position count, largest observed position, and observed price coverage.
3. Concentration view showing ranked observed market values.
4. Dense positions table with search, account filter, sort controls, keyboard-accessible inspection, and responsive horizontal overflow.
5. Data-quality summary preserving incomplete values.
6. Position detail dialog linking to existing Market Intelligence.

The existing Portfolio route remains the place for import, add, edit, delete, and refresh workflows. UI-04 deliberately contains no portfolio mutation controls.

## Trust and provenance

Unknown and incomplete values are rendered as `Unavailable` or explicit incomplete coverage. The UI does not default missing values to zero. Synchronization/as-of context is shown when supplied by the existing summary contract. Detailed source-hash provenance belongs to the backend contracts and future evidence workspace phases.

## Responsive and accessibility behavior

The desktop view uses compact aligned numeric columns and a horizontally scrollable semantic table for narrow screens. Search and filters have labels, table headers use `scope`, position inspection is available by keyboard, dialogs use modal semantics, and data-quality meaning is communicated with text rather than color alone.

## Performance

The route makes three existing API reads in parallel, performs only small presentation-level filtering/sorting, and renders no additional chart dependency. No new state-management or table library was added.

## Validation

Focused UI-04 tests cover route rendering, canonical data display, incomplete positions, filtering, inspection navigation, backend error handling, and the no-execution boundary. Existing UI-02/sidebar and UI-03 brief tests are run as regressions.

## Security and human boundary

No broker, order, execution, transfer, money movement, rebalance, or automatic portfolio mutation capability was added. Position detail links to research context only. Existing API authorization remains responsible for owner scope.

## Dependencies

No dependencies were added. Existing Next.js, React, Tailwind, Lucide, Atlas layout primitives, and API client are reused.

## Limitations and future handoff

UI-04 does not implement:

- UI-05 Security Research workspace
- new portfolio backend projections
- advanced allocation charts without canonical chart payloads
- recommendation review or decision capture
- outcome analytics
- broker integration or trading
- new persistence or API routes

The current backend exposes holdings/accounts and dashboard summary, but not a dedicated INV-03 serialized portfolio snapshot endpoint. UI-04 therefore consumes the existing canonical frontend contracts and keeps richer snapshot/provenance presentation for a future backend read-model integration.

## Rollback

Disable or remove `/portfolio/intelligence`. The existing `/portfolio` route and all other Atlas routes remain unchanged.

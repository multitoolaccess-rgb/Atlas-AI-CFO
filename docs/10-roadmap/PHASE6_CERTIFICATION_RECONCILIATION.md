# Phase 6 Clean-main Certification Reconciliation

## Scope

This record reconciles the 14 browser failures from clean-main certification run
`31868205933` and the local baseline run (`93 passed, 14 failed, 1 skipped`).
The correction is limited to canonical information-architecture expectations,
shared URL-state continuity, and explicit handling of server-owned unavailable
responses. It does not change financial calculations, backend contracts,
feature flags, ownership, privacy, or execution authority.

## Failure classification

| # | Failing journey | Classification | Evidence and bounded correction |
|---:|---|---|---|
| 1 | `atlas-enhanced-pages`: Debts KPI summary | A — stale test expectation | `/debts` is a compatibility redirect. Wealth owns the page at `/wealth?view=debts`; the journey now asserts the canonical Wealth heading and debt surface. |
| 2 | `atlas-enhanced-pages`: debt composition donut | A — stale test expectation | Same migrated Wealth ownership; no duplicate Debts route was restored. |
| 3 | `atlas-enhanced-pages`: debt table | A — stale test expectation | Same migrated Wealth ownership; specialist debt content remains under the Wealth tab. |
| 4 | `atlas-enhanced-pages`: payoff projections | A — stale test expectation | Same migrated Wealth ownership; authoritative debt presentation is unchanged. |
| 5 | `atlas-enhanced-pages`: no Debts time selector | A — stale test expectation | The point-in-time contract is asserted at `/wealth?view=debts`, not the retired standalone route. |
| 6 | `atlas-enhanced-pages`: cross-page Debts navigation | A — stale test expectation | The sidebar exposes Wealth, then its Debts tab owns the specialist view. |
| 7 | `dashboard-filter`: Cash Flow range retained when selecting Income | C — genuine product defect | `AtlasFilterContext` updated the URL while `PageTabs` read a stale query snapshot. Synchronous URL-state continuity plus live-query tab selection now preserves `range=30D`. |
| 8 | `dashboard`: legacy simulation workspace and visual modules | A — stale test expectation | Mission Control no longer renders client-side simulation calculators. The tests now assert the server-backed Scenario Lab destination and absence of the legacy slider surface. |
| 9 | `dashboard`: legacy Money Flow Simulator slider | A — stale test expectation | Unsupported client-side calculation behavior is not restored; the canonical Scenario Lab link is covered instead. |
| 10 | `imports-and-analyst`: `/recommendations` analyst panel | A — stale test expectation | Recommendations are owned by Decisions. The compatibility URL now asserts `/decisions?view=recommendations` and honest no-recommendation recovery copy. |
| 11 | `market-brief-operationalization`: Market Briefs link on the page | A — stale test expectation | `/market-briefs` remains a bookmark-compatible redirect to `/market-intelligence`; no duplicate Market Briefs navigation link is reintroduced. |
| 12 | `navigation`: Decisions console failure | B — expected server-owned recovery | The merged frontend had been probing an uncontracted forecast collection URL. The typed Decisions client now fails closed without that request, preserving the honest no-recommendations state and eliminating the browser 404. |
| 13 | `sidebar-navigation`: Activity active-link assertion | A — stale test expectation | Activity remains reachable from Cash Flow / Transactions but is no longer a duplicate primary sidebar destination. |
| 14 | `universe`: Financial Universe route heading | A — stale test expectation | `/universe` redirects to `/wealth?view=universe`; the journey now asserts Wealth ownership and the nested Financial Universe heading. |

## Availability observability

Known server-owned availability responses for Market Intelligence,
Scenario Lab, and the forecast recommendation read gate are handled by the
shared client only when they are HTTP `503` responses on the exact endpoint
families. The client emits a bounded `console.info` diagnostic without the raw
payload, while unexpected statuses, authentication failures, JavaScript
errors, and unhandled promise rejections remain observable as errors.

Route-mocked regression coverage proves that a Scenario Lab `503` produces no
Atlas API error and that a synthetic `500` remains observable. The UI remains
default-off and server-authoritative; no client override or local financial
calculation was added.

## Focused evidence

- Typed/API and shared-tab Vitest: 9 passed.
- Route-mocked Scenario Lab journey: 4 passed.
- Previously failing isolated live-stack journeys: 14 passed.
- TypeScript: passed.
- ESLint: passed.
- Tracker validation and deterministic rendering: passed.

The complete Phase 6 certification matrix is rerun only after this correction
is merged back to clean `main`.

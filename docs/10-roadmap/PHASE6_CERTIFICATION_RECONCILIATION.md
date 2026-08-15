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

## Post-merge certification discovery

The first clean-main rerun after PR #56 completed the backend and frontend
matrices but exposed three remaining browser expectation issues:

| Journey | Classification | Reconciliation |
|---|---|---|
| `goals-phase2-slice`: forecast → recommendation journey | A — stale test expectation | The merged client correctly fails closed because no authoritative forecast collection route exists. The journey now verifies that Goals renders no forecast/recommendation and does not attempt a decision write. |
| `navigation`: Scenario Lab console diagnostics | B — expected default-off recovery | Chromium reports the resource-level `503` even though the client handles the server-owned disabled response. The navigation assertion now ignores only this exact Scenario Lab availability diagnostic; unexpected API and JavaScript errors remain failures. |
| `scenario-lab-route-mocked`: disabled recovery auth diagnostics | D — test fixture defect | The route-mocked shell now supplies a synthetic profile response, preventing the shared profile/401 retry path from producing unrelated console errors. Scenario Lab error handling remains covered, including observable synthetic `500` behavior. |

The focused reconciliation rerun passed the updated Goals journey (1), full
navigation journey (15), and Scenario Lab route-mocked journey (4), for 20
browser checks across the affected specs. This correction remains test and
observability scope only; server-owned feature flags, sanitized responses, and
financial authority are unchanged.

## Clean-main certification result

After PR #57 merged, clean main was certified locally at
`4f80f0ca8a6114e5c68bc101c59a7d5b44e77eb7`:

- Rules Service: `1,298 passed, 10 skipped, 1 xfailed`.
- Finlynq: `106 passed`.
- Root cross-service/governance tests: `33 passed`.
- Scenario and migration focus: `22 passed, 3 skipped`; the complete Rules
  suite also passed.
- Frontend Vitest: `630 passed` across `70` files.
- TypeScript, ESLint, and production build: passed. Build emitted only the
  known backend-unavailable static-generation warnings.
- Canonical live-stack Playwright: `108 passed, 1 skipped` across `109` tests.
- Scenario Lab route-mocked coverage was included in the canonical run: `4
  passed`; the corrected Goals recovery journey also passed.
- Tracker/status/render, handoff, shell syntax, and diff checks: passed.

The required hosted manual clean-main certification was attempted three times
(the initial dispatch `31896160628`, its rerun, and dispatch `31896202299`).
Each run failed before any job step because GitHub reported: “The job was not
started because recent account payments have failed or your spending limit
needs to be increased.” The failure is recorded as an external billing/
availability blocker, not a product or test result. No hosted heavy result is
claimed as passed, and `phase-6-complete` remains absent.

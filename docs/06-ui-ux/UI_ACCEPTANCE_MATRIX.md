# Atlas UI Acceptance Matrix — Phases 0–6

- **Audit date:** 2026-08-15
- **Audited commit:** `8efcdaeeebeea3742cd5376ed06e730342960a49`
- **Certification evidence:** canonical Wave 6 browser matrix `108 passed, 1 policy-defined skip`; screenshot matrix `1/1 passed`.
- **Scope:** final information architecture, complete local browser certification, isolated synthetic acceptance, and read-only personal route/readiness acceptance; no personal write journey was performed.
- **Related:** [Capability Matrix](../10-roadmap/ATLAS_CAPABILITY_MATRIX.md), [Personal-Use Readiness Report](../07-engineering/PERSONAL_USE_READINESS_REPORT.md), [Remediation Backlog](../10-roadmap/REMEDIATION_BACKLOG.md).

## Evidence sources

- `ui/lib/informationArchitecture.ts`, `ui/middleware.ts`, `ui/lib/moneyRoutes.ts`
- `ui/components/layout/Sidebar.tsx`, shared PageLayout/PageHeader/PageTabs/Analytical primitives
- Primary route implementations under `ui/app/`
- `ui/__tests__/e2e/navigation-route-mocked.spec.ts`
- `ui/__tests__/e2e/scenario-lab-route-mocked.spec.ts`
- `ui/__tests__/e2e/market-brief-operationalization.spec.ts`
- `ui/__tests__/e2e/goals-phase2-slice.spec.ts`
- `ui/__tests__/e2e/appearance-art-direction.spec.ts`
- `ui/__tests__/e2e/appearance-screenshot-matrix.spec.ts`
- Phase 6 clean-main evidence: canonical Playwright `108 passed, 1 skipped`; scoped axe, keyboard, reduced motion, responsive overflow and appearance/profile checks passed.

## Acceptance matrix

| Route / owner | Discoverable and URL state | Loading/empty/error/recovery | Keyboard/screen reader | Responsive/overflow | Appearance/motion | Evidence and disposition |
|---|---|---|---|---|---|---|
| Mission Control `/` | Primary Home link; bounded summaries and Scenario Lab deep link | Loading skeleton, error banner, bounded no-data summaries | Skip link, landmarks, buttons/links have labels | Canonical and focused browser coverage | Shared shell/profile matrix | **Accepted**; no full analytical duplicate remains |
| Cash Flow `/cash-flow` | Four URL-synced tabs; legacy `/income`, `/expenses`, `/activity` preserve state | Summary/chart/detail loading and source-empty states | PageTabs keyboard behavior and table/chart semantics | Focused URL/overflow evidence; canonical matrix | Shared context bar and reduced-motion conventions | **Accepted**, with range state regression fixed in IA reconciliation |
| Plan `/plan` | Budget/commitments/calendar tabs | Transaction-derived empty/error states | Tabs and controls labelled | Appearance suite passed reduced-motion and widths | Indigo/Vermilion/Ion and light/dark evidence | **Accepted** |
| Wealth `/wealth` | Overview/assets/debts/universe tabs; `/debts` and `/universe` compatibility | Loading, unavailable, empty assets, unavailable Universe | Tables, alerts and links labelled | Canonical navigation and overflow evidence | Shared frame | **Accepted**; `/debts` and `/universe` are aliases, not duplicate owners |
| Portfolio `/portfolio` | Specialist destination; data and provider actions remain bounded | Loading, import, price/provider and empty states | Forms, modals, tables and action labels | Canonical and appearance evidence | Shared shell; semantic financial colors | **Accepted with operator gap:** real provider/portfolio data was not used |
| Goals `/goals` | Goals/forecasts/progress specialist surface | No forecast/recommendation state is honest when authority unavailable | Goal controls and decision history semantics | Focused Goals journey and read-only personal baseline reload passed | Shared shell and profile behavior | **Accepted:** personal baseline was read/reloaded without personal write journey |
| Decisions `/decisions` | Recommendations/journal/outcomes tabs; legacy redirect | No current recommendation, history unavailable, conflict and error states | Server IDs/lifecycle, action labels, alert semantics | Canonical navigation, synthetic write journey, and read-only personal availability | Shared frame | **Accepted:** write paths proven on disposable clone; personal database remained read-only |
| Market Intelligence `/market-intelligence` | Portfolio/pulse/earnings/scanner/archive tabs; `/market-briefs` redirect | Empty, provider unavailable, degraded, freshness/warning and archive detail | Citations, main landmark, scoped axe | Mobile full-bleed and no overflow passed | Dark mode and semantic colors passed | **Accepted for synthetic data; real provider readiness unproven** |
| Scenario Lab `/scenario-lab` | Scenarios/comparisons/archive plus `goal`, `scenario`, `compare` state | Disabled/no-goal/missing baseline/stale/incompatible/loading/error | Builder labels, comparison checkbox/table, tabs | 390px no overflow, keyboard journey, and canonical matrix passed | Dark/reduced-motion/Indigo/Vermilion/Ion evidence | **Accepted:** complete synthetic write journey passed; personal route/readiness remained read-only |
| Data Connections `/data-connections` | Accounts/imports/synchronization/data quality; `/accounts` redirect | Disconnected, incomplete, stale and error states from Accounts implementation | Tabs, forms, alerts | Route-mocked mobile/navigation evidence | Shared shell | **Accepted**; legacy implementation is intentionally delegated, not duplicated |
| Settings `/settings` | System link; appearance/profile and safe preferences | Profile/config errors and destructive-data confirmation states | Appearance controls use labelled selection; modals have actions | Axe and supported viewport evidence | Indigo/Vermilion/Ion, light/dark; System is implemented in provider | **Accepted with destructive-action caution:** audit did not mutate data |
| Help `/help` | System link; final domain map | Recovery/privacy/data-limitation guidance | Headings, links and recovery section | Route-mocked navigation evidence | Shared shell | **Accepted** |
| Scout `/assistant` fallback/global header | Global Scout contract and accessible fallback route | Offline assistant recovery | Keyboard-accessible fallback | Existing navigation coverage | Shared shell | **Accepted as compatibility/fallback; not a duplicate IA destination** |

## Cross-cutting acceptance

| Criterion | Evidence | Result |
|---|---|---|
| Final primary navigation has one owner per destination | Typed IA contract and Sidebar list 12 activated destinations | Pass |
| Compatibility redirects preserve meaningful query state | Middleware, money route tests, navigation route-mocked journey | Pass for documented aliases |
| No full visualization duplicated across primary pages | IA plan, Mission Control bounded summary, specialist deep links | Pass by code review; continued cleanup recommended |
| Honest server-off and unavailable states | Scenario/Market/Goals route-mocked tests and typed clients | Pass |
| No client financial calculation authority in Phase 5/6 surfaces | Scenario contract, UI client contracts, Mission Control no legacy simulator rendering | Pass; legacy compatibility code remains quarantined |
| Keyboard and screen-reader semantics | Tab/button labels, skip link, focused browser journeys, axe checks | Pass in scoped evidence |
| Reduced motion | Appearance/art-direction tests and canonical certification | Pass |
| Mobile/tablet/desktop overflow | Plan/Market/Scenario journeys and canonical certification | Pass in tested routes |
| Light/Dark/System and all accent profiles | Appearance tests and final Wave 6 canonical certification/screenshot matrix | Pass: canonical matrix and screenshot invocation passed |
| Console/page errors | Focused unexpected-500 observability, personal route sweep, and canonical certification | Pass: handled 503 recovery is bounded; no unexpected 5xx, page, or console errors in final acceptance |

## Wave 6 evidence and limitations

- The final canonical browser matrix passed `108` tests with `1` policy-defined skip; the screenshot matrix passed `1/1`. Generated screenshot artifacts were kept outside Git.
- The personal route sweep used fresh browser contexts across 12 routes: expected handled Market Intelligence `503`s only, zero unexpected 5xx, zero page/console errors, and no horizontal overflow.
- Settings destructive data-maintenance controls were not clicked. Full Scout conversational behavior was not exercised beyond placement/fallback/navigation contracts.
- Synthetic decision/outcome/scenario writes were exercised only on the disposable clone; the personal database was read-only during final acceptance.

## Recommended UI disposition

The final shell, route architecture, readiness states, accessibility behavior, and appearance matrix are suitable for the bounded single-user release candidate. Preserve compatibility routes and quarantined legacy components until a separately authorized cleanup or terminology decision.

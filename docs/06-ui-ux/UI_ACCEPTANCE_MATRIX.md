# Atlas UI Acceptance Matrix — Phases 0–6

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Scope:** final information architecture and representative local synthetic browser acceptance; no UI behavior changed.
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
| Goals `/goals` | Goals/forecasts/progress specialist surface | No forecast/recommendation state is honest when authority unavailable | Goal controls and decision history semantics | Focused Goals journey passed | Shared shell and profile behavior | **Accepted with activation gap:** enabled forecast journey not proven |
| Decisions `/decisions` | Recommendations/journal/outcomes tabs; legacy redirect | No current recommendation, history unavailable, conflict and error states | Server IDs/lifecycle, action labels, alert semantics | Canonical navigation/route evidence | Shared frame | **Accepted with activation gap:** default-off server APIs not enabled in audit |
| Market Intelligence `/market-intelligence` | Portfolio/pulse/earnings/scanner/archive tabs; `/market-briefs` redirect | Empty, provider unavailable, degraded, freshness/warning and archive detail | Citations, main landmark, scoped axe | Mobile full-bleed and no overflow passed | Dark mode and semantic colors passed | **Accepted for synthetic data; real provider readiness unproven** |
| Scenario Lab `/scenario-lab` | Scenarios/comparisons/archive plus `goal`, `scenario`, `compare` state | Disabled/no-goal/missing baseline/stale/incompatible/loading/error | Builder labels, comparison checkbox/table, tabs | 390px no overflow and keyboard journey passed | Dark/reduced-motion/canonical evidence | **Accepted for synthetic route-mocked data; enabled local activation unproven** |
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
| Light/Dark/System and all accent profiles | Appearance tests and canonical certification | Pass for tested controls; screenshot matrix partly harness-limited |
| Console/page errors | Focused route-mocked unexpected-500 observability and canonical certification | Pass for tested boundaries; transient dev chunk failures remain runner debt |

## Evidence gaps

- The screenshot matrix’s route list predates the final IA and includes aliases. It captured 126 files before stopping at a migrated route harness issue; captures are outside Git at `/tmp/atlas-phase0-6-audit-ff85ad7-screenshots`.
- A real enabled local financial journey was not run because server-owned defaults remained unchanged and no personal data/credentials were used.
- Settings destructive data-maintenance controls were inspected but not clicked.
- Full Scout conversational behavior was not exercised; only placement/fallback/navigation contracts were considered.

## Recommended UI disposition

The final shell and route architecture are suitable for continued personal-use hardening. Prioritize a canonical final-IA screenshot/acceptance harness and readiness states before adding new product surfaces. Preserve compatibility routes and quarantined legacy components until a separate cleanup wave proves safe removal.

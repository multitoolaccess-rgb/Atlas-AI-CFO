# Atlas Visual Art Direction v2.1 Route Coverage

This inventory records the navigable Atlas routes reviewed under the shared
Luminous Financial Observatory art direction. The phrase is an internal art
direction label only; it is not product copy.

## Shared grammar

- **Atmospheric canvas:** profile-aware canvas, illumination, grain, and edge vignette tokens in `styles/tokens.css`, rendered by the global shell.
- **Shell:** `PageLayout`, `Sidebar`, and `Header` provide the navigation rail, command surface, responsive gutters, focus states, and profile-aware active treatment. Overview and Financial Universe use the same shell primitives directly.
- **Page header:** `components/ui/PageHeader.tsx` establishes title, context, optional eyebrow, and action alignment without forcing a page layout.
- **Surface roles:** `surface-ambient`, `surface-working`, and `surface-focal` are reusable tonal roles. `Card`, `ChartWrapper`, and `EmptyState` consume the working/focal vocabulary where appropriate.
- **Guided states:** `EmptyState` answers what the feature is, why it matters, what is missing, and what to do next without inventing data or actions.
- **Motion:** shared transitions use transform/opacity and respect reduced-motion media preferences. Decorative Budgeting orbit motion is CSS-only and static when motion is reduced.
- **Financial semantics:** profile accent tokens are independent from positive, negative, warning, neutral, and critical financial signal tokens.

## Route inventory and evidence

The two 1440px Indigo screenshots linked in each route row are the curated representative evidence intended for repository retention under `ui/artifacts/v2.1/`. The complete six-profile responsive matrix, test reports, traces, videos, and redundant captures remain local/CI review artifacts and must not be committed wholesale. Every linked path must exist before publication; an unverified capture is not evidence of completion.

| Route | Archetype | Shared components used | Page-specific improvement | Light screenshot | Dark screenshot | Responsive validation | Remaining visual debt |
|---|---|---|---|---|---|---|---|
| `/` | Command-center dashboard | `Sidebar`, `Header`, atmospheric canvas, dashboard chart/card primitives | Preserves real intelligence focal area, chart narrative, status strip, and data-driven loading/error states | [`overview-indigo-light-1440.png`](../../ui/artifacts/v2.1/overview-indigo-light-1440.png) | [`overview-indigo-dark-1440.png`](../../ui/artifacts/v2.1/overview-indigo-dark-1440.png) | Indigo desktop + representative 390/768/1440 matrix captured | Audit dense dashboard card rhythm after capture |
| `/budgeting` | Guided onboarding and empty states | `PageLayout`, `PageHeader`, `FloatingTimeRangeBar`, `EmptyState`, `BudgetOrbit`, focal surface | Honest first-budget composition, real Add Budget workflow, Plan/Track/Adjust guidance | [`budgeting-indigo-light-1440.png`](../../ui/artifacts/v2.1/budgeting-indigo-light-1440.png) | [`budgeting-indigo-dark-1440.png`](../../ui/artifacts/v2.1/budgeting-indigo-dark-1440.png) | 390/768/1024/1440/1728 overflow checks + representative matrix captured | Budgeted populated state needs the same focal/working distinction review |
| `/portfolio` | Financial-analysis workspace | `PageLayout`, `PageHeader`, filter bar, `ChartWrapper`, `EmptyState` | Numeric hierarchy, portfolio import/add actions, holdings comparison and coverage surfaces | [`portfolio-indigo-light-1440.png`](../../ui/artifacts/v2.1/portfolio-indigo-light-1440.png) | [`portfolio-indigo-dark-1440.png`](../../ui/artifacts/v2.1/portfolio-indigo-dark-1440.png) | Indigo desktop + representative 390/768/1440 matrix captured | Dense legacy table utility labels need follow-up visual pass |
| `/income` | Financial-analysis workspace | `PageLayout`, filter bar, chart primitives | Shared analytical canvas and date controls | [`income-indigo-light-1440.png`](../../ui/artifacts/v2.1/income-indigo-light-1440.png) | [`income-indigo-dark-1440.png`](../../ui/artifacts/v2.1/income-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Page-specific chart/card density review |
| `/expenses` | Financial-analysis workspace | `PageLayout`, filter bar, chart primitives | Shared analytical canvas and date controls | [`expenses-indigo-light-1440.png`](../../ui/artifacts/v2.1/expenses-indigo-light-1440.png) | [`expenses-indigo-dark-1440.png`](../../ui/artifacts/v2.1/expenses-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Page-specific chart/card density review |
| `/debts` | Financial-analysis workspace | `PageLayout`, filter bar, analytical cards/charts | Shared numeric hierarchy and warning semantics | [`debts-indigo-light-1440.png`](../../ui/artifacts/v2.1/debts-indigo-light-1440.png) | [`debts-indigo-dark-1440.png`](../../ui/artifacts/v2.1/debts-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Review legacy KPI card grouping |
| `/universe` | Financial-analysis workspace | `Sidebar`, `Header`, atmospheric canvas, `FloatingTimeRangeBar` | Shared shell/gutters applied to the 3D data view without changing its data behavior | [`universe-indigo-light-1440.png`](../../ui/artifacts/v2.1/universe-indigo-light-1440.png) | [`universe-indigo-dark-1440.png`](../../ui/artifacts/v2.1/universe-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | 3D scene needs a dedicated accessibility/contrast audit |
| `/goals` | Planning and decision workspace | `PageLayout`, `PageHeader`, `EmptyState`, filter bar, planning primitives | Current state/target/projection hierarchy and honest create-goal action | [`goals-indigo-light-1440.png`](../../ui/artifacts/v2.1/goals-indigo-light-1440.png) | [`goals-indigo-dark-1440.png`](../../ui/artifacts/v2.1/goals-indigo-dark-1440.png) | Indigo desktop + representative 390/768/1440 matrix captured | Review projection section depth after capture |
| `/recommendations` | Planning and decision workspace | `PageLayout`, `PageHeader`, `EmptyState`, recommendation cards | Clear recommendation context and no dead action in the empty state | [`recommendations-indigo-light-1440.png`](../../ui/artifacts/v2.1/recommendations-indigo-light-1440.png) | [`recommendations-indigo-dark-1440.png`](../../ui/artifacts/v2.1/recommendations-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Existing recommendation action semantics require product-owner review |
| `/activity` | Intelligence/editorial and decision history | `PageLayout`, filter bar, status/decision primitives | Shared editorial shell and readable activity states | [`activity-indigo-light-1440.png`](../../ui/artifacts/v2.1/activity-indigo-light-1440.png) | [`activity-indigo-dark-1440.png`](../../ui/artifacts/v2.1/activity-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Large legacy activity surface needs density audit |
| `/market-briefs` | Intelligence and editorial workspace | `PageLayout`, `Header`, archive/source/status primitives | Source, freshness, limitations, and archive hierarchy remain authoritative; pre-generation status is explicitly not checked and generation failures expose sanitized server reason copy | [`market-briefs-indigo-light-1440.png`](../../ui/artifacts/v2.1/market-briefs-indigo-light-1440.png) | [`market-briefs-indigo-dark-1440.png`](../../ui/artifacts/v2.1/market-briefs-indigo-dark-1440.png) | Indigo desktop + representative 390/768/1440 matrix captured | Archive-specific empty state should consume `EmptyState` in a follow-up |
| `/accounts` | Configuration workspace | `PageLayout`, filter bar, `EmptyState`, form/button primitives | Honest connect/import empty state and shared configuration shell | [`accounts-indigo-light-1440.png`](../../ui/artifacts/v2.1/accounts-indigo-light-1440.png) | [`accounts-indigo-dark-1440.png`](../../ui/artifacts/v2.1/accounts-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Form sections still contain legacy card wrappers |
| `/settings` | Configuration workspace | `PageLayout`, `PageHeader`, Appearance controls, form primitives | Preserves Light/Dark/System, three profiles, persistence, and accessible controls | [`settings-indigo-light-1440.png`](../../ui/artifacts/v2.1/settings-indigo-light-1440.png) | [`settings-indigo-dark-1440.png`](../../ui/artifacts/v2.1/settings-indigo-dark-1440.png) | Indigo desktop + representative 390/768/1440 matrix captured | Settings subsections need a later section-navigation refinement |
| `/help` | Configuration/support workspace | `PageLayout`, shell, disclosure/card primitives | Shared readable shell and FAQ hierarchy | [`help-indigo-light-1440.png`](../../ui/artifacts/v2.1/help-indigo-light-1440.png) | [`help-indigo-dark-1440.png`](../../ui/artifacts/v2.1/help-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | FAQ cards can be reduced to more direct canvas composition |
| `/assistant` | Command/intelligence workspace | `PageLayout`, shell, chat primitives | Shared Atlas command surface and readable Scout entry point | [`assistant-indigo-light-1440.png`](../../ui/artifacts/v2.1/assistant-indigo-light-1440.png) | [`assistant-indigo-dark-1440.png`](../../ui/artifacts/v2.1/assistant-indigo-dark-1440.png) | Indigo desktop captured; representative archetype responsive matrix governs shared behavior | Chat-specific empty/loading states need shared-state migration |

## Screenshot matrix

Representative archetypes require all six mode/profile combinations at 390px,
768px, and 1440px: Overview, Budgeting, Portfolio, Goals, Market Briefs, and
Settings. Every route requires at least Indigo light and Indigo dark desktop
captures. Captures must be made against real route data/states; no mock financial
values may be introduced for visual evidence.

## Verified Market Brief behavior

The Market Brief route now uses a server-authoritative status progression:

- Before a brief or generation attempt: `Provider not checked`, with guidance to generate a brief to verify coverage and market-data availability.
- During generation: `Checking market data`, with duplicate submission disabled.
- After a returned brief: `Provider ready` or `Coverage limited` follows the embedded provider readiness.
- After a sanitized generation failure: `Provider unavailable` is paired with the mapped actionable reason and recovery copy; unsupported or blank imported symbols are reported as unsupported holdings rather than generic readiness failures, and raw provider responses and credentials are never rendered.
- Generation remains a bounded authenticated control request and archive replay remains immutable.

The local Rules Service startup path was cold-restarted during verification. The configured market-brief gates were enabled, server-side provider credentials were present without disclosure, and archive reads returned successfully. Non-market holding labels are fail-closed as unsupported omissions before provider access so they cannot break generation serialization.

## Completion record

This file is the route inventory and evidence contract for the active v2.1
branch. The linked Indigo desktop captures are the curated repository evidence;
the six-profile responsive matrix is retained only as local/CI evidence. The
route inventory must not be used to claim completion while any required
responsive or screenshot evidence remains unverified.

# Atlas Information Architecture and UI Migration Plan

Status: Steps 1–5 implemented. This document is the repository copy of the
approved design proposal and the route-ownership record for the consolidated
Atlas information architecture. System destinations are now active; legacy
bookmarks remain covered by compatibility redirects.

Step 5 evidence is recorded in the project tracker and current handoff. The
System destination ownership is: Data Connections owns accounts and imports;
Settings owns appearance, profile, and safe preferences; Help owns navigation,
data-limitations, evidence interpretation, privacy, and recovery guidance.

## Step 1 contract record

The proposed navigation is represented by `ui/lib/informationArchitecture.ts`.
It remains intentionally disconnected from the production sidebar until Step 2.
`PageTabs`, `AnalyticalContextBar`, and `AnalyticalPageFrame` are reusable
contracts rather than page migrations. They preserve the current URL-synced
range behavior through `FloatingTimeRangeBar`; a page can omit range controls
when they do not affect its authoritative query.

| Existing component or route | Future authoritative destination | Step 1 status |
| --- | --- | --- |
| `SankeyHero`, money-flow detail | Cash Flow / Overview | Retained in place |
| `TrendChart`, `BreakdownPanel`, category detail | Cash Flow / Income or Spending | Retained in place |
| `RecentActivity`, `/activity` | Cash Flow / Transactions | Retained in place |
| `RecurringTransactions` | Plan / Commitments | Retained in place |
| `FinancialPlans`, legacy simulation components | Scenario Lab | Slice 2 uses server-backed presentation; local calculators quarantined |
| `/debts`, `/universe` | Wealth tabs | Retained in place |
| `/assistant` | Global header Scout with accessible fallback | Retained in place |

The activation order is fixed: Step 2 activates Money destinations and its
compatibility redirects atomically; later steps activate Wealth, Intelligence,
and System destinations only when their corresponding pages are ready. No
redirect may activate before its target route exists.

## Product objective

Turn Atlas into one coherent financial operating system. Each financial question has one authoritative destination. Other pages may show a compact summary and link to that destination, but they must not repeat the complete visualization or workflow.

## Final primary navigation

```text
Home
└── Mission Control

Money
├── Cash Flow
│   ├── Overview
│   ├── Income
│   ├── Spending
│   └── Transactions
└── Plan
    ├── Budget
    ├── Commitments
    └── Calendar

Wealth
├── Wealth
│   ├── Overview
│   ├── Assets
│   ├── Debts
│   └── Universe view
├── Portfolio
│   ├── Holdings
│   ├── Allocation
│   ├── Performance
│   └── Risk
└── Goals
    ├── Goals
    ├── Forecasts
    └── Progress

Intelligence
├── Decisions
│   ├── Recommendations
│   ├── Decision journal
│   └── Outcomes
├── Market Intelligence
│   ├── My Portfolio
│   ├── Market Pulse
│   ├── Earnings & Events
│   ├── S&P 500 Scanner
│   └── Archive
└── Scenario Lab
    ├── Scenarios
    ├── Comparisons
    ├── Life events
    └── Financial Twin

System
├── Data Connections
│   ├── Accounts
│   ├── Imports
│   ├── Synchronization
│   └── Data quality
├── Settings
└── Help

Global header
├── Search / command palette
├── Scout assistant
├── Notifications
└── Appearance / profile
```

## One-home ownership rules

| Capability | Authoritative home | Allowed elsewhere |
|---|---|---|
| Cross-domain priorities | Mission Control | Count/badge only |
| Money-flow Sankey | Cash Flow / Overview | Small cash-flow figure only |
| Income analytics | Cash Flow / Income | Total and change only |
| Spending analytics | Cash Flow / Spending | Total and change only |
| Transaction review | Cash Flow / Transactions | Recent 3-5 rows only |
| Budgets and safe-to-spend | Plan / Budget | Status and deep link only |
| Upcoming bills and commitments | Plan / Commitments | Next 1-3 events only |
| Net worth and balance sheet | Wealth / Overview | Net-worth figure only |
| Debt payoff | Wealth / Debts | Debt total and risk only |
| Financial Universe | Wealth / Universe view | No duplicate 3D view |
| Holding analytics | Portfolio | Allocation/risk digest only |
| Goal forecasts | Goals | Goal status digest only |
| Recommendations and outcomes | Decisions | Priority badge/deep link only |
| Portfolio news and market evidence | Market Intelligence | Top catalyst digest only |
| What-if modeling | Scenario Lab | Scenario result summary only |
| Accounts and imports | Data Connections | Coverage/freshness only |
| Conversational assistance | Global Scout | Full-page fallback route only |

## Existing route and feature mapping

### Current `/` Overview

Destination: `Mission Control` plus specialist destinations.

Retain in Mission Control:

- concise greeting and data coverage;
- goal trajectory and forecast health;
- top recommendations / approval queue;
- one Market Intelligence catalyst digest;
- one cash-flow summary;
- one portfolio-risk summary;
- urgent alerts and next actions.

Move out:

- `SankeyHero` -> Cash Flow / Overview;
- `TrendChart`, `BreakdownPanel`, `FinancialHealthGauges`, `SpendByCategoryBar` -> Cash Flow tabs;
- `RecurringTransactions` -> Plan / Commitments;
- `RecentActivity` and review queue details -> Cash Flow / Transactions;
- `FinancialPlans` remains bounded goal planning; Scenario Lab owns server-backed what-if analysis. `WealthTimeline`, `MoneyFlowSimulator`, `LifeEventSimulator`, and `FinancialTwin` remain retained for compatibility tests but are no longer rendered from Mission Control and are not Scenario Lab authority;
- net-worth and balance-sheet detail -> Wealth;
- goal-specific forecast detail -> Goals;
- detailed category movers/anomalies -> Spending or Decisions depending on actionability.

Retire after migration:

- duplicate bento summaries that do not answer a unique question;
- decorative tilt wrappers around analytical modules;
- repeated KPI walls already represented in the position strip.

### Current `/income`

Destination: Cash Flow / Income.

Preserve and enhance:

- income breakdown and drill-down;
- monthly trend;
- source categories;
- transaction evidence.

Add:

- recurring/variable/one-time classification;
- source concentration;
- expected-payment calendar;
- missing/late income detection;
- income resilience and data coverage.

Compatibility: `/income` redirects to `/cash-flow?view=income`, preserving query parameters where possible.

### Current `/expenses`

Destination: Cash Flow / Spending.

Preserve and enhance:

- expense breakdown and drill-down;
- category and group analysis;
- merchant table;
- anomaly insights;
- monthly trend.

Add:

- merchant drift;
- subscription price changes and duplicates;
- refunds/credits separation;
- recurring and upcoming charges;
- spending-quality evidence.

Compatibility: `/expenses` redirects to `/cash-flow?view=spending`.

### Current `/activity`

Destination: Cash Flow / Transactions.

Preserve:

- server-side account, type, category, status, date and search filters;
- sorting and pagination;
- categorization tools;
- duplicate resolution;
- transaction evidence and editing.

Compatibility: `/activity` redirects to `/cash-flow?view=transactions`.

### Current `/budgeting`

Destination: Plan / Budget.

Preserve:

- create/edit budget flows;
- budget status;
- category groups;
- budget evidence and errors.

Enhance with:

- budget runway;
- projected month-end;
- safe-to-spend corridor;
- pace alerts;
- review-only reallocation suggestions.

Compatibility: `/budgeting` redirects to `/plan?view=budget`.

### Current `/portfolio`

Destination: Portfolio.

Preserve all authoritative holdings, classification, allocation, performance, analyst coverage and Market Intelligence links. Remove net-worth, goal, debt or market-news modules that have a different authoritative home.

### Current `/goals`

Destination: Goals.

Preserve goal CRUD, forecasts, projection status and goal-linked decision summaries. The full decision journal moves to Decisions; Goals displays only goal-scoped recent decisions with a deep link.

### Current `/debts`

Destination: Wealth / Debts.

Preserve debt table, payoff projection, payoff comparison and debt allocation. Compatibility: `/debts` redirects to `/wealth?view=debts`.

### Current `/universe`

Destination: Wealth / Universe view.

Preserve the interactive 3D experience as an optional visual mode, not a separate primary destination. Compatibility: `/universe` redirects to `/wealth?view=universe`.

### Current `/recommendations`

Destination: Decisions / Recommendations.

Preserve recommendation cards and approval semantics. Combine with the append-only decision journal and outcome evaluations. Compatibility: `/recommendations` redirects to `/decisions?view=recommendations`.

### Current `/market-briefs`

Destination: Market Intelligence.

Preserve all Phase 5 evidence, archive, provider-readiness, generation, coverage and privacy boundaries. Evolve into the portfolio-first Market Intelligence workspace. Compatibility: `/market-briefs` redirects to `/market-intelligence`.

### Current simulation components and Phase 6 Scenario APIs

Destination: Scenario Lab.

Preserve Phase 6 Slice 1 scenario identity, immutable history, comparison, ownership and Decimal-safe calculations. Slice 2 uses dedicated server-result presentation components under `ui/components/scenario-lab/`. The legacy `MoneyFlowSimulator`, `LifeEventSimulator`, `WealthTimeline`, and `FinancialTwin` remain quarantined for compatibility coverage only: they are not rendered from Mission Control, do not receive Scenario Lab data, and do not provide financial authority.

### Current `/assistant`

Destination: global Scout in the header.

The full route remains as an accessible fallback/deep link, but Scout no longer consumes a primary sidebar slot.

### Current `/accounts`

Destination: Data Connections / Accounts and Imports.

Preserve account management, statement imports, synchronization, data freshness and errors. Compatibility: `/accounts` redirects to `/data-connections?view=accounts`.

### Settings and Help

Remain primary System destinations. Settings preserves the independent Light/Dark/System selection and Indigo/Vermilion/Ion profiles.

## Shared application anatomy

Every analytical workspace uses:

1. Global header with search, Scout, notifications and profile.
2. Page header with one clear purpose and at most two actions.
3. Page tabs for sibling views.
4. Shared context bar with only controls that affect that workspace.
5. One narrative position strip.
6. One dominant analytical visualization.
7. One ranked attention rail.
8. At most three supporting modules above the fold.
9. A consistent drill-down drawer for evidence and detailed records.
10. Explicit loading, empty, partial, stale and error states.

Shared context-bar contract:

- time range: 7D, 30D, 90D, MTD, QTD, YTD, 1Y, All;
- compare control;
- account scope;
- one workspace-specific filter;
- coverage and freshness;
- URL-synchronized state;
- no time selector on pages where time does not change the authoritative query.

## Visual and interaction rules

- Preserve Indigo, Vermilion and Ion profiles.
- Profiles control selection, focus and primary chart emphasis only.
- Emerald, rose, amber and red remain stable financial semantics.
- Dark mode uses warm graphite/ink, never pure black.
- Light mode uses pearl/silver layers, never pure white.
- Use tabular figures for money, rates and dates.
- One primary motion story per screen.
- Range changes morph existing charts instead of replaying the entire page.
- Drill-downs use one shared drawer and preserve filter context.
- Motion uses transform/opacity and honors reduced motion.
- Mobile turns the shared context bar into a filter sheet and moves the attention rail below the primary visualization.

## Clutter budget

Each analytical view may have:

- one position strip;
- one primary visualization;
- one attention rail;
- at most three supporting modules above the fold;
- one detailed table/ledger below the fold;
- zero duplicate full-size charts from another authoritative destination.

Mission Control may show no more than six priority modules and no complete specialist workflow.

## Delivery plan

### Step 1 - Information architecture contract and shared shell

Risk: medium. No financial behavior changes.

Deliver:

- an implementation-grade route/ownership specification in `docs/06-ui-ux`;
- a typed consolidated navigation model and global Scout placement contract;
- page-tab primitive;
- unified URL-synced context-bar contract;
- shared analytical page frame and drill-down drawer contract;
- compatibility redirect table;
- component-level tests for the navigation model, tabs, context bar, keyboard behavior and mobile collapse.

Do not activate the consolidated sidebar, add redirects, or move financial components in this step. The objective is to create reviewed foundations without making live navigation point to incomplete destinations. Activation happens atomically with the Money migration in Step 2.

### Step 2 - Money migration

Risk: high because route/query behavior and financial presentation move.

Deliver:

- Cash Flow / Overview from the revised reference;
- Income, Spending and Transactions tabs using existing production behavior;
- Plan with Budget, Commitments and Calendar tabs;
- activation of the consolidated sidebar and global Scout placement;
- removal of duplicate Money modules from Mission Control;
- compatibility redirects for `/income`, `/expenses`, `/activity` and `/budgeting`;
- complete financial-parity, accessibility, responsive and E2E coverage.

### Step 3 - Wealth migration

Deliver:

- Wealth Overview, Assets, Debts and Universe view;
- Portfolio Holdings, Allocation, Performance and Risk;
- Goals, Forecasts and Progress;
- removal of duplicated net-worth, debt and goal charts from other pages;
- compatibility redirects for `/debts` and `/universe`.

### Step 4 - Intelligence migration

Deliver:

- Decisions with recommendations, journal and outcomes;
- Market Intelligence v2;
- Scenario Lab using Phase 6 authoritative APIs;
- global Scout integration;
- redirects for `/recommendations`, `/market-briefs` and `/assistant`.

### Step 5 - System migration and final cleanup — implemented

Delivered:

- Data Connections at `/data-connections` with Accounts, Imports,
  Synchronization readiness, and Data quality views;
- compatibility redirect for `/accounts` that preserves query state and adds
  `view=accounts`;
- Settings remains the authoritative home for appearance, accent profiles,
  profile preferences, maintenance, and the existing safe configuration
  surfaces;
- Help now explains the final Home, Money, Wealth, Intelligence, and System
  structure, evidence limitations, privacy boundaries, default-off behavior,
  and recovery guidance;
- command-palette and specialist deep links now target Data Connections;
- the obsolete Tools sidebar group and duplicate Accounts/Activity primary
  entries were removed; Activity remains reachable from Cash Flow / Transactions;
- focused responsive, keyboard, appearance, and compatibility certification
  was recorded without changing financial or backend authority.

## Acceptance rules for every migration wave

- Existing authoritative calculations, authorization and persistence do not change silently.
- Existing completed-phase features remain reachable in their new home.
- Old routes redirect without losing meaningful query state.
- No page displays a complete duplicate of another page's authoritative visualization.
- All financial totals match the pre-migration route for identical filters.
- Light/dark and all three accent profiles pass visual and contrast checks.
- Keyboard, reduced-motion, loading, empty, partial, stale and error states are covered.
- No personal data, credentials or local database artifacts enter test fixtures or screenshots.

## Final route ownership record

| Destination | Authoritative route | Compatibility and deep links |
|---|---|---|
| Mission Control | `/` | Cross-domain summaries only |
| Cash Flow | `/cash-flow` | `/income`, `/expenses`, and `/activity` redirect to URL-synced views |
| Plan | `/plan` | `/budgeting` redirects to the Budget view |
| Wealth | `/wealth` | `/debts` and `/universe` redirect to specialist views |
| Portfolio | `/portfolio` | Full holdings and portfolio analytics live here |
| Goals | `/goals` | Goal-scoped summaries only elsewhere |
| Decisions | `/decisions` | `/recommendations` redirects to Recommendations |
| Market Intelligence | `/market-intelligence` | `/market-briefs` redirects here |
| Scenario Lab | `/scenario-lab` | Server-backed scenario authority remains unchanged |
| Data Connections | `/data-connections` | `/accounts` redirects to `view=accounts`; imports are `view=imports` |
| Settings | `/settings` | Safe profile and appearance preferences |
| Help | `/help` | Product navigation, evidence, privacy, and recovery guidance |
| Scout | Global header + `/assistant` | Full-page fallback remains accessible |

The final cleanup preserves legacy routes as compatibility surfaces, keeps one
full visualization or analytical workflow per authoritative destination, and
removes obsolete primary-navigation entries only after their replacement route
is active.

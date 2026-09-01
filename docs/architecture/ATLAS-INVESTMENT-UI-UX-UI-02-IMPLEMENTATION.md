# Atlas Investment UI/UX — UI-02 Implementation

**Status:** Implemented
**Scope:** Investment navigation and route contract

## Purpose

UI-02 establishes the Atlas-native investment entry point at `/investments`. It is a read-only navigation surface for the investment intelligence pipeline and does not duplicate backend calculations or create investment actions.

The repository roadmap assigns the Daily Investment Brief to UI-03. Therefore this phase intentionally establishes the route and progressive-disclosure pattern rather than prematurely implementing the full brief dashboard.

## Route and surfaces

- `/investments` — Investment Command Center entry point.
- `/investments/brief` — reserved navigation contract for the planned Daily Investment Brief; no fabricated content is rendered by UI-02.
- `/portfolio` — existing canonical portfolio surface.
- `/market-intelligence` — existing canonical market intelligence surface.

The primary sidebar now exposes **Investments** under Intelligence. Existing routes remain unchanged.

## Information architecture

The command center provides:

1. A clear investment-intelligence header.
2. A human-controlled analysis notice.
3. Search affordance with `/` keyboard focus behavior.
4. Explicitly labelled available and planned investment surfaces.
5. Trust and safety boundary messaging.

The layout uses existing `PageLayout`, `PageHeader`, Sidebar, Atlas tokens, Lucide icons, and Tailwind conventions. No new design system or dependency was introduced.

## Data and API boundary

UI-02 does not fetch or calculate investment data. It does not create a new API, view model, provider call, persistence layer, portfolio ledger, recommendation lifecycle, or decision workflow. Future UI phases will consume Atlas-owned read models only.

## Interaction and accessibility

- Native links provide keyboard and screen-reader navigation.
- Search has a visible label for assistive technology.
- `/` focuses the search field unless the user is already typing in a form control.
- Status labels distinguish available from planned surfaces.
- Safety semantics are communicated in text and are not color-only.
- Existing focus styles and responsive shell behavior are reused.

## Responsive behavior

The surface cards use responsive grid breakpoints and remain usable on laptop, tablet, and mobile widths. Existing Atlas shell/sidebar behavior is preserved. The route contains no dense data table yet; that belongs to the data-backed brief/research phases once their read models are integrated.

## Validation

Focused UI-02 tests cover route rendering, canonical links, absence of execution actions, and keyboard search behavior. Existing sidebar compatibility coverage verifies the new navigation link while retaining prior destinations.

## Boundaries and non-goals

UI-02 does not implement:

- the complete Daily Investment Brief (UI-03)
- production recommendation tables or decision controls
- complete security research workspace
- portfolio intelligence redesign
- evidence drawer implementation
- outcome analytics workspace
- broker, order, trade, execution, rebalance, or money movement functionality
- automatic trading or portfolio mutation
- INV-12 backtesting or performance analytics

No INV-03 through INV-11 backend contract was modified. UI-03+ should add data-backed sections only after the corresponding Atlas-owned read models and authorization contracts are stable.

## Rollback

Remove the `/investments` route and its single sidebar item. Existing Portfolio, Market Intelligence, Decisions, and other Atlas routes remain independently usable.

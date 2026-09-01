# Atlas Investment UI/UX - UI-03 Implementation

**Status:** Implemented
**Route:** `/investments/brief`

## Scope

UI-03 turns the UI-02 route contract into a Daily Investment Brief experience. It is a structured, read-only Atlas workstation for reviewing server-owned market intelligence, portfolio coverage, warnings, and analytical review actions.

The page does not calculate investment intelligence in React and does not invent unavailable data.

## Component architecture

The route is composed of:

- Brief header with report as-of, generation timestamp, and quality/readiness state.
- Structured section renderer for server-authored brief content.
- Coverage and freshness panel.
- Portfolio context link to the existing canonical Portfolio route.
- Human review queue with action filtering and progressive detail disclosure.
- Evidence detail dialog with provider, freshness, retrieval, publication, and source link context.
- Loading skeleton and honest unavailable/error state.

Existing `PageLayout`, `PageHeader`, Atlas tokens, Tailwind, and Lucide primitives are reused.

## Data and integration

The frontend consumes the existing owner-scoped Market Brief contract in `ui/lib/marketBriefs.ts` through `generateMarketBrief()`. This provides structured sections, warnings, as-of/generation metadata, provider readiness, coverage, portfolio daily change, and action-to-review data.

No new backend API, provider, persistence, migration, or dependency was introduced. The existing server remains responsible for canonical INV-01 through INV-11 data, authorization, calculations, evidence, and temporal filtering.

The brief preserves the available fields rather than creating a shadow CIO report model. Future API work can expose the full INV-10 CIO report envelope when that read model is available.

## UX behavior

- The page prioritizes structured sections and warnings before review actions.
- Source references open in an evidence detail dialog rather than cluttering the primary view.
- Review actions remain analytical and are never presented as execution controls.
- Action filtering is client-side presentation filtering only; it does not reinterpret action semantics.
- Empty sections and unavailable provider data remain explicitly visible.
- The `/investments` command center remains the navigation parent.

## Freshness and point-in-time semantics

Canonical `as_of`, `generated_at`, retrieval, publication, and freshness fields are displayed when provided. The browser does not replace them with request time and does not perform independent timestamp filtering. The server-owned brief remains authoritative for point-in-time behavior.

## Responsive and accessibility behavior

The layout uses a desktop-first two-column analytical composition that collapses to a single reading column on smaller screens. Dense review rows remain horizontally structured without requiring inaccessible card transformations. Native headings, links, buttons, labels, dialog semantics, focus-visible styles, keyboard navigation, and text labels provide non-color communication.

## Testing

Focused UI-03 tests cover:

- loading state
- structured section rendering
- as-of and readiness context
- warnings and partial coverage
- evidence disclosure
- review-action filtering
- unavailable/error state
- absence of execution controls

Existing frontend regression tests and sidebar compatibility tests remain part of the validation set.

## Performance

The page makes one server-owned brief generation request, avoids frontend financial calculations, keeps evidence details progressive, and renders no chart unless a canonical chart payload is later supplied. The existing Next.js and Atlas bundle are reused.

## Security and human boundary

The route does not expose credentials, provider internals, or unrelated account data. It contains no broker, order, trade, execution, transfer, money movement, portfolio mutation, or automatic rebalancing capability. Review actions are informational context only and do not create user decisions or execute recommendations.

## Limitations and future boundaries

UI-03 does not implement:

- complete portfolio intelligence workspace (UI-04)
- security research workspace (UI-05)
- visualization adapter (UI-06)
- dedicated evidence/provenance workspace (UI-07)
- recommendation review and decision workflow (UI-08)
- full outcome analytics
- scheduler or notification infrastructure
- new market-data providers
- INV-12 backtesting or performance analysis

The current frontend API exposes the existing Market Brief contract rather than the full INV-10 CIO report envelope. The page therefore renders only fields available from that approved contract and remains explicit about unavailable sections.

## Rollback

Remove the `/investments/brief` route and retain the UI-02 command center link as a planned surface, or disable that link until the route is re-enabled. Existing portfolio, market intelligence, decisions, and market brief routes remain unaffected.

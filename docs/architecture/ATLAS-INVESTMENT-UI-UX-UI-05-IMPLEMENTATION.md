# Atlas Investment UI/UX - UI-05 Implementation

**Status:** Implemented
**Route:** `/investments/security/[securityId]`

## Scope

UI-05 adds a deep-linkable, read-only security research workspace. It establishes the security-level navigation and trust surface without duplicating investment calculations or presenting unsupported data as fact.

UI-04 remains the portfolio-level intelligence workspace. UI-05 does not implement UI-06 financial chart adapters, UI-07 full evidence/provenance tooling, UI-08 recommendation review, or any later research workspace.

## Data sources

The route uses the existing `rulesService` client and current Atlas contracts:

- `Holding[]` for owner-scoped portfolio context, price, quantity, value, type, and position quality.
- `Account[]` for account-safe display labels and synchronization context.
- `getAnalystRatings()` for the existing server-mediated analyst-rating projection.

The browser does not call financial-data providers directly. It does not calculate indicators, returns, valuation, portfolio weights, benchmark metrics, or recommendation semantics.

## Research surfaces

The page provides:

- Canonical security reference and ticker context.
- Most recent server-owned holding price when available.
- Portfolio ownership, value, weight, quantity, account context, and data quality.
- Analyst period, buy/hold/sell consensus, and price target when the existing projection is available.
- Explicit unavailable states for INV-04 fundamentals, INV-05 technicals, INV-07 quant, INV-06 macro, and INV-08 committee data because those projections are not currently exposed through the frontend API.
- Links to Portfolio Intelligence, Daily Brief, and Market Intelligence.

Unavailable sections are intentionally visible rather than populated with fabricated values.

## Temporal and provenance behavior

Account synchronization metadata is shown when available. The page does not substitute browser time for a server timestamp and does not claim live pricing. The current frontend contracts do not expose security observation `as_of`, adjustment basis, source hashes, fundamental filing metadata, or calculation versions; those details remain a documented dependency for the future read-model/evidence phases.

## Responsive and accessibility behavior

The page uses the existing Atlas shell and tokens, compact KPI panels, semantic tables, labeled timestamps, text-based quality states, visible focus styles, and 44px interactive targets. Portfolio positions remain horizontally scrollable on narrow screens instead of being silently truncated. Loading, error, unheld, and unavailable states are explicit.

## Navigation

Security routes are direct deep links under `/investments/security/[securityId]`. Existing Portfolio, Daily Brief, Market Intelligence, and holdings-management routes remain unchanged. The future research workspace can replace the unavailable lens placeholders once stable read models are authorized.

## Validation

Focused UI-05 tests cover identity, held and unheld context, analyst data, partial research, backend errors, and the no-execution boundary. UI-02, UI-03, and UI-04 tests are run as frontend regressions together with TypeScript, ESLint, production build, and `git diff --check`.

## Dependencies

No dependencies were added. Existing Next.js, React, Tailwind, Lucide, Atlas layout primitives, and API client are reused.

## Security and human boundary

No broker, order, execution, trade, transfer, money movement, rebalance, or portfolio mutation capability was added. Research and analyst information are read-only. No action button implies that an analytical signal is an instruction to transact.

## Limitations and UI-06 handoff

The current API does not provide a dedicated public security projection or serialized INV-02 through INV-08 research envelope. Consequently, the page does not invent fundamentals, technicals, quant, macro, committee, evidence, or recommendation data. UI-06 should consume a stable normalized chart payload rather than adding browser-side calculations. UI-07 and UI-08 can later add provenance and review controls against their own authorized contracts.

## Rollback

Remove or feature-gate the dynamic security route. Existing Portfolio and Market Intelligence routes remain intact.

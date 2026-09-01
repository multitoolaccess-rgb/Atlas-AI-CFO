# Atlas Investment UI/UX - UI-07 Implementation

**Status:** Implemented
**Scope:** Evidence and provenance experience

## Roadmap interpretation

The authoritative roadmap defines UI-07 as the evidence and provenance experience. It does not define a new investment route or authorize recommendation review. UI-08 remains responsible for recommendation review and human decision capture.

## Component

`ui/components/investments/EvidenceDrawer.tsx` provides a reusable progressive-disclosure drawer for bounded server-owned evidence records. It supports:

- Human-readable claim labels and values.
- Evidence category and state.
- Period and as-of context.
- As-known-at and retrieval timestamps.
- Source/provider and freshness.
- Sanitized server-supplied source links.
- Methodology and calculation version.
- Evidence ID and source-reference details.
- Honest empty, unavailable, missing, stale, estimated, derived, and insufficient-history states.

## Data architecture

The drawer accepts typed evidence records from an owning read model. It does not fetch providers, calculate metrics, filter timestamps, rewrite facts, or infer missing provenance. Existing `MarketBrief` citation semantics remain compatible, while future INV-01 evidence packets can map directly to this view model.

No API, backend contract, persistence layer, migration, or dependency was added.

## Interaction and accessibility

The drawer is keyboard dismissible with Escape, focuses its close control on open, exposes modal semantics, uses semantic headings and definition lists, and keeps technical provenance behind a native disclosure element. Source links open in a separate tab with `noreferrer`. The panel is full width on mobile and constrained on desktop, with scrollable content and 44px controls.

## Visual and information design

The primary view stays compact and readable. Technical hashes, identifiers, methodology, and calculation metadata are disclosed only when requested. State is communicated with text, not color alone. The pattern is designed for evidence-backed claims in briefs, security research, portfolio analysis, and future decision review surfaces.

## Testing and validation

Focused tests cover evidence rendering, values, period/as-of metadata, source links, technical provenance, unavailable states, empty states, Escape dismissal, closed state, and the no-execution boundary. UI-02 through UI-06 regressions, TypeScript, ESLint, production build, and `git diff --check` are required validation gates.

## Security and human boundary

The component is read-only. It introduces no broker integration, order creation, execution, trading, transfer, money movement, portfolio mutation, or automatic rebalancing. It does not create recommendations or record decisions.

## Limitations and future handoff

A current dedicated evidence-packet API is not exposed in the frontend. Owners must map their canonical evidence to `EvidenceRecord` until UI-07's backend dependency is available. UI-08 may compose this drawer for recommendation review; UI-07 does not add those controls.

## Rollback

Stop rendering the drawer and use existing inline citation patterns. No backend or persistence rollback is required.

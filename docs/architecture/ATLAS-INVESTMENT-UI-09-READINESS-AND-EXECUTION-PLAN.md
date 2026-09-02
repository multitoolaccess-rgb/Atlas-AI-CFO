# UI-09 Opportunity Discovery & Comparison
## Readiness and Execution Plan

**Status:** Backend foundation in progress — approved current-only portfolio and bounded S&P 500 universe modes; UI remains pending
**Scope:** UI-09 only; no UI-08, INV-01–INV-11 redesign, UI-10–UI-12, INV-12, or execution capability
**Authority:** UI/UX roadmap, INV-01–INV-HARDEN-01 contracts, ADR-007, and the repository architecture audit

## Executive decision

UI-09 is not ready for a production discovery experience yet. The repository has useful server-owned research and market-intelligence inputs, but it does not have a complete durable security master or an approved discovery/screening methodology.

The approved first slice uses two explicitly separated, current-only server-owned modes: owner portfolio holdings and the bounded factual S&P 500 symbol list. The implementation must remain fail-closed for missing metrics and must not silently merge the modes or create recommendations.

## Current findings

### Existing usable inputs

- Portfolio `Account` and `Holding` rows are owner-scoped but mutable, Float-based, symbol-based, and current-state only.
- Market Intelligence has strict normalized market, company, analyst, SEC, earnings, freshness, source, and failure contracts.
- Market Pulse has a bundled factual S&P 500 symbol list and a bounded scanner, but it is a Market Brief/pulse input rather than a discovery read model.
- `SecurityIdentity` contracts exist in the investment modules, but no complete durable Security/Instrument master exists.
- Recommendation, committee, decision, outcome, scenario, and Market Brief persistence are downstream or presentation-specific and must not become the discovery universe.

### Missing authority

The repository does not currently define all of the following for UI-09:

- whether the universe is portfolio-only, bounded S&P 500, or an explicitly labeled combination;
- effective-dated universe membership;
- candidate eligibility;
- discovery score or ranking methodology;
- watch-state ownership and persistence;
- candidate-level source/observation identity;
- historical discovery reconstruction guarantees;
- comparison metric compatibility rules;
- a complete durable security identity crosswalk.

## Architectural decision

UI-09 should be implemented as a **read-only deterministic discovery projection**, not a new recommendation aggregate.

The safe initial shape is:

```text
Approved bounded universe input
    ↓
Canonical SecurityIdentity normalization
    ↓
Validated research/quote evidence adapter
    ↓
Deterministic discovery candidate projection
    ↓
Typed authenticated owner-scoped API
    ↓
Descriptive comparison projection
    ↓
UI-09 discovery/detail/comparison surfaces
```

No LLM is used for candidate generation, ranking, or financial calculation. No discovery candidate is a recommendation.

## Required prerequisite: discovery input contract

Before UI or production API implementation, approve and implement a single bounded input contract with these fields:

### Universe

- `universe_id` and `universe_version`;
- explicit membership source and source hash;
- scope: global/public versus owner-specific;
- bounded maximum size and pagination policy;
- current-only versus historical semantics.

### Security identity

- canonical `security_id`;
- instrument type;
- normalized symbol as a display/provider alias only;
- identity state and lifecycle;
- provider identifiers and effective dates where available;
- identity provenance.

### Candidate eligibility

- explicit source reason;
- allowed status values;
- no implicit recommendation promotion;
- deterministic duplicate handling;
- no invented score unless a methodology is approved.

### Evidence and provenance

- source/reference identity;
- observation/snapshot identity;
- source hash where available;
- `as_of`;
- `as_known_at` where supported;
- retrieval timestamp;
- freshness/data state;
- methodology/calculation version.

### Owner context

- public candidate data must not reveal private portfolio information;
- owner-specific exposure, watch state, preferences, and recommendation linkage must be separately scoped;
- cross-owner IDs must return bounded not-found behavior;
- no owner state should be introduced unless explicitly required by UI-09.

### Comparison compatibility

Each metric must declare:

- canonical meaning;
- unit and currency;
- observation period;
- adjustment basis;
- `as_of`/`as_known_at`;
- data state;
- calculation/methodology version;
- compatibility rule.

Incompatible metrics must be marked unavailable or non-comparable. They must never be silently converted.

## Methodology decision

No authoritative UI-09 discovery score or ranking formula was found.

Therefore the initial implementation must use:

> deterministic filtering and stable canonical-identity ordering only

Any future score requires a separately documented methodology, versioned inputs, missing-data policy, temporal policy, and golden fixtures.

## Approved source selection

The product decision is now recorded: **Option 3 — portfolio and bounded S&P 500 modes, explicitly separated; current-only semantics; deterministic filtering/stable ordering; no discovery score.**

## Source selection recommendation

Use the smallest bounded source that can be made authoritative:

1. **Portfolio mode:** owner portfolio holdings normalized into the bounded discovery identity projection.
2. **S&P 500 mode:** the existing factual S&P 500 list, wrapped with explicit current-only universe and provenance metadata.
3. **Do not combine them silently.** The API must identify the universe and scope.
4. Market Brief remains a reusable evidence/provider adapter, not the discovery authority.
5. Investment recommendations remain downstream and are only informational links.

If the product requires market-wide discovery beyond this bounded source, a security master and universe contract must be implemented first.

## Execution sequence

### Phase 1 — Contract decision

- Confirm portfolio-only versus bounded public scanner versus two explicitly labeled modes.
- Confirm current-only semantics for the first slice.
- Confirm no ranking score in the first slice.
- Record the decision in an ADR or approved roadmap amendment.

### Phase 2 — Server-owned source adapter

- Build an adapter from the approved source into canonical `SecurityIdentity`.
- Reject unresolved, ambiguous, unsupported, malformed, or duplicate identities.
- Preserve source/universe hash, timestamps, freshness, and omissions.
- Keep provider calls behind existing Market Intelligence controls.
- Do not add a second security system or financial ledger.

### Phase 3 — Discovery service

- Generate candidates only from validated adapter output.
- Apply bounded allowlisted filters.
- Order by stable canonical identity.
- Keep scores absent unless explicitly approved.
- Preserve optional recommendation linkage as downstream context only.
- Return unavailable/unknown states explicitly.

### Phase 4 — Comparison service

- Support only an allowlist of normalized metrics with defined semantics.
- Require compatible currency, units, periods, adjustment basis, methodology, and timestamps.
- Mark missing, stale, unsupported, and insufficient inputs explicitly.
- Never calculate authoritative values in React.

### Phase 5 — Typed API

Recommended endpoints:

- `GET /api/v1/investments/discovery`
- `GET /api/v1/investments/discovery/{candidate_id}`
- `POST /api/v1/investments/discovery/compare`

All endpoints must require authentication, use server-owned source data, enforce owner scope for private context, return typed Pydantic envelopes, and avoid ORM/raw provider payload leakage.

### Phase 6 — Tests before UI

Prove:

- unauthenticated access is rejected;
- owner-specific context cannot cross owners;
- public/global scope is not confused with private scope;
- deterministic candidate IDs and ordering;
- bounded filters and limits;
- stable pagination;
- source and universe provenance;
- future/unknown timestamps fail closed;
- missing states never become zero;
- incompatible comparison metrics are marked non-comparable;
- recommendations are not created or mutated;
- no execution vocabulary or capability is introduced.

### Phase 7 — UI-09 surfaces

Only after the API gates pass, build:

- discovery list with explicit universe/as-of/methodology;
- candidate detail with reason, source, freshness, and limitations;
- bounded comparison tray/table;
- loading, empty, unavailable, stale, error, and no-compatible-comparison states;
- mobile filter controls and accessible table semantics.

The UI must say or make clear that a candidate is not a recommendation.

### Phase 8 — Certification

Run backend contract/API tests, investment regressions, frontend tests/typecheck/build, accessibility/responsive checks, execution-boundary scan, `git diff --check`, and ownership review. Mark UI-09 complete only when all gates pass.

## Test matrix

| Area | Required proof |
|---|---|
| Authentication | list, detail, compare reject unauthenticated calls |
| Ownership | private context is visible only to its owner; cross-owner IDs are bounded not-found |
| Identity | canonical security identity remains stable; ticker aliases are not authority |
| Provenance | universe/source/observation IDs, hashes, timestamps, freshness, and methodology survive projection |
| Temporal | future evidence, invalid known-at, and mixed historical/current inputs fail closed |
| Filtering | allowlisted values/operators only; invalid fields and limits return typed 422 |
| Pagination | bounded page size, stable continuation, no overlap, deterministic omission metadata |
| Missing data | missing, stale, unsupported, unknown, and unavailable states remain distinct |
| Comparison | valid compatible metrics pass; currencies/periods/bases/methodologies that differ are non-comparable |
| Separation | discovery does not create recommendation, decision, outcome, or execution state |
| API typing | Pydantic response validation and no raw ORM/provider payload leakage |
| UI | loading, empty, stale, unavailable, error, accessible table/filter, and mobile states |

## Explicit non-goals

- No broker, trading, orders, transfers, money movement, or rebalancing.
- No LLM discovery or autonomous scout.
- No portfolio optimization.
- No new recommendation semantics.
- No speculative security-master/lot-ledger expansion unless required by the approved universe scope.
- No UI-10, UI-11, UI-12, or INV-12.

## Exit criteria

UI-09 may be marked **Backend Foundation Complete / UI Pending** only when the approved source adapter, contract, typed APIs, comparison compatibility rules, and backend/API test matrix pass.

UI-09 may be marked **Complete** only after the discovery, detail, and comparison UI passes its own functional, accessibility, responsive, privacy, provenance, and no-execution gates.

## Current status

**BACKEND FOUNDATION IN PROGRESS:** the universe decision is approved and the bounded source adapter is being implemented. UI-09 is not complete until typed HTTP/API tests and discovery/detail/comparison UI certification pass.

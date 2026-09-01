# Atlas Investment Intelligence — INV-09 Implementation

**Status:** Implemented as an in-memory, provider-neutral analytical projection.

## Objective and boundary

INV-09 transforms a validated INV-08 `CommitteeFinding` and frozen evidence
packet into an immutable, typed `InvestmentRecommendation`. The existing Atlas
recommendation ledger remains the persistence/lifecycle authority; this slice
does not add a second store, route, migration, scheduler, notification, or UI.

The output is a user-review proposal. It is not an order, broker instruction,
execution payload, or portfolio mutation.

## Taxonomy

- `BUY`: consider initiating a security exposure when not held.
- `ADD`: consider increasing an existing exposure. A requested `BUY` for an
  already-held security is normalized to `ADD`.
- `HOLD`: maintain the current exposure for the stated horizon.
- `REDUCE`: consider decreasing exposure without necessarily exiting.
- `SELL`: consider exiting exposure.
- `WATCH`: monitor without immediate portfolio action. A requested `SELL` or
  `REDUCE` for an unheld security is normalized to `WATCH`.

`recommendation_type` is separate from lifecycle `status`. Status is currently
`active`, `superseded`, `expired`, or `withdrawn`; long-term tracking remains
INV-11.

## Committee dependency and gates

Recommendations require a valid INV-08 committee finding, matching security,
validated packet, matching portfolio snapshot hash, and an analysis timestamp
not later than recommendation time. Evidence references must exist in the
packet; unknown/missing packet evidence is rejected. Stale evidence blocks
actionable recommendations. Unknown position state blocks position-changing
semantics. Low or unavailable conviction cannot become an actionable result.

No LLM call occurs in the recommendation gate. Committee model metadata is
carried as provenance only; the server computes conviction.

## Deterministic methodology

Version: `investment-recommendation/v1`.

Conviction is computed from bounded components:

- evidence coverage: referenced material evidence / packet evidence;
- committee support: constructive/neutral/cautious = 1, mixed = 0.5,
  insufficient evidence = 0;
- data quality: 1 for non-stale evidence, 0.5 for stale evidence.

The weighted score is `40% coverage + 35% committee support + 25% data
quality`, rounded to an integer. A blocker caps the score at 25. Scores and
bands are server-derived, reproducible, and never accepted from model output.
This is a bounded initial methodology, not a suitability or return forecast.

## Contract and provenance

`InvestmentRecommendation/v1` records the owner, security, action, committee
run/finding, portfolio snapshot hash, analysis/recommendation timestamps,
horizon, conviction components, thesis, rationale, supporting and contradicting
evidence, risks, invalidation conditions, portfolio impact, position context,
freshness/data quality, review time, expiry, model metadata, input hash, and
recommendation hash. Hashes exclude wall-clock creation time and include the
canonical analytical inputs.

Portfolio impact is analytical only. It may include an allocation range or
concentration/liquidity notes, but the contract has no quantity, execution
price, broker, order, or transfer fields.

## Freshness, time, and uncertainty

Evidence is required to be no later than the packet analysis boundary. Analysis
and recommendation timestamps are timezone-aware UTC. Review dates are
explicit and default to 7, 14, or 30 days for short-, medium-, and long-term
horizons. Stale evidence is disclosed and blocks actionable actions in this
slice. Missing, unknown, insufficient, and conflicting states remain explicit
rather than being converted to zero or current.

## Existing lifecycle and persistence

The domain contract is an additive projection over the existing append-only
`Recommendation` model and existing decision journal/outcome records. INV-09
does not persist speculative investment columns or automatically create a user
decision. A production persistence adapter must be added only after the typed
contract and ownership integration are separately reviewed. INV-11 owns
tracking, supersession history, review automation, and outcome linkage.

## Model/provider and prompt safety

The recommendation layer is deterministic and provider-independent. INV-08
model/provider metadata is retained without credentials or raw prompts. External
text remains inert evidence data. No provider is activated, no network call is
made, and no dependency is added.

## API and UI boundary

No API or production UI is changed in this bounded implementation. Future
read-only routes should reuse the existing recommendation lifecycle, enforce
owner scope before existence-sensitive reads, expose evidence/provenance and
uncertainty, and accept no client-authored financial facts. UI/UX-01 remains the
presentation authority; future UI must use `Consider`, `Review`, `Watch`, and
similar human-decision language rather than execution controls.

## Evaluation and testing

Focused tests cover valid/invalid contracts, taxonomy normalization, held vs
unheld semantics, stale/future/unknown portfolio gates, evidence provenance,
strict fields, deterministic hashing, and AST-level execution-import checks.
Existing INV-08 evaluation remains the committee entry gate. Long-term hit rate,
realized-return attribution, calibration, and backtesting are explicitly
excluded and belong to INV-11/INV-12.

## Non-goals and later boundaries

INV-09 does not implement automatic trading, broker integration, order creation,
execution, money movement, portfolio mutation, automatic rebalancing,
notifications, scheduling, recommendation performance tracking, CIO reports,
full tracking, outcome attribution, backtesting, or production UI. INV-10 owns
CIO reporting; INV-11 owns recommendation tracking and outcomes; INV-12 owns
historical evaluation/backtesting.

## Rollback

Because this slice is domain-level and in-memory, disable its caller or feature
flag without data migration. Existing generic recommendations, decisions, and
holdings remain untouched. Any future persisted investment projection must be
additive, immutable, owner-scoped, and independently rollback-reviewed.

## Known limitations

The initial methodology does not calculate suitability, tax, liquidity, target
allocation, or risk from raw portfolio data; callers must provide a validated
portfolio snapshot hash and bounded position context. Catalysts are not inferred
from external text. No HTTP ownership adapter or persistence handoff is part of
this phase.

# Atlas Investment Intelligence — INV-10 Implementation

**Status:** Implemented as a deterministic, provider-neutral CIO report projection.

## Objective and scope

INV-10 assembles validated INV-03 portfolio context, INV-04–07 research,
INV-08 committee findings, and INV-09 recommendations into an immutable,
typed `CIOReport`. It is a reporting projection, not a research engine,
recommendation engine, portfolio ledger, broker, scheduler, or execution system.

The implementation supports two bounded report types:

- `DAILY_BRIEF`: one calendar-day review window.
- `WEEKLY_REVIEW`: a seven-calendar-day window ending on the anchor date.

## Report contract and period semantics

`CIOReport/v1` records owner, report type, explicit UTC period start/end,
`as_of`, generation time, status, portfolio snapshot hash, committee summaries,
recommendation summaries, evidence, ordered sections, quality, methodology,
input hash, and report hash. `as_of` is distinct from generation time and
upstream observation/retrieval times. Naive timestamps, inverted periods, and
future-dated upstream findings/recommendations are rejected.

Identical canonical inputs produce identical report hashes. Report identity and
content exclude wall-clock entropy. The contract is immutable/frozen; a future
correction must be a new report rather than mutation.

## Structured assembly

The assembler creates sections for:

- executive summary;
- portfolio;
- market context;
- fundamental developments;
- technical and quantitative signals;
- macro context;
- committee conclusions;
- active recommendations;
- key conflicts;
- risks; and
- items requiring human review.

Sections contain structured items and evidence IDs. Recommendation action,
thesis, conviction band, risks, supporting evidence, contradicting evidence,
and review date are copied from INV-09 without reinterpretation. Committee
views and dissent are copied from INV-08. The report never invents a
recommendation or silently changes `ADD` to `BUY`.

## Evidence, uncertainty, and quality

Recommendation evidence is projected with source hash, category, as-of time,
and upstream state. Section references must resolve to report evidence. Mixed
committee evidence is surfaced in an explicit conflict section. Report quality
is `complete`, `partial`, or `conflicting` for this bounded slice; upstream
missing, unknown, stale, estimated, and insufficient states remain represented
rather than converted to zero/current/false.

## Ownership and privacy

The report requires an owner ID and rejects recommendations owned by another
owner or linked to a different portfolio snapshot hash. No raw provider payloads,
credentials, account identifiers, or unrelated personal data are accepted by
the report contract. Portfolio summaries are caller-supplied validated
projections from INV-03.

## Narrative and provider boundary

The canonical report is structured and exists independently of prose. No LLM
is called by INV-10, and no new provider or dependency is activated. A future
narrative adapter may consume this structured report, but must validate output
against the same evidence and must not author dates, metrics, actions, owners,
or evidence references. External text remains data, not instructions.

## Persistence, API, and scheduler boundaries

No new persistence, migration, API, route, scheduler, notification, delivery,
or UI change is included in this bounded implementation. Existing Market Brief
persistence remains available for its existing market-intelligence lifecycle;
this CIO projection does not overload or mutate that model. A future additive
persistence adapter must preserve owner scope, immutable history, idempotency,
input references, and report hashes. Future read-only APIs must accept no
client-authored financial facts.

The service is callable on demand for daily or weekly reports. Autonomous
scheduling and external delivery remain disabled and out of scope.

## Evaluation and testing

Focused tests cover daily/weekly windows, UTC validation, inverted periods,
future committee/recommendation rejection, owner and portfolio-snapshot
isolation, recommendation fidelity, evidence projection, conflict visibility,
deterministic replay, strict report validation, and execution-boundary imports.
The affected investment, recommendation, committee, Market Brief, decision, and
outcome suites passed locally: **290 passed**. Compilation and `git diff
--check` passed.

Long-term recommendation success, realized return attribution, alpha, hit rate,
calibration, and backtesting are not evaluated here; those belong to INV-11 and
INV-12.

## Safety and explicit non-goals

INV-10 does not implement:

- automatic trading or rebalancing;
- broker integration, order creation, or order execution;
- money movement or portfolio mutation;
- recommendation tracking or outcome attribution;
- backtesting, strategy optimization, or factor modeling;
- production investment UI or terminal replacement;
- new market-data providers or a duplicate portfolio ledger.

A report may state that Atlas recommends an action for human review, but it
never states that Atlas performed that action. The decision boundary remains:

```text
CIO Report → Recommendation → Human Review → Human Decision
```

## Rollback and limitations

This phase is domain-level and in-memory. Disable its caller without migration
or data rollback; prior Market Briefs, recommendations, decisions, holdings,
and research records remain untouched. Current limitations are the absence of
persistence/API integration, a deterministic structured-only narrative, and no
independent materiality thresholds beyond explicit upstream inputs.

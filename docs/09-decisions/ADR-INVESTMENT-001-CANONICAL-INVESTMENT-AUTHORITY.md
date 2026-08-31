# ADR-INVESTMENT-001: Canonical Investment Authority

- **Status:** Accepted for INV-01 implementation
- **Date:** 2026-08-30
- **Scope:** Investment Intelligence foundation only

## Decision

Atlas remains the canonical authority for investment ownership, accounts,
holdings, historical financial truth, calculations, recommendation identity,
evidence provenance, decisions, and outcomes. Investment Intelligence adds
provider-neutral contracts and projections; it does not create a parallel
ledger or replace existing Atlas models.

Current holdings are observations and must not be treated as complete
historical lots, cost basis, or performance unless canonical source history
supports that claim. External providers and open-source libraries are bounded
adapters, data sources, research tools, or analytical engines. They cannot
become the source of truth.

## Authority boundaries

- Deterministic Atlas calculations own financial arithmetic, currency validity,
  portfolio state, risk metrics, scoring, and recommendation gates.
- Evidence references preserve source/calculation identity, content hash,
  as-of/retrieval timestamps, and data state.
- LLMs may later synthesize validated evidence, but cannot create or mutate
  financial facts, holdings, prices, currency, or authoritative scores.
- The assistant investment boundary is read-only. No broker, order, trading,
  transfer, rebalance, credential, or money-movement capability is included.

## Invariants

`Unknown` is not `Zero`; `Missing` is not `No Change`; `Stale` is not `Current`;
`Estimated` is not `Observed`; and an `LLM Claim` is not a `Financial Fact`.
Current Holding is not Historical Investment Truth.

## Consequences

INV-01 contracts are additive and versioned. Immutable historical records are
never rewritten. Provider activation and persistence require later approved
phases, explicit configuration, and focused validation. Rollback consists of
disabling new contract consumers; existing Atlas financial behavior remains
operational.

## References

- `docs/09-decisions/ADR-002-CANONICAL-FINANCIAL-CORE.md`
- `docs/09-decisions/ADR-004-EVENTED-HISTORY.md`
- `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md`

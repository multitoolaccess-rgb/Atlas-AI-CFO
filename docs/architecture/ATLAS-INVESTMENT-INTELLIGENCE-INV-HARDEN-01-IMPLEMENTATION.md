# INV-HARDEN-01 — Cross-Phase Investment Integrity Hardening

## Status

**COMPLETE** — targeted implementation and focused validation passed. The hardening commit is intentionally limited to cross-phase semantic corrections and regression coverage.

## Why this phase exists

INV-01 through INV-10 established separate canonical contracts for securities, portfolio intelligence, research, committee analysis, recommendations, and CIO reports. This phase closes six integration defects that could otherwise weaken identity consistency, point-in-time safety, fail-closed calculation behavior, or report provenance.

## Fixes delivered

1. **Canonical security identity (INV-02/INV-03):** portfolio positions now derive identity from stable instrument type and symbol, never holding, account, owner, or snapshot identifiers. Unresolved/unsupported symbols remain explicitly unresolved/unsupported.
2. **Point-in-time fundamentals (INV-04):** metric derivation excludes facts known after `as_of`, requires compatible period basis/end, selects revisions deterministically, and rejects ambiguous vintage ties rather than using input order.
3. **Zero-price protection (INV-05/INV-07):** technical volatility and quantitative returns/beta fail closed when a denominator close is zero; no substitute value is fabricated.
4. **Benchmark identity (INV-07):** benchmark security identity is kept distinct from benchmark observation hashes. The calculation accepts the canonical security ID (or `SecurityIdentity`) and retains hashes only as provenance.
5. **CIO section provenance (INV-10):** report sections now link category-appropriate evidence, while committee, recommendation, conflict, and risk sections retain their specific evidence relationships. Section references must exist in report-level evidence.
6. **Additional report evidence PIT validation (INV-10):** caller-supplied evidence is rejected deterministically when `evidence.as_of > report.as_of`, with source and provenance fields preserved.

## Files changed

- `services/rules-service/app/investments/portfolio_intelligence.py`
- `services/rules-service/app/investments/fundamentals.py`
- `services/rules-service/app/investments/technicals.py`
- `services/rules-service/app/investments/quant.py`
- `services/rules-service/app/investments/cio_reports.py`
- `services/rules-service/tests/test_investment_harden_01.py`
- `services/rules-service/tests/test_investment_quant.py`

## Compatibility and boundaries

The changes preserve the INV-01 → INV-10 typed contracts and remain provider-neutral. Portfolio source holding/account provenance remains separate from security identity. Research calculations continue to use Decimal values and explicit state enums. Committee and recommendation semantics are not rewritten; CIO reporting remains an assembler. No UI, route, API, migration, persistence redesign, scheduler, or provider boundary was introduced.

The benchmark function remains compatible with string IDs and additionally accepts the canonical `SecurityIdentity`, allowing older callers to migrate without confusing IDs with observation hashes.

## Validation

Focused hardening and affected calculation/report tests passed:

- `11 passed` — hardening and quantitative regression tests
- `31 passed` — broader INV-HARDEN-01, quant, fundamentals, technicals, and CIO report tests
- Python compilation passed for `app/investments`
- `git diff --check` passed

The broader repository contains unrelated dirty dashboard/backend/UI work; those files were not modified or staged by this phase. Any unrelated baseline failures remain outside this hardening ownership boundary and must not be attributed to INV-HARDEN-01.

## Security and execution boundary

No broker, order, execution, transfer, money movement, portfolio mutation, automatic trading, or automatic rebalancing capability was introduced. No providers, credentials, secrets, dependencies, APIs, or migrations were added.

## Explicit non-goals

- INV-11 recommendation tracking was not started.
- INV-12 evaluation/backtesting was not started.
- No production UI was implemented.
- No new provider or persistence architecture was introduced.
- No completed investment phase was redesigned.
- No recommendation, committee, or portfolio lifecycle was reopened.

## Remaining acceptable technical debt

The report layer remains an in-memory deterministic projection, and the existing model contracts still rely on callers to provide canonical benchmark identity when a benchmark series is supplied. Full historical recommendation tracking, outcome attribution, and backtesting remain intentionally deferred to INV-11 and INV-12.

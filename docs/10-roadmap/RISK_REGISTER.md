# Atlas Risk Register

Status is synchronized from `PROJECT_STATUS.json`; do not treat this document
as an independent source of truth.

| ID | Description | Severity | Likelihood | Mitigation | Owner | Status | Related evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| risk-frontend-lint-debt | Repository-wide frontend lint debt remains outside Phase 0 scope. | medium | high | Keep targeted lint and CI checks; schedule bounded cleanup separately. | engineering | open | CI and import report |
| risk-monte-carlo-deferred | Monte Carlo probability model is intentionally deferred. | medium | medium | Preserve deterministic projections; authorize probability work separately. | product-architecture | open | ADR-005 |
| risk-transitional-tenancy | User-scoped tenancy remains transitional. | high | medium | Require authorization and isolation tests before expansion. | security | open | architecture/security docs |
| risk-legacy-product-names | Legacy Finance Copilot, WealthIQ, CashFlix, and Finlynq names remain. | low | high | Track bounded terminology cleanup; avoid broad rename during delivery work. | engineering | open | import report |
| risk-fixture-compatibility-names | Synthetic fixture directories retain compatibility-oriented names. | low | medium | Keep synthetic labels and manifest; rename only in a dedicated compatibility change. | quality | open | PR #1 |
| risk-service-dependency-separation | Rules Service and Finlynq require separate FastAPI-pinned environments. | high | high | Use `.venv-rules` and `.venv-finlynq`; CI provisions both independently. | engineering | mitigated | 8baa1c2, PR #1 |

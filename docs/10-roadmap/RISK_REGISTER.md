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
| risk-p1-legacy-goal-float | The existing Goal.target_amount Float can lose source precision before Phase 1 snapshot normalization. | high | medium | Convert through Decimal(str(value)), record the source representation and non-restored precision, add boundary fixtures, and review a Goal Decimal migration separately. | rules-service | open | ADR-006, issue #3 |
| risk-p1-dialect-parity | SQLite and PostgreSQL differ in exact numeric storage and concurrency semantics for immutable forecast versions. | high | medium | Require Decimal round-trip, migration, locking, uniqueness-race, and rollback tests on both supported dialects before rollout. | rules-service | open | ADR-006, issue #3 |
| risk-p1-retention-rollout-gate | No approved retention or user-deletion policy exists for immutable forecast history. | high | medium | Retain without purge or cascade, limit work to default-off validation, and block external multi-user production enablement until policy approval. | product-security | open | ADR-006, issue #3, PR #4 |
| risk-p1-trusted-generation-boundary | An untrusted generation request could forge canonical financial state or provenance if the trusted adapter boundary regresses. | high | medium | Accept no client financial-state fields, authorize the goal before one trusted adapter invocation, reject unknown fields, and require spoofing and adapter-order tests. | rules-service-security | open | ADR-006, issue #3, PR #4 |

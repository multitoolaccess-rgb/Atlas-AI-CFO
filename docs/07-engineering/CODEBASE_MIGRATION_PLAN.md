# Atlas Codebase Migration Plan

## Principle

Evolve the existing Finance Copilot incrementally; do not rewrite proven ingestion, visualization, and account capabilities without evidence.

## Phases

1. Inventory features, data flows, tests, and debt.
2. Establish canonical domain types and adapters.
3. Add goal, decision, recommendation, and audit models.
4. Introduce deterministic forecast and scoring services.
5. Add read-only agents behind evaluation gates.
6. Transform the dashboard into Mission Control.
7. Add simulation and advisor sharing.
8. Introduce approval-based execution only after security readiness.

## Release method

Feature flags, shadow calculations, dual-read comparison, migration telemetry, and reversible rollouts.

## Exit criteria

Data parity, test coverage, monitored accuracy, documented rollback, and no unresolved critical security findings.

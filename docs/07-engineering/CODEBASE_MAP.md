# Codebase Map

## Target modules

- `domain`: canonical entities and invariants
- `data`: connectors, ingestion, normalization, repositories
- `calculations`: deterministic finance functions
- `intelligence`: forecasting, scoring, simulation, and recommendations
- `agents`: orchestration and specialist prompts/tools
- `policies`: permissions, suitability, and execution guardrails
- `app`: user experience
- `observability`: logs, traces, metrics, and audit events

## Dependency direction

Experience and agents depend on domain services; domain calculations do not depend on models or UI.

## Migration

Map existing features before movement, add adapters, migrate by vertical slice, and remove legacy paths only after parity and telemetry.

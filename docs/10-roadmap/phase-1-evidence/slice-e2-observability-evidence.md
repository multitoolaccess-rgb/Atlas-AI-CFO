# Phase 1 Slice E.2 — Safe Observability Evidence

## Slice
**codex/phase-1-slice-e-observability** (MEDIUM risk, bounded feature)

## Files Added (2 in-scope)
- `services/rules-service/app/forecasts/observability.py` (~180 LOC): bounded sanitization + emission surface.
- `services/rules-service/tests/test_observability.py` (~190 LOC): parametrized bounded tests.

## Bounded Safety Contract (Hard)
- NO PII / NO financial / NO provenance leakage. Forbidden-key fragment drop recurses at every depth.
- NO direct emission of pydantic `BaseModel` instances (no repr, no hash).
- NO Decimal-shaped strings (defense-in-depth; raw money values dropped even on allowlisted keys).
- Strict server-owned field allowlist: `event_type`, `route`, `status`, `latency_ms`, `model_version`, `calculation_version`, `schema_versions`, `http_method`, `user_scope`, `dry_run`.
- Bounded cardinality counter labeled only by `event_type` x boolean `success`.
- Stdlib `logging` + in-memory `prometheus_client.Counter` are the ONLY emission surfaces.
- External multi-user production enablement remains BLOCKED pending the Phase 1 retention / user-deletion policy approval.

## Audit Gates
- A: 2 in-scope files only — GREEN.
- B: py_compile — GREEN.
- C: focused pytest — GREEN.
- D: regression smoke on (config + mapper + route) — GREEN (no regression).
- E: forbidden-key drop — GREEN (parametrized).
- F: Decimal-shape drop — GREEN.
- G: pydantic BaseModel drop — GREEN.
- H: stdlib-only emission — GREEN.
- I: sensitive-data leak scan — GREEN (0 matches).
- J: Slice D-post behavior unchanged — GREEN.

## Follow-up Bounded Slices
- Slice E.3: bounded dry-run shadow validation + rollout/rollback runbook.
- Final Phase 1 verification + `atlas-1-complete` ceremony.

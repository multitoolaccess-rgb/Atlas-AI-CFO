# Phase 1 Slice E.1 — Read-API Default-Off Flag Evidence

## Slice
**codex/phase-1-slice-e-read-api-flag** (HIGH risk, bounded feature)

## Files Modified (3 in-scope)
- `services/rules-service/app/config.py` (add `atlas_forecast_read_api_enabled: bool = False`)
- `services/rules-service/tests/test_config.py` (add 4 bounded default-off tests)
- `.env.example` (add `ATLAS_FORECAST_READ_API_ENABLED=false` line)

## Audit Gates (Verbatim)
- **A (3 in-scope files only)**: GREEN (config.py + test_config.py + .env.example).
- **B (py_compile smoke)**: GREEN (config.py + test_config.py compile cleanly).
- **C (default-off + no-client-override invariant)**: GREEN (flag lives only in server-side Settings BaseSettings).
- **D (fail-closed on invalid value)**: GREEN — `ValidationError` raised on ambiguous env values.
- **F (focused pytest)**: GREEN — 4 new tests pass; total 10 in `test_config.py`; regression smoke passes 39 across related test files.
- **Sensitive-data leak scan**: 0 matches (no snapshot JSON, raw state, JWT secret, Finlynq token in diff).

## Bounded Test Coverage
| Test                                | Behavior                                       |
|-------------------------------------|------------------------------------------------|
| `test_read_api_flag_default_is_off` | absent env -> `False`                          |
| `test_read_api_flag_explicit_false_remains_off` | `false` -> `False`              |
| `test_read_api_flag_explicit_true_enables` | `true` -> `True`                          |
| `test_read_api_flag_invalid_value_fails_closed` | ambiguous -> `ValidationError` |

## External Production Enablement
- Off (per ADR-006). No routes, adapters, observability rollout landed.
- The read-API route layer is wired in a follow-up bounded slice that consults this flag.

## Slice-D-Post Handoff
- Slice D-post certification `CERTIFIED_FOR_SLICE_E_HANDOFF` honored.
- The existing `ReadApiDisabledEnvelope` (`schemas.py` line 317) is the route-layer error shape for the follow-up wiring.

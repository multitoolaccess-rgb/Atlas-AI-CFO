# Phase 1 — Mapper Cleanup Slice Evidence

## Slice
**codex/phase-1-forecast-version-mapper-cleanup** (medium risk, bounded cleanup)

## 5 Audit Items Bundled
1. Path B1 validator swap in `app/forecasts/schemas.py` — `_check_calculation_decimal` (50 sig digits) for `monthly_real_rate` + `unrounded_*`; `_check_canonical_decimal` (38 total + 18 scale + 40 length + |v| ≤ 1E+24) for `rounded_*` + canonical-money fields.
2. `tests/test_routes_forecast_generation.py`: 9 `# BUG-` headers collapsed into module-level cleanup NOTE + xfail markers dropped where routes pass.
3. Dead-code sweep in `app/routes/forecasts_generation.py`: dropped unused imports while preserving `Annotated` for Depends-style annotations on `user_sub` + `db`.
4. Restored deterministic Slice B + Slice D-post framing inside test fixtures (Goal.id and horizon aligned with the trusted-adapter stub).
5. New `tests/test_mappers_schema_validation.py` proves B1 validator swap with quantum-aligned Decimal-string values; dead-helper sweep applied.

## Audit Gates (Verbatim)
- **A (in-scope files only)**: GREEN — 4 files in `git diff main --stat`.
- **B (validator wiring present)**: GREEN — `_check_calculation_decimal`, `_check_canonical_decimal`, `_unrounded_is_calculation_decimal`, `_rate_is_calculation_decimal`, `_money_is_canonical` all present in `schemas.py`.
- **C (Annotated retained)**: GREEN — `from typing import Annotated, Final, Optional` in `forecasts_generation.py`.
- **D (BUG- count)**: GREEN — `grep -c '^# BUG-'` = 0 in both test files.
- **E (xfail decorator count)**: GREEN — `grep -c '^@pytest.mark.xfail'` = 0 (only cleanup-NOTE comment mentions the string; not a decorator).
- **F (pytest verdict)**: GREEN — `29 passed, 0 xfailed, 35 warnings` (0 failures).
- **py_compile smoke**: GREEN — all 4 in-scope files compile cleanly.

## Reviewer Verdicts (Independent)
- Code-reviewer-minimax-m3 (14-pass bounded sequence): **APPROVE_FOR_MERGE** on committed+push head `5adb99a`.

## External Production Enablement
- Off (PER ADR-006). No routes, flags, shadow validation, observability rollout landed.

## Quantum-Invariant Verification (manual)
- Test #1: `Decimal("1.123...49digits").quantize(Decimal("0.01"), ROUND_HALF_EVEN) == Decimal("1.12")` (3rd fractional digit is '3' → round DOWN) ✓
- Test #2: `Decimal("2.987...49digits").quantize(Decimal("0.01"), ROUND_HALF_EVEN) == Decimal("2.99")` (3rd fractional digit is '7' → round UP) ✓
- Test #3: `Decimal("100.5").quantize(Decimal("0.01"), ROUND_HALF_EVEN) == Decimal("100.50")` (round-trip, numerical equality) ✓

## Slice-D-Post Certification
**CERTIFIED_FOR_SLICE_E_HANDOFF** — the bounded mapper-cleanup PR does not regress Slice D-post behavior and authorizes proceeding to Slice E.

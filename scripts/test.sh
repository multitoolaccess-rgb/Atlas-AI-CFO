#!/usr/bin/env bash
# scripts/test.sh
#
# Canonical full-stack test runner for Finance Copilot. Single command,
# deterministic output, tracks pass/fail per step.
#
# Runs:
#   1. Backend pytest          (services/rules-service, 18 tests)
#   2. Frontend vitest         (ui, 25 tests across 3 files)
#   3. Frontend typecheck      (ui, tsc --noEmit)
#   4. Playwright smoke test   (ui, 3 browser scenarios)
#
# Environment knobs:
#   SKIP_BACKEND=1     — skip step 1 (frontend-only envs)
#   SKIP_VITEST=1      — skip step 2 (faster inner loop)
#   SKIP_PLAYWRIGHT=1  — skip step 4 (CI without chromium)
#   SKIP_TYPECHECK=1   — skip step 3 (faster inner loop)
#   SKIP_TESTS=1       — bypass the pre-push hook entirely
#   FORCE_ALL_TESTS=1  — bypass the pre-push smart mode
#
# Exit code: 0 if all enabled steps pass; 1 otherwise.
#
# Used by:
#   - CI                            (manual: bash scripts/test.sh)
#   - Contributors                  (manual: npm run test:all  from ui/, or
#                                    bash scripts/test.sh  from project root)

set -uo pipefail

# Resolve paths relative to THIS script, not the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
RULES_DIR="$PROJECT_ROOT/services/rules-service"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

# ---- Pretty banner ----
echo ""
echo "=========================================="
echo "🧪  Finance Copilot — full test suite"
echo "=========================================="
echo "Project root:  $PROJECT_ROOT"
echo "UI dir:        $UI_DIR"
echo "Backend dir:   $RULES_DIR"
echo ""

# ---- Sanity checks ----
if [ ! -d "$UI_DIR" ]; then
  echo "❌  Missing $UI_DIR. Run from the project root."; exit 1
fi
if [ ! -d "$UI_DIR/node_modules" ]; then
  echo "❌  $UI_DIR/node_modules is missing. Run: (cd $UI_DIR && npm install)"
  exit 1
fi

# ---- Step runner (track pass/fail) ----
PASS=0
FAIL=0
FAILED_STEPS=()

run_step() {
  local name="$1"
  shift
  echo ""
  echo "=========================================="
  echo "▶  $name"
  echo "=========================================="
  if "$@"; then
    PASS=$((PASS + 1))
    echo "✅  $name: PASS"
  else
    FAIL=$((FAIL + 1))
    FAILED_STEPS+=("$name")
    echo "❌  $name: FAIL"
  fi
}

# ---- Step 1: backend pytest ----
step_backend() {
  if [ ! -x "$VENV_PY" ]; then
    echo "❌  $VENV_PY missing. Run: bash scripts/bootstrap.sh"
    return 1
  fi
  cd "$RULES_DIR"
  # The .env uses SQLite for local dev (see services/rules-service/.env),
  # so pytest will use the SQLite path whether or not postgres is running
  # on :5433. We check best-effort for visibility only.
  if command -v pg_isready >/dev/null 2>&1; then
    if ! pg_isready -h localhost -p 5433 -q 2>/dev/null; then
      echo "→ postgres on :5433 not running; pytest will use the SQLite path from .env"
    fi
  fi
  "$VENV_PY" -m pytest -q --tb=short
}

# ---- Step 1b: finlynq backend pytest ----
step_finlynq_backend() {
  if [ ! -x "$VENV_PY" ]; then
    echo "❌  $VENV_PY missing. Run: bash scripts/bootstrap.sh"
    return 1
  fi
  # finlynq's pytest.ini sets `pythonpath = .` so the flat
  # `from app.main import app` imports used in tests/* resolve when
  # pytest is run from inside services/finlynq.
  cd "$PROJECT_ROOT/services/finlynq"
  "$VENV_PY" -m pytest -q --tb=short
}

# ---- Step 2: frontend vitest ----
step_vitest() {
  cd "$UI_DIR"
  ./node_modules/.bin/vitest run
}

# ---- Step 3: frontend tsc ----
step_typecheck() {
  cd "$UI_DIR"
  ./node_modules/.bin/tsc --noEmit
}

# ---- Step 4: Playwright browser smoke test ----
step_playwright() {
  cd "$UI_DIR"
  ./node_modules/.bin/playwright test
}

# ---- Run the enabled steps ----
if [ "${SKIP_BACKEND:-0}" != "1" ]; then
  run_step "Backend pytest (services/rules-service)" step_backend
else
  echo ""
  echo "⏭  SKIP_BACKEND=1 — skipping backend pytest"
fi

if [ "${SKIP_FINLYNQ:-0}" != "1" ]; then
  run_step "Backend pytest (services/finlynq)" step_finlynq_backend
else
  echo ""
  echo "⏭  SKIP_FINLYNQ=1 — skipping finlynq backend pytest"
fi

if [ "${SKIP_VITEST:-0}" != "1" ]; then
  run_step "Frontend vitest (ui)" step_vitest
else
  echo ""
  echo "⏭  SKIP_VITEST=1 — skipping frontend vitest"
fi

if [ "${SKIP_TYPECHECK:-0}" != "1" ]; then
  run_step "Frontend typecheck (tsc --noEmit)" step_typecheck
else
  echo ""
  echo "⏭  SKIP_TYPECHECK=1 — skipping typecheck"
fi

if [ "${SKIP_PLAYWRIGHT:-0}" != "1" ]; then
  run_step "Playwright browser smoke test (ui/__tests__/e2e)" step_playwright
else
  echo ""
  echo "⏭  SKIP_PLAYWRIGHT=1 — skipping Playwright"
fi

# ---- Final summary ----
echo ""
echo "=========================================="
TOTAL=$((PASS + FAIL))
echo "🏁  SUMMARY: $PASS/$TOTAL steps passed"
if [ $FAIL -gt 0 ]; then
  echo "Failed steps:"
  for step in "${FAILED_STEPS[@]}"; do
    echo "  - $step"
  done
  echo "=========================================="
  exit 1
fi
echo "✅  All tests passed."
echo "=========================================="
exit 0

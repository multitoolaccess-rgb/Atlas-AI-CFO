#!/usr/bin/env bash
# scripts/test-e2e.sh
#
# Full E2E test runner: starts the rules-service backend on :8000 if not
# already running, then runs the Playwright browser smoke test against the
# live stack (Next.js dev server on :3000 auto-started by playwright's
# webServer config).
#
# Why this exists alongside scripts/test.sh:
#   scripts/test.sh runs the smoke test against a no-backend-tolerant page
#   (the dashboard renders the loading state; vitest covers the actual
#   backend integration). scripts/test-e2e.sh verifies the full stack:
#   real backend + real axios round-trip + real /api/auth/devlogin +
#   real /api/dashboard/summary.
#
# Exit code: 0 if all scenarios pass; 1 otherwise.
#
# Used by:
#   - CI                            (manual: bash scripts/test-e2e.sh)
#   - Contributors                  (manual: bash scripts/test-e2e.sh
#                                    or npm run test:e2e from ui/)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
RULES_DIR="$PROJECT_ROOT/services/rules-service"
RULES_VENV_PY="$PROJECT_ROOT/.venv-rules/bin/python"
BACKEND_LOG="/tmp/finance-copilot-e2e-backend.log"
BACKEND_PID=""
STARTED_BACKEND=0

cleanup() {
  if [ "$STARTED_BACKEND" = "1" ] && [ -n "$BACKEND_PID" ]; then
    echo ""
    echo "→ Stopping backend (pid $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    echo "  backend log: $BACKEND_LOG"
  fi
}
trap cleanup EXIT INT TERM

# ---- Pretty banner ----
echo ""
echo "=========================================="
echo "🧪  Finance Copilot — E2E test runner"
echo "=========================================="
echo ""

# ---- Sanity checks ----
if [ ! -x "$RULES_VENV_PY" ]; then
  echo "❌  Rules Service environment missing: $RULES_VENV_PY. Run: bash scripts/bootstrap.sh"
  exit 1
fi
if [ ! -d "$UI_DIR/node_modules/@playwright/test" ]; then
  echo "❌  @playwright/test not installed. Run: (cd $UI_DIR && npm install)"
  exit 1
fi

# ---- Backend: start if not running ----
start_backend() {
  echo "→ Starting backend (rules-service on :8000)..."
  cd "$RULES_DIR"
  DATABASE_URL='sqlite:///./finance.db' \
  JWT_SECRET='dev-jwt-secret-for-tests-only-32chars-min' \
  LOCAL_USER='alex' \
    "$RULES_VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      > "$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!
  STARTED_BACKEND=1
  # Wait for /health to respond (max 15s)
  for i in $(seq 1 15); do
    if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
      echo "  backend up (pid $BACKEND_PID, log: $BACKEND_LOG)"
      return 0
    fi
    sleep 1
  done
  echo "❌  Backend failed to start within 15s. See $BACKEND_LOG"
  return 1
}

if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
  echo "→ Backend already running on :8000 (will reuse)"
else
  start_backend || exit 1
fi

# ---- Playwright smoke test ----
echo ""
echo "=========================================="
echo "▶ Playwright browser smoke test (live backend)"
echo "=========================================="
cd "$UI_DIR"
./node_modules/.bin/playwright test
EXIT=$?

if [ $EXIT -eq 0 ]; then
  echo ""
  echo "=========================================="
  echo "✅  E2E suite passed."
  echo "=========================================="
else
  echo ""
  echo "=========================================="
  echo "❌  E2E suite failed (exit $EXIT)."
  echo "=========================================="
fi
exit $EXIT

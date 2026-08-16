#!/usr/bin/env bash
# scripts/test-e2e.sh
#
# Full E2E test runner: starts Finlynq on :8001 and rules-service on :8000
# when they are not already running, then runs the Playwright browser suite
# against a runner-owned live stack, including the Next.js dev server on
# :3000. Playwright's webServer hook is disabled for this invocation so the
# runner has one explicit owner and bounded readiness/timeout diagnostics.
#
# Why this exists alongside scripts/test.sh:
#   scripts/test.sh runs the smoke test against a no-backend-tolerant page
#   (the dashboard renders the loading state; vitest covers the actual
#   backend integration). scripts/test-e2e.sh verifies the full stack:
#   real Finlynq + Rules Service + real axios round-trip + real
#   /api/auth/devlogin + real /api/dashboard/summary.
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
FINLYNQ_DIR="$PROJECT_ROOT/services/finlynq"
FINLYNQ_VENV_PY="$PROJECT_ROOT/.venv-finlynq/bin/python"
RULES_LOG="/tmp/finance-copilot-e2e-rules.log"
FINLYNQ_LOG="/tmp/finance-copilot-e2e-finlynq.log"
RULES_PID=""
FINLYNQ_PID=""
UI_PID=""
STARTED_RULES=0
STARTED_FINLYNQ=0
STARTED_UI=0
TEST_JWT_SECRET='dev-jwt-secret-for-tests-only-32chars-min'
E2E_TMP_DIR="${TMPDIR:-/tmp}"
E2E_DB_PATH=""
E2E_DATABASE_URL=""
# Rules Service imports the full application and can be slower than the
# lightweight health-only Finlynq boot on cold GitHub-hosted runners.
RULES_STARTUP_TIMEOUT_SECONDS=60
UI_STARTUP_TIMEOUT_SECONDS=60
PLAYWRIGHT_TIMEOUT_SECONDS="${E2E_PLAYWRIGHT_TIMEOUT_SECONDS:-900}"
UI_LOG="/tmp/finance-copilot-e2e-ui.log"

cleanup() {
  if [ "$STARTED_UI" = "1" ] && [ -n "$UI_PID" ]; then
    echo ""
    echo "→ Stopping UI server (pid $UI_PID)..."
    kill "$UI_PID" 2>/dev/null || true
    wait "$UI_PID" 2>/dev/null || true
    echo "  UI log: $UI_LOG"
  fi
  if [ "$STARTED_RULES" = "1" ] && [ -n "$RULES_PID" ]; then
    echo ""
    echo "→ Stopping Rules Service (pid $RULES_PID)..."
    kill "$RULES_PID" 2>/dev/null || true
    wait "$RULES_PID" 2>/dev/null || true
    echo "  Rules Service log: $RULES_LOG"
  fi
  if [ "$STARTED_FINLYNQ" = "1" ] && [ -n "$FINLYNQ_PID" ]; then
    echo "→ Stopping Finlynq (pid $FINLYNQ_PID)..."
    kill "$FINLYNQ_PID" 2>/dev/null || true
    wait "$FINLYNQ_PID" 2>/dev/null || true
    echo "  Finlynq log: $FINLYNQ_LOG"
  fi
  if [ -n "$E2E_DB_PATH" ]; then
    case "$E2E_DB_PATH" in
      "$E2E_TMP_DIR"/atlas-ai-cfo-e2e-*.db)
        rm -f -- "$E2E_DB_PATH" "${E2E_DB_PATH}-wal" "${E2E_DB_PATH}-shm"
        echo "→ Removed isolated E2E database"
        ;;
      *)
        echo "→ Refusing to remove unexpected E2E database path: $E2E_DB_PATH"
        ;;
    esac
  fi
}
trap cleanup EXIT INT TERM

print_rules_log_tail() {
  echo "---- Rules Service log tail (sanitized) ----"
  if [ -f "$RULES_LOG" ]; then
    tail -n 80 "$RULES_LOG" | sed -E \
      -e 's#(postgres(ql)?|mysql)://[^[:space:]]+#\1://[REDACTED]#g' \
      -e 's#(JWT_SECRET|DATABASE_URL|FINLYNQ_BASE_URL)=[^[:space:]]+#\1=[REDACTED]#g' \
      -e 's#Bearer[[:space:]]+[A-Za-z0-9._-]+#Bearer [REDACTED]#g' || true
  else
    echo "  (Rules Service log was not created)"
  fi
  echo "----------------------------------------------"
}

prepare_e2e_database() {
  E2E_DB_PATH="$(mktemp "$E2E_TMP_DIR/atlas-ai-cfo-e2e-XXXXXX.db")"
  E2E_DATABASE_URL="sqlite:///$E2E_DB_PATH"
  echo "→ Migrating isolated E2E database..."
  (
    cd "$RULES_DIR"
    DATABASE_URL="$E2E_DATABASE_URL" "$RULES_VENV_PY" -m alembic -c alembic.ini upgrade head
  )
}

require_port_available() {
  local port="$1"
  local service="$2"
  if ! command -v lsof >/dev/null 2>&1; then
    echo "❌  Cannot verify whether port $port is available because lsof is not installed."
    return 1
  fi
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "❌  Port $port is already in use; stop the local $service service before running the hermetic E2E suite."
    return 1
  fi
}

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
if [ ! -x "$FINLYNQ_VENV_PY" ]; then
  echo "❌  Finlynq environment missing: $FINLYNQ_VENV_PY. Run: bash scripts/bootstrap.sh"
  exit 1
fi
if [ ! -d "$UI_DIR/node_modules/@playwright/test" ]; then
  echo "❌  @playwright/test not installed. Run: (cd $UI_DIR && npm install)"
  exit 1
fi

# This suite writes test data. Never reuse a developer service at either
# fixed endpoint: doing so would route browser mutations outside the isolated
# E2E database.
require_port_available 8001 "Finlynq" || exit 1
require_port_available 8000 "Rules Service" || exit 1
require_port_available 3000 "UI server" || exit 1

# Rules Service deliberately does not auto-migrate by default. Build its
# schema before either service starts so the live browser stack never reads a
# developer's finance.db and Finlynq shares the same canonical E2E state.
prepare_e2e_database || exit 1

# ---- Service dependencies: start and own the entire live stack ----
start_finlynq() {
  echo "→ Starting Finlynq on :8001..."
  cd "$FINLYNQ_DIR"
  DATABASE_URL="$E2E_DATABASE_URL" \
  JWT_SECRET="$TEST_JWT_SECRET" \
  LOCAL_USER='alex' \
    "$FINLYNQ_VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8001 \
      > "$FINLYNQ_LOG" 2>&1 &
  FINLYNQ_PID=$!
  STARTED_FINLYNQ=1
  for i in $(seq 1 15); do
    if curl -s -f http://localhost:8001/health >/dev/null 2>&1; then
      echo "  Finlynq up (pid $FINLYNQ_PID, log: $FINLYNQ_LOG)"
      return 0
    fi
    sleep 1
  done
  echo "❌  Finlynq failed to start within 15s. See $FINLYNQ_LOG"
  return 1
}

start_rules() {
  echo "→ Starting Rules Service on :8000..."
  cd "$RULES_DIR"
  DATABASE_URL="$E2E_DATABASE_URL" \
  JWT_SECRET="$TEST_JWT_SECRET" \
  LOCAL_USER='alex' \
  FINLYNQ_BASE_URL='http://localhost:8001' \
    "$RULES_VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      > "$RULES_LOG" 2>&1 &
  RULES_PID=$!
  STARTED_RULES=1
  for i in $(seq 1 "$RULES_STARTUP_TIMEOUT_SECONDS"); do
    if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
      echo "  Rules Service up (pid $RULES_PID, log: $RULES_LOG)"
      return 0
    fi
    sleep 1
  done
  echo "❌  Rules Service failed to start within ${RULES_STARTUP_TIMEOUT_SECONDS}s. See $RULES_LOG"
  print_rules_log_tail
  return 1
}

start_ui() {
  echo "→ Starting isolated UI server on :3000..."
  cd "$UI_DIR"
  NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8000' \
    npm run dev -- --hostname 127.0.0.1 --port 3000 > "$UI_LOG" 2>&1 &
  UI_PID=$!
  STARTED_UI=1
  for i in $(seq 1 "$UI_STARTUP_TIMEOUT_SECONDS"); do
    if curl -s -f http://localhost:3000/ >/dev/null 2>&1; then
      echo "  UI up (pid $UI_PID, log: $UI_LOG)"
      return 0
    fi
    sleep 1
  done
  echo "❌  UI failed to return HTTP within ${UI_STARTUP_TIMEOUT_SECONDS}s. See $UI_LOG"
  return 1
}

start_finlynq || exit 1
start_rules || exit 1
start_ui || exit 1

# ---- Playwright smoke test ----
echo ""
echo "=========================================="
echo "▶ Playwright browser smoke test (live backend)"
echo "=========================================="
cd "$UI_DIR"
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL='http://localhost:3000' \
  ./node_modules/.bin/playwright test "$@" > /tmp/finance-copilot-e2e-playwright.log 2>&1 &
PLAYWRIGHT_PID=$!
STARTED_AT=$(date +%s)
while kill -0 "$PLAYWRIGHT_PID" 2>/dev/null; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - STARTED_AT))
  if [ "$ELAPSED" -ge "$PLAYWRIGHT_TIMEOUT_SECONDS" ]; then
    echo "❌  Playwright exceeded ${PLAYWRIGHT_TIMEOUT_SECONDS}s; terminating pid $PLAYWRIGHT_PID."
    kill "$PLAYWRIGHT_PID" 2>/dev/null || true
    wait "$PLAYWRIGHT_PID" 2>/dev/null || true
    EXIT=124
    break
  fi
  echo "  Playwright running (${ELAPSED}s; pid $PLAYWRIGHT_PID)"
  sleep 15
done
if [ -z "${EXIT:-}" ]; then
  wait "$PLAYWRIGHT_PID"
  EXIT=$?
fi
cat /tmp/finance-copilot-e2e-playwright.log

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

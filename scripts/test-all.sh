#!/bin/bash
# Finance Copilot — Consolidated Test Runner
# ------------------------------------------
# Runs ALL test tiers in order and prints a rollup so the developer
# can see at a glance what passed, what failed, and (if everything
# was green) how long it took.
#
# Tiers:
#   1. Backend pytest            (~30 s) — services/rules-service + finlynq + tests/
#   2. Frontend vitest unit      (~10 s) — ui/__tests__/*.test.ts
#   3. Frontend typecheck        (~15 s) — tsc --noEmit
#   4. End-to-end (Playwright)   (~45 s) — ui/__tests__/e2e/*.spec.ts
#
# PLUS the consolidated project tests at tests/test_start_sh_{unit,e2e}.py
# (the cold-boot contract suite from the round-7 wave).
#
# Outputs go to /tmp/fc-*.log. The run is non-destructive — the
# rules-service DB is isolated under /tmp/fc-*test*.db files.
#
# Quick usage:
#   bash scripts/test-all.sh            # FULL suite
#   bash scripts/test-all.sh --no-e2e   # skip Playwright
#   bash scripts/test-all.sh --be-only  # backend pytest only
#
# Exit codes: 0 if all tiers pass; the FIRST failing tier's exit code otherwise.

set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
RULES_VENV_PY="$PROJECT_ROOT/.venv-rules/bin/python"
FINLYNQ_VENV_PY="$PROJECT_ROOT/.venv-finlynq/bin/python"
RUN_DIR="$PROJECT_ROOT/.run"
mkdir -p "$RUN_DIR"

# ---- arg parsing -------------------------------------------------------
SKIP_E2E=0
BE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-e2e)  SKIP_E2E=1 ;;
    --be-only) BE_ONLY=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
  esac
done

# ---- sweep stale pyc / temp DBs ---------------------------------------
find "$PROJECT_ROOT"/services "$PROJECT_ROOT"/tests -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null >/dev/null
rm -f /tmp/fc-rules-test-*.db /tmp/fc-finlynq-test-*.db /tmp/fc-cross-engine-*.db 2>/dev/null

RULES_VENV_OK=0
FINLYNQ_VENV_OK=0
[ -x "$RULES_VENV_PY" ] && RULES_VENV_OK=1
[ -x "$FINLYNQ_VENV_PY" ] && FINLYNQ_VENV_OK=1

# ---- helpers -----------------------------------------------------------
hr()  { printf '\n=== %s ===\n' "$1"; }
ok()  { printf '  ✓ %s\n' "$1"; }
bad() { printf '  ✗ %s\n' "$1"; }

# ---- rollup state ------------------------------------------------------
TIERS=()

# ---- TIER 1 — backend pytest -------------------------------------------
hr "TIER 1 — backend pytest"
TIER1_RC=0
if [ "$RULES_VENV_OK" -eq 0 ] || [ "$FINLYNQ_VENV_OK" -eq 0 ]; then
  [ "$RULES_VENV_OK" -eq 0 ] && bad "missing Rules Service environment at $RULES_VENV_PY — run scripts/bootstrap.sh first"
  [ "$FINLYNQ_VENV_OK" -eq 0 ] && bad "missing Finlynq environment at $FINLYNQ_VENV_PY — run scripts/bootstrap.sh first"
  TIER1_RC=1
else
  set +e
  ( cd "$PROJECT_ROOT/services/rules-service"
    "$RULES_VENV_PY" -m pytest -q --tb=short -p no:cacheprovider --no-header \
      tests/ 2>&1 ) > /tmp/fc-tier1-be.log
  TIER1_BE_RC=$?
  if [ -f "$PROJECT_ROOT/services/finlynq/pytest.ini" ]; then
    ( cd "$PROJECT_ROOT/services/finlynq"
      "$FINLYNQ_VENV_PY" -m pytest -q --tb=short -p no:cacheprovider --no-header \
        tests/ 2>&1 ) > /tmp/fc-tier1-fq.log
    TIER1_FQ_RC=$?
    TIER1_FQ_NOTE="ok"
  else
    TIER1_FQ_RC=0
    TIER1_FQ_NOTE="(no pytest.ini — skipped)"
    # Touch an empty log so the rollup's path reference points at a
    # real artifact (operators tailing /tmp/fc-tier*.log don't get a
    # confusing file-not-found from a no-op finlynq run).
    : > /tmp/fc-tier1-fq.log
  fi
  ( cd "$PROJECT_ROOT/tests"
    "$RULES_VENV_PY" -m pytest -v --tb=short -p no:cacheprovider --no-header \
      test_start_sh_unit.py test_start_sh_e2e.py 2>&1 ) > /tmp/fc-tier1-proj.log
  TIER1_PROJ_RC=$?
  set -e
  TIER1_RC=$((TIER1_BE_RC | TIER1_FQ_RC | TIER1_PROJ_RC))
  case "$TIER1_RC" in 0) ok "rules-service  → /tmp/fc-tier1-be.log"
                        ok "finlynq        $TIER1_FQ_NOTE → /tmp/fc-tier1-fq.log"
                        ok "project tests  → /tmp/fc-tier1-proj.log" ;;
                  *) bad "rules-service  (rc=$TIER1_BE_RC)    → /tmp/fc-tier1-be.log"
                     bad "finlynq        (rc=$TIER1_FQ_RC)    → /tmp/fc-tier1-fq.log"
                     bad "project tests  (rc=$TIER1_PROJ_RC) → /tmp/fc-tier1-proj.log" ;;
  esac
fi
TIERS+=("backend-pytest:$TIER1_RC")

if [ "$BE_ONLY" -eq 1 ]; then
  hr "ROLLUP"
  printf '  %-22s rc=%s\n' "backend-pytest" "$TIER1_RC"
  exit "$TIER1_RC"
fi

# ---- TIER 2 — frontend vitest unit -------------------------------------
hr "TIER 2 — frontend vitest unit tests"
TIER2_RC=0
if ! command -v npm >/dev/null 2>&1; then
  bad "npm not on PATH"
  TIER2_RC=1
else
  set +e
  ( cd "$PROJECT_ROOT/ui" && npm run test --silent 2>&1 ) > /tmp/fc-tier2-fe.log
  TIER2_RC=$?
  set -e
  if [ "$TIER2_RC" -eq 0 ]; then
    ok "vitest              → /tmp/fc-tier2-fe.log"
  else
    bad "vitest (rc=$TIER2_RC) → /tmp/fc-tier2-fe.log"
  fi
fi
TIERS+=("fe-vitest:$TIER2_RC")

# ---- TIER 3 — frontend typecheck --------------------------------------
hr "TIER 3 — frontend typecheck (tsc --noEmit)"
TIER3_RC=0
set +e
( cd "$PROJECT_ROOT/ui" && npm run typecheck --silent 2>&1 ) > /tmp/fc-tier3-tsc.log
TIER3_RC=$?
set -e
if [ "$TIER3_RC" -eq 0 ]; then ok "tsc --noEmit        → /tmp/fc-tier3-tsc.log"
else bad "tsc (rc=$TIER3_RC) → /tmp/fc-tier3-tsc.log"; fi
TIERS+=("fe-typecheck:$TIER3_RC")

# ---- TIER 4 — end-to-end (Playwright) — optional -----------------------
TIER4_RC=0
if [ "$SKIP_E2E" -eq 1 ]; then
  hr "TIER 4 — e2e (skipped via --no-e2e)"
  ok "e2e (skipped)"
else
  hr "TIER 4 — e2e (Playwright)"
  if [ "$RULES_VENV_OK" -eq 0 ]; then
    bad "Rules Service environment missing — can't run backend; skipping e2e"
    TIER4_RC=1
  else
    set +e
    ( cd "$PROJECT_ROOT" && bash scripts/test-e2e.sh 2>&1 ) > /tmp/fc-tier4-e2e.log
    TIER4_RC=$?
    set -e
    if [ "$TIER4_RC" -eq 0 ]; then ok "playwright          → /tmp/fc-tier4-e2e.log"
    else bad "playwright (rc=$TIER4_RC) → /tmp/fc-tier4-e2e.log"; fi
  fi
  TIERS+=("e2e:$TIER4_RC")
fi

# ---- rollup ------------------------------------------------------------
ANY_FAIL=0
hr "ROLLUP"
for t in "${TIERS[@]}"; do
  name=${t%%:*}
  rc=${t##*:}
  marker='✓'
  [ "$rc" -ne 0 ] && marker='✗' && ANY_FAIL=1
  printf '  %s %-22s rc=%s\n' "$marker" "$name" "$rc"
done

hr "SUMMARY"
if [ "$ANY_FAIL" -eq 0 ]; then
  ok "ALL TIERS PASSED"
  exit 0
else
  bad "SEE PER-TIER LOGS UNDER /tmp/fc-tier*.log"
  exit 1
fi

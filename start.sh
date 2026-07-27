#!/bin/bash
# Finance Copilot - Dev Server Startup
# ------------------------------------
# Launches THREE services in the background:
#   • Finlynq             on :8001 (canonical store; Phase F4 ship target)
#   • Rules-service       on :8000 (auth + UI-facing routes; Phase 11 ship)
#   • Next.js UI          on :3000
# then waits for each port to return 200, prints a final status block with
# PIDs, HTTP codes, log paths.
#
# Logs:
#   $PROJECT_ROOT/.run/finlynq.log
#   $PROJECT_ROOT/.run/backend.log
#   $PROJECT_ROOT/.run/frontend.log
#   $PROJECT_ROOT/.run/start.sh.stdout.log  (when invoked with bash … 2>&1)
#   $PROJECT_ROOT/.run/finlynq-pip.log      (Finlynq dep-install log)
#
# Lifecycle:
#   Re-running this script will reap any *this project's* stale
#   listeners on :8001 / :8000 / :3000 and start fresh. It will NOT
#   kill an unrelated process that happens to be on the same port.
#
# Stop:
#   kill $(cat .run/fq.pid .run/be.pid .run/fe.pid)
#
# Tails:
#   tail -f .run/finlynq.log .run/backend.log .run/frontend.log

set -u  # do NOT use -e: we want to continue past stale-listener cleanup

# Per-service healthcheck budget (seconds). Defaults preserve the user's
# 30s spec; slow boxes can lift these without editing the script.
: "${START_FQ_TIMEOUT:=30}" "${START_BE_TIMEOUT:=30}" "${START_FE_TIMEOUT:=30}"

# ----- paths --------------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
BE_DIR="$PROJECT_ROOT/services/rules-service"
FQ_DIR="$PROJECT_ROOT/services/finlynq"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
NEXT_BIN="$UI_DIR/node_modules/.bin/next"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_BE="$RUN_DIR/backend.log"
LOG_FE="$RUN_DIR/frontend.log"
LOG_FQ="$RUN_DIR/finlynq.log"
LOG_PIP="$RUN_DIR/finlynq-pip.log"
PID_BE="$RUN_DIR/be.pid"
PID_FE="$RUN_DIR/fe.pid"
PID_FQ="$RUN_DIR/fq.pid"
mkdir -p "$RUN_DIR"

# Tracked array of PIDs that have been launched successfully + still
# running. We append to it from each launch block ONLY when nohup
# actually fires. On the strict-gate failure branch we walk the array
# + SIGTERM them so the user doesn't have to manually kill otherwise
# healthy services just because ONE probe timed out.
STARTED_PIDS=()

# ----- helpers ------------------------------------------------------------
hr()   { printf '\n=== %s ===\n' "$1"; }
note() { printf '  • %s\n' "$1"; }

# Polls one TCP port until it returns HTTP 200 within $timeout seconds;
# returns 0 on success, 1 on timeout. $1=URL, $2=label, $3=timeout, $4=log
# (used to point operators at the right log file on a timeout banner).
# We re-implement wait_for_health here rather than depending on
# external tools so this script is self-contained at any checkout.
http_probe() {
  local url=$1
  local code
  code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)
  [ -z "$code" ] && code=000
  printf '%s' "$code"
}

# Wait until the given URL returns HTTP 200, or until the timeout elapses.
# Differs from the now-removed ``wait_for_port``: probes the *real*
# healthcheck endpoint (e.g. ``/health`` on the BE) rather than just
# ``/`` so we know the service is actually serving traffic, not merely
# bound to a TCP port. Only an exact 200 is accepted; 3xx / 5xx / 000 all
# count as "not ready".
wait_for_health() {
  local url=$1 label=$2 timeout=$3 log=$4
  local end=$((SECONDS + timeout))
  while [ $SECONDS -lt $end ]; do
    local code
    code=$(http_probe "$url")
    if [ "$code" = "200" ]; then
      printf '  ✓ %-12s %s ready (HTTP %s)\n' "$label" "$url" "$code"
      return 0
    fi
    sleep 1
  done
  printf '  ✗ %-12s %s did NOT return 200 within %ss — see %s\n' "$label" "$url" "$timeout" "$log"
  return 1
}

# Reap HTTP listeners on the given port, but ONLY if the cmdline identifies
# them as part of this project (finance-copilot / rules-service / finlynq /
# uvicorn / next-server / "next dev"). Leaves listeners of unrelated
# projects alone.
reap_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  [ -z "$pids" ] && return 0

  local project_pid=
  for pid in $pids; do
    local cmd
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    case "$cmd" in
      *finance-copilot*|*rules-service*|*finlynq*|*uvicorn*|*next-server*|"next dev"*)
        project_pid=$pid
        break
        ;;
    esac
  done

  if [ -n "$project_pid" ]; then
    printf '  ⚠️  port :%s busy w/ stale copilot pid=%s — killing\n' "$port" "$project_pid"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 1
  else
    printf '  ℹ️  port :%s has pid(s) %s — leaving alone (cmdline not this project)\n' "$port" "$pids"
  fi
}

# cleanup_started_pids: SIGTERM (then SIGKILL after a 3s grace) every
# PID in the $STARTED_PIDS array — RECURSIVELY, so any uvicorn/next-dev
# child workers inherit the same fate. Called from the strict-gate
# failure branch so a timeout on ONE service doesn't leave the OTHER
# two orphans running until the operator notices.
#
# Round-7 reviewer hardening (after a 0.5s grace + non-tree-walking
# initial cut tripped on busy CI runners):
#   • 0.5s -> 3s SIGTERM grace. uvicorn's ASGI shutdown can block on
#     websocket close / atexit drain for >500ms; a tight window risks
#     orphaning a half-shut-down worker.
#   • Single parallel sleep after the SIGTERM loop, NOT per-PID — the
#     inner-loop ``sleep 0.5`` in v1 was 1.5s sequential on 3 services.
#   • ``pgrep -P $pid`` recursive tree walk. If a future uvicorn
#     line lands ``--workers > 1``, the parent dies but children
#     otherwise hold the ports; walking the tree closes that gap.
cleanup_started_pids() {
  local pid
  # SIGTERM across the tree rooted at every tracked PID.
  for pid in "${STARTED_PIDS[@]}"; do
    [ -z "$pid" ] && continue
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    [ -n "$children" ] && kill -TERM $children 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  # One parallel grace window — not per-PID.
  sleep 3
  # Escalate: SIGKILL anything still alive (parent OR child).
  for pid in "${STARTED_PIDS[@]}"; do
    [ -z "$pid" ] && continue
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    [ -n "$children" ] && kill -KILL $children 2>/dev/null || true
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  done
  return 0
}

# ----- intro --------------------------------------------------------------
hr "Finance Copilot — Dev Server (Finlynq + Rules + UI)"
note "root : $PROJECT_ROOT"
note "ui   : $UI_DIR"
note "be   : $BE_DIR"
note "fq   : $FQ_DIR"

# ----- frontend dependency gate ------------------------------------------
if [ ! -d "$UI_DIR/node_modules" ]; then
  hr "📦 Installing ui/node_modules"
  if ! ( cd "$UI_DIR" && npm install ); then
    printf '  ✗ npm install failed — see output above\n'
    exit 1
  fi
fi

if [ ! -x "$NEXT_BIN" ]; then
  printf '  ✗ %s missing after install — re-run `npm install` from %s\n' "$NEXT_BIN" "$UI_DIR"
  exit 1
fi

# ----- clean next.js cache (faster compile on cold start) -----------------
hr "🧹 Cleaning Next.js cache"
rm -rf "$UI_DIR/.next" "$UI_DIR/node_modules/.cache"

# ----- reap any stale listeners left over from prior sessions --------------
# Only :8001 / :8000 / :3000 are owned by this script. Other ports
# (e.g. :8081) are skipped on purpose — see file header.
hr "🧹 Reaping stale copilot listeners (if any)"
reap_port 8001
reap_port 8000
reap_port 3000

# ----- shared JWT_SECRET between rules-service and Finlynq -----
# Phase F2 cross-service invariant: the ``fc_session`` cookie minted by
# rules-service's ``POST /api/auth/devlogin`` MUST be accepted by Finlynq's
# ``Depends(require_user)``. Without this, Finlynq falls back to the
# default ``"dev-secret-change-in-production"`` from its config.py,
# ``verify_token`` rejects the cookie, the dashboard forwarder relays
# the 401 to the FE, and the FE renders "Session expired" even though
# the user's local session was fine (it was a downstream auth mismatch).
#
# Layered defense:
#   1. ``services/finlynq/.env`` pins JWT_SECRET to the same value as
#      ``services/rules-service/.env`` (the source of truth).
#   2. This ``export`` makes uvicorn inherit the value from the shell,
#      so a future env-file drift CANNOT silently desync the two.
# If both ``.env`` files drift AND this export is removed, the dev
# sees the dashboard "Session expired" flash on first paint. Fix by
# either re-exporting here OR mirroring the value in both .env files.
hr "🔐 Aligning shared config across services"
if [ -f "$BE_DIR/.env" ] && grep -q '^JWT_SECRET=' "$BE_DIR/.env"; then
  EXPORT_JWT_SECRET=$(grep '^JWT_SECRET=' "$BE_DIR/.env" | head -1 | cut -d= -f2-)
  if [ -n "$EXPORT_JWT_SECRET" ]; then
    export JWT_SECRET="$EXPORT_JWT_SECRET"
    note "JWT_SECRET : exported to shell from $BE_DIR/.env (Finlynq + Rules will inherit)"
  fi
fi

# Phase F2 shared-DB invariant: Finlynq MUST read the same finance.db that
# rules-service owns. Without this export, Finlynq's relative
# ``sqlite:///./finance.db`` resolves to its own CWD
# (``services/finlynq/finance.db``) — an empty DB with 0 accounts and
# 0 transactions. The dashboard forwarder relays Finlynq's /state/summary
# which queries that empty DB → the UI shows $0 balance despite real data
# living in ``services/rules-service/finance.db``.
export DATABASE_URL="sqlite:///$BE_DIR/finance.db"
note "DATABASE_URL : $DATABASE_URL (shared between Finlynq + Rules)"

# ----- ensure Finlynq parser deps are installed in .venv ------------------
# ``services/rules-service/requirements.txt`` already installs fastapi,
# uvicorn, pydantic, httpx (the common surface Finlynq shares). The
# Phase-F3 lift pulled in pdfplumber / pandas / pytesseract / openpyxl
# for Finlynq's parse_router — those live in
# services/finlynq/requirements.txt and need a one-time ``pip install``
# on a fresh clone.
#
# Polish #2: PROBE-THEN-SKIP. The probe set is DERIVED from
# finlynq/requirements.txt at probe time — NOT a hand-maintained import
# list. A static `import fastapi, httpx, ...` allowlist silently regresses
# when a new dep ships in requirements.txt (round-7 reviewer #1 surfaced
# uvicorn/pydantic-settings/python-jose/Pillow/ofxparse/xlrd/reportlab
# missing from a hand-maintained list — a fresh clone would probe-pass
# + skip pip + fail at uvicorn cold boot). Reading the requirements file
# at probe time keeps the probe and pip-install target in lockstep.
hr "🔧 Ensuring Finlynq parser deps are installed"
if [ ! -x "$VENV_PY" ]; then
  printf '  ✗ missing venv at %s — create it: python -m venv .venv && .venv/bin/pip install -r services/rules-service/requirements.txt\n' "$VENV_PY"
  exit 1
fi
if [ -f "$FQ_DIR/requirements.txt" ]; then
  if "$VENV_PY" -c "
import importlib.metadata as md, re, sys
miss = []
try:
    with open('$FQ_DIR/requirements.txt', encoding='utf-8') as fp:
        for line in fp:
            line = line.split('#', 1)[0].strip()
            if not line or line.startswith('-'): continue
            # Strip specifiers + extras: ``python-jose[cryptography]==3.3.0``
            # -> ``python-jose``; ``-r foo.txt`` -> ``foo.txt`` (skip via the
            # ``-`` check above).
            pkg = re.split(r'[=<>!~;\[ ]', line, 1)[0].strip()
            if not pkg: continue
            try: md.version(pkg)
            except md.PackageNotFoundError: miss.append(pkg)
except FileNotFoundError:
    sys.exit(1)
sys.exit(0 if not miss else 1)
" 2>/dev/null; then
    note "finlynq deps : every requirements.txt package already importable — skipping pip install"
  else
    if ! "$VENV_PY" -m pip install -q -r "$FQ_DIR/requirements.txt" 2>"$LOG_PIP"; then
      printf '  ✗ pip install failed for Finlynq requirements — see %s\n' "$LOG_PIP"
      # cleanup-started-pids is a no-op here (none launched yet) but
      # keep the exit clean. Operator must run bootstrap.sh.
      exit 1
    fi
    note "finlynq deps : installed (was missing one or more)"
  fi
fi

# ----- Finlynq :8001 -------------------------------------------------------
# Canonical-store (Phase F4 ship target). The /health route is the readiness
# probe. Base.metadata.create_all + seed_default_categories run on the
# @app.on_event("startup") hook inside Finlynq's main.py so the first cold
# start populates the categories table without an external migration run.
#
# ``--reload`` watches $FQ_DIR (services/finlynq) for *.py changes and
# rebinds the worker without a manual bounce. Mirror of the BE block
# above: the watcher walks the CWD by default and ``cd "$FQ_DIR"``
# narrows it so UI saves do NOT trigger a Finlynq reload. The pidfile
# captures the watcher PID; ``stop.sh``'s ``kill_tree`` BFS walks the
# uvicorn-reload parent/child tree so SIGTERM still reaches the
# listener.
hr "🚀 Starting Finlynq   (uvicorn → :8001, --reload)"
cd "$FQ_DIR"
nohup "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 \
  --reload \
  > "$LOG_FQ" 2>&1 &
echo $! > "$PID_FQ"
FQ_PID=$(cat "$PID_FQ")
STARTED_PIDS+=("$FQ_PID")
note "pid  : $FQ_PID (uvicorn --reload watcher; worker is a child)"
note "log  : $LOG_FQ"

# ----- alembic upgrade head (Phase 27 regression fix) -------------------
# Phase 27 foot-gun: leaving migrations un-applied at boot landed the
# Settings UI in a "grey chip / no source column" state (the
# Migration J0a1b2c3d4e5 sat un-applied on a live DB and the merchant
# rules silently lost the `source` column). The fix is to RUN the
# migration on every boot — `alembic upgrade head` is idempotent
# (no-ops when the DB is already at head) so the cost is one SELECT
# against `alembic_version` per cold start, ~10ms.
#
# The bootstrap path ALSO calls this (see scripts/bootstrap.sh) so
# `bash scripts/bootstrap.sh && bash start.sh` is idempotent end-to-end.
hr "🔧 Applying alembic migrations"
if ! ( cd "$BE_DIR" && "$VENV_PY" -m alembic upgrade head 2>&1 | tee -a "$LOG_BE" ); then
  printf '  ✗ alembic upgrade head failed — see %s\n' "$LOG_BE"
  cleanup_started_pids
  exit 1
fi
note "alembic : $BE_DIR at head"

# ----- backend :8000 ------------------------------------------------------
# ``--reload`` watches $BE_DIR (services/rules-service) for *.py changes and
# rebinds the worker without a manual bounce. Without it, every route or
# schema edit lands as "tests pass but the browser still shows stale data"
# (the user-reported Phase 52+ debit/credit outage was exactly this gap).
# The watcher walks the CWD by default; ``cd "$BE_DIR"`` above narrows the
# watch to the rules-service tree so a UI save does NOT trigger a BE
# reload (which would race the FastAPI startup against the alembic gate).
# ``start.sh`` writes the WATCHER pid to ``.run/be.pid``; ``stop.sh``'s
# ``kill_tree BFS`` walks the worker children so SIGTERM still reaches
# the listener — verified compatible with the uvicorn-reload parent/child
# process layout.
hr "🚀 Starting Rules    (uvicorn → :8000, --reload)"
cd "$BE_DIR"
nohup "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  --reload \
  > "$LOG_BE" 2>&1 &
echo $! > "$PID_BE"
BE_PID=$(cat "$PID_BE")
STARTED_PIDS+=("$BE_PID")
note "pid  : $BE_PID (uvicorn --reload watcher; worker is a child)"
note "log  : $LOG_BE"

# ----- frontend :3000 -----------------------------------------------------
hr "🚀 Starting Frontend (next dev → :3000)"
cd "$UI_DIR"
nohup "$NEXT_BIN" dev -p 3000 -H 127.0.0.1 \
  > "$LOG_FE" 2>&1 &
echo $! > "$PID_FE"
FE_PID=$(cat "$PID_FE")
STARTED_PIDS+=("$FE_PID")
note "pid  : $FE_PID (initial; may be a wrapper — see status block)"
note "log  : $LOG_FE"

# ----- healthcheck (strict gate: must return 200 within 30s each) --------
hr "🩽️ Healthcheck"
# If any probe fails after the 30s budget, the gate below fires. Per-service
# rcs are tracked so the status block can label which side timed out (and
# so we don't claim "ready" next to an actual rc=1 exit).
fq_health_rc=0; be_health_rc=0; fe_health_rc=0
wait_for_health "http://localhost:8001/health" "Finlynq" "${START_FQ_TIMEOUT}" "$LOG_FQ" || fq_health_rc=$?
wait_for_health "http://localhost:8000/health" "Rules"    "${START_BE_TIMEOUT}" "$LOG_BE" || be_health_rc=$?
wait_for_health "http://localhost:3000/"        "UI"       "${START_FE_TIMEOUT}" "$LOG_FE" || fe_health_rc=$?
health_rc=$((fq_health_rc | be_health_rc | fe_health_rc))

# ----- resolve actual FE listener pid (next dev forks) --------------------
# $! from nohup is the next dev wrapper, not necessarily the port-binding
# child. Re-read the live listener so the Stop command below actually
# tears down the right process.
FE_LISTENER=$(lsof -ti:3000 2>/dev/null | head -1 | tr -d ' ' || true)
if [ -n "$FE_LISTENER" ] && [ "$FE_LISTENER" != "$FE_PID" ]; then
  printf '  • next dev forked: wrapper pid=%s → listener pid=%s (recorded)\n' "$FE_PID" "$FE_LISTENER"
  echo "$FE_LISTENER" > "$PID_FE"
  FE_PID="$FE_LISTENER"
elif [ -z "$FE_LISTENER" ]; then
  # wait_for_port 3000 just returned 2xx a moment ago — if the listener
  # is already gone, the FE crashed (OOM, watcher, etc.). Tell the user.
  printf '  ⚠️  FE listener disappeared after wait (port :3000 free) — see %s\n' "$LOG_FE"
fi

# ----- final status block -------------------------------------------------
hr "✨ Status"
# Re-probe (fresh) so the block reflects the *current* HTTP code, not the
# transient value seen during wait_for_port.
FQ_HTTP=$(http_probe "http://localhost:8001/health")
BE_HTTP=$(http_probe "http://localhost:8000/health")
FE_HTTP=$(http_probe "http://localhost:3000/")
fq_state='✓ up'; be_state='✓ up'; fe_state='✓ up'
case "$FQ_HTTP" in 200) ;; *) fq_state='✗ not 200' ;; esac
case "$BE_HTTP" in 200) ;; *) be_state='✗ not 200' ;; esac
case "$FE_HTTP" in 200) ;; *) fe_state='✗ not 200' ;; esac
# If the strict gate fired on this side, override the live-re-probe label
[ "$fq_health_rc" -ne 0 ] && fq_state='⏱ timeout'
[ "$be_health_rc" -ne 0 ] && be_state='⏱ timeout'
[ "$fe_health_rc" -ne 0 ] && fe_state='⏱ timeout'
# Status block column widths (lock alignment across all 3 rows):
#   "FQ (finlynq       :8001)" — "finlynq" + 7 spaces = 14 chars before :port
#   "BE (rules-service :8000)" — "rules-service" + 1 space = 14 chars before :port
#   "FE (next dev      :3000)" — "next dev" + 6 spaces = 14 chars before :port
# Each row emits 2 spaces + code + " (" + name + spaces + ":port)  pid=" ; the
# `pid=` column therefore lands at offset 30 for all three rows.
printf '  FQ (finlynq       :8001)  pid=%s   HTTP=%s   %s   log=%s\n' "$FQ_PID" "$FQ_HTTP" "$fq_state" "$LOG_FQ"
printf '  BE (rules-service :8000)  pid=%s   HTTP=%s   %s   log=%s\n' "$BE_PID" "$BE_HTTP" "$be_state" "$LOG_BE"
printf '  FE (next dev      :3000)  pid=%s   HTTP=%s   %s   log=%s\n' "$FE_PID" "$FE_HTTP" "$fe_state" "$LOG_FE"
printf '\n'
printf '  🌐 Open   : http://localhost:3000\n'
printf '  🩺 Health : http://localhost:8001/health (HTTP %s)   http://localhost:8000/health (HTTP %s)\n' "$FQ_HTTP" "$BE_HTTP"
printf '  📋 Tail   : tail -f %s %s %s\n' "$LOG_FQ" "$LOG_BE" "$LOG_FE"
printf '  🛑 Stop   : kill %s %s %s\n' "$FQ_PID" "$BE_PID" "$FE_PID"
printf '             (or just re-run ./start.sh — it will reap stale listeners)\n'

# ----- strict gate --------------------------------------------------------
# This is where we enforce "the script does not return until ALL THREE
# /health probes and the / probe return 200 within their respective budgets."
# If health_rc is non-zero, surface a failure banner + reap the
# already-started services so the user doesn't have to manually kill
# healthy orphans. Then exit non-zero so a CI caller sees the failure.
if [ "$health_rc" -ne 0 ]; then
  hr "❌ Not Ready — healthcheck failed (rc=$health_rc)"
  printf '  One or more services did not return HTTP 200 within their budget.\n'
  printf '  Healthcheck timeouts used: FQ=%ss  BE=%ss  FE=%ss\n' "$START_FQ_TIMEOUT" "$START_BE_TIMEOUT" "$START_FE_TIMEOUT"
  printf '  Failing side(s): '
  [ "$fq_health_rc" -ne 0 ] && printf 'FQ '
  [ "$be_health_rc" -ne 0 ] && printf 'BE '
  [ "$fe_health_rc" -ne 0 ] && printf 'FE '
  printf '\n'
  printf '  Reaping already-started services so you can re-run start.sh fresh:\n'
  cleanup_started_pids
  printf '  ✓ reap complete (or had nothing to do)\n'
  printf '\n'
  printf '  Diagnose with:\n'
  printf '    tail -f %s\n' "$LOG_FQ"
  printf '    tail -f %s\n' "$LOG_BE"
  printf '    tail -f %s\n' "$LOG_FE"
  printf '  Re-run ./start.sh (will reap stale listeners), or fix the\n'
  printf '  underlying failure and try again.\n'
  exit "$health_rc"
fi

hr "✨ Ready"

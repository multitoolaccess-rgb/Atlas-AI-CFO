#!/bin/bash
# Atlas AI CFO - development server startup.
#
# Runs the Atlas UI, Rules Service, and Finlynq using project-local .run/
# logs and pidfiles. Lifecycle ownership is verified by a process's working
# directory; generic executable names are never considered sufficient.

set -u

usage() {
  cat <<'EOF'
Usage: ./start.sh [--help|--check]

Start Atlas AI CFO development services.

Environment overrides:
  ATLAS_UI_PORT       UI port (default: 3333)
  ATLAS_RULES_PORT    Rules Service port (default: 8888)
  ATLAS_FINLYNQ_PORT  Finlynq port (default: 8889)

--check prints the resolved configuration without creating files, modifying
caches, installing dependencies, running migrations, or starting processes.
EOF
}

MODE=run
case "${1:-}" in
  '') ;;
  --help|-h) MODE=help ;;
  --check) MODE=check ;;
  *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
esac

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
BE_DIR="$PROJECT_ROOT/services/rules-service"
FQ_DIR="$PROJECT_ROOT/services/finlynq"
RUN_DIR="$PROJECT_ROOT/.run"
RULES_VENV_PY="$PROJECT_ROOT/.venv-rules/bin/python"
FINLYNQ_VENV_PY="$PROJECT_ROOT/.venv-finlynq/bin/python"
NEXT_BIN="$UI_DIR/node_modules/.bin/next"

: "${ATLAS_UI_PORT:=3333}"
: "${ATLAS_RULES_PORT:=8888}"
: "${ATLAS_FINLYNQ_PORT:=8889}"
: "${START_FQ_TIMEOUT:=30}" "${START_BE_TIMEOUT:=30}" "${START_FE_TIMEOUT:=30}"
export ATLAS_UI_PORT ATLAS_RULES_PORT ATLAS_FINLYNQ_PORT

valid_port() { [[ "$1" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$1" -le 65535 ]; }
for port_name in ATLAS_UI_PORT ATLAS_RULES_PORT ATLAS_FINLYNQ_PORT; do
  port_value=${!port_name}
  if ! valid_port "$port_value"; then
    printf '%s must be an integer between 1 and 65535 (got %s)\n' "$port_name" "$port_value" >&2
    exit 2
  fi
done

if [ "$MODE" = help ]; then
  usage
  exit 0
fi

if [ "$MODE" = check ]; then
  printf 'Atlas AI CFO lifecycle configuration (non-mutating)\n'
  printf '  root    : %s\n' "$PROJECT_ROOT"
  printf '  UI      : http://127.0.0.1:%s\n' "$ATLAS_UI_PORT"
  printf '  Rules   : http://127.0.0.1:%s\n' "$ATLAS_RULES_PORT"
  printf '  Finlynq : http://127.0.0.1:%s\n' "$ATLAS_FINLYNQ_PORT"
  printf '  run dir : %s\n' "$RUN_DIR"
  exit 0
fi

LOG_BE="$RUN_DIR/backend.log"
LOG_FE="$RUN_DIR/frontend.log"
LOG_FQ="$RUN_DIR/finlynq.log"
PID_BE="$RUN_DIR/be.pid"
PID_FE="$RUN_DIR/fe.pid"
PID_FQ="$RUN_DIR/fq.pid"
mkdir -p "$RUN_DIR"
STARTED_PIDS=()

hr() { printf '\n=== %s ===\n' "$1"; }
note() { printf '  • %s\n' "$1"; }

process_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1
}

# A process is Atlas-owned only when its current working directory is the
# resolved project root or one of its descendants. Command names such as
# uvicorn and next-server are shared by unrelated projects and are ignored.
atlas_pid_owner() {
  local pid=$1 cwd
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  cwd=$(process_cwd "$pid")
  [ "$cwd" = "$PROJECT_ROOT" ] || [[ "$cwd" == "$PROJECT_ROOT/"* ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# Snapshot before signaling so a terminating parent cannot reparent a child
# before it is discovered. Every candidate is independently CWD-verified; the
# resulting order is descendants first, then their verified parent.
ATLAS_TREE_PIDS=()
snapshot_atlas_tree() {
  local root_pid=$1 queue seen= node children pid index
  ATLAS_TREE_PIDS=()
  atlas_pid_owner "$root_pid" || return 1
  queue="$root_pid"
  while [ -n "$queue" ]; do
    node=${queue%% *}
    if [ "$node" = "$queue" ]; then queue=; else queue=${queue#* }; fi
    case " $seen " in *" $node "*) continue ;; esac
    seen="$seen $node"
    children=$(pgrep -P "$node" 2>/dev/null || true)
    [ -n "$children" ] && queue="${queue:+$queue }$children"
    atlas_pid_owner "$node" && ATLAS_TREE_PIDS+=("$node")
  done
  # Reverse breadth-first discovery so every verified child is signaled first.
  for ((index=0; index < ${#ATLAS_TREE_PIDS[@]} / 2; index++)); do
    pid=${ATLAS_TREE_PIDS[index]}
    ATLAS_TREE_PIDS[index]=${ATLAS_TREE_PIDS[${#ATLAS_TREE_PIDS[@]} - index - 1]}
    ATLAS_TREE_PIDS[${#ATLAS_TREE_PIDS[@]} - index - 1]=$pid
  done
  [ "${#ATLAS_TREE_PIDS[@]}" -gt 0 ]
}

signal_atlas_snapshot() {
  local signal=$1; shift
  local pid
  for pid in "$@"; do
    # Revalidation protects against PID reuse, especially before SIGKILL.
    atlas_pid_owner "$pid" && kill -"$signal" "$pid" 2>/dev/null || true
  done
}

kill_atlas_tree() {
  local signal=$1 root_pid=$2
  snapshot_atlas_tree "$root_pid" || return 1
  signal_atlas_snapshot "$signal" "${ATLAS_TREE_PIDS[@]}"
}

reap_port() {
  local port=$1 pids pid found=0
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  [ -z "$pids" ] && return 0
  for pid in $pids; do
    if atlas_pid_owner "$pid"; then
      printf '  ⚠ port :%s has stale Atlas pid=%s — stopping\n' "$port" "$pid"
      kill_atlas_tree KILL "$pid" || true
      found=1
    else
      printf '  ℹ port :%s has unrelated pid=%s — leaving alone\n' "$port" "$pid"
    fi
  done
  [ "$found" -eq 0 ] || sleep 1
}

cleanup_started_pids() {
  local pid
  local -a started_tree_pids=()
  for pid in "${STARTED_PIDS[@]}"; do
    if snapshot_atlas_tree "$pid"; then started_tree_pids+=("${ATLAS_TREE_PIDS[@]}"); fi
  done
  signal_atlas_snapshot TERM "${started_tree_pids[@]}"
  sleep 3
  signal_atlas_snapshot KILL "${started_tree_pids[@]}"
}

http_probe() {
  local code
  code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null)
  printf '%s' "${code:-000}"
}

wait_for_health() {
  local url=$1 label=$2 timeout=$3 log=$4 end code
  end=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$end" ]; do
    code=$(http_probe "$url")
    if [ "$code" = 200 ]; then
      printf '  ✓ %-12s %s ready (HTTP %s)\n' "$label" "$url" "$code"
      return 0
    fi
    sleep 1
  done
  printf '  ✗ %-12s %s did NOT return 200 within %ss — see %s\n' "$label" "$url" "$timeout" "$log"
  return 1
}

hr 'Atlas AI CFO — Dev Server (Finlynq + Rules + UI)'
note "root : $PROJECT_ROOT"
note "ports: UI=$ATLAS_UI_PORT Rules=$ATLAS_RULES_PORT Finlynq=$ATLAS_FINLYNQ_PORT"
if [ -f "$BE_DIR/.env" ]; then
  note "rules env: $BE_DIR/.env (service-relative configuration)"
else
  note "rules env: $BE_DIR/.env not found (server-only provider features may be unavailable)"
fi

if [ ! -d "$UI_DIR/node_modules" ]; then
  hr 'Installing ui/node_modules'
  (cd "$UI_DIR" && npm install) || exit 1
fi
[ -x "$NEXT_BIN" ] || { printf 'Missing %s\n' "$NEXT_BIN" >&2; exit 1; }
[ -x "$RULES_VENV_PY" ] || { printf 'Missing %s\n' "$RULES_VENV_PY" >&2; exit 1; }
[ -x "$FINLYNQ_VENV_PY" ] || { printf 'Missing %s\n' "$FINLYNQ_VENV_PY" >&2; exit 1; }

hr 'Cleaning Next.js cache'
rm -rf "$UI_DIR/.next" "$UI_DIR/node_modules/.cache"

hr 'Reaping stale Atlas listeners (if any)'
reap_port "$ATLAS_FINLYNQ_PORT"
reap_port "$ATLAS_RULES_PORT"
reap_port "$ATLAS_UI_PORT"

if [ -f "$BE_DIR/.env" ] && grep -q '^JWT_SECRET=' "$BE_DIR/.env"; then
  export JWT_SECRET
  JWT_SECRET=$(grep '^JWT_SECRET=' "$BE_DIR/.env" | head -1 | cut -d= -f2-)
fi
# The documented default is the shared Rules Service database. A caller may
# select a disposable restored clone only with the explicit synthetic-acceptance
# gate; ordinary startup never accepts an arbitrary database override.
if [ "${ATLAS_SYNTHETIC_ACCEPTANCE:-0}" = "1" ] && [ -n "${DATABASE_URL:-}" ]; then
  export DATABASE_URL
else
  export DATABASE_URL="sqlite:///$BE_DIR/finance.db"
fi

hr "Starting Finlynq (uvicorn → :$ATLAS_FINLYNQ_PORT)"
# Keep one stable service process per PID file. Uvicorn's reload supervisor
# previously outlived/respawned the recorded child during detached local
# startup, so health could pass once and then authenticated readiness would
# lose its listener. File watching is an explicit developer choice outside
# the supported Atlas lifecycle; this path owns the actual server PID.
(cd "$FQ_DIR" && nohup "$FINLYNQ_VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$ATLAS_FINLYNQ_PORT" </dev/null >"$LOG_FQ" 2>&1 & echo $! >"$PID_FQ")
FQ_PID=$(<"$PID_FQ"); STARTED_PIDS+=("$FQ_PID")

# Schema migrations are intentionally an explicit operator action. In
# particular, starting Atlas must never apply an unmerged Phase 3 migration.
hr "Starting Rules Service (uvicorn → :$ATLAS_RULES_PORT)"
(cd "$BE_DIR" && FINLYNQ_BASE_URL="http://127.0.0.1:$ATLAS_FINLYNQ_PORT" nohup "$RULES_VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$ATLAS_RULES_PORT" </dev/null >"$LOG_BE" 2>&1 & echo $! >"$PID_BE")
BE_PID=$(<"$PID_BE"); STARTED_PIDS+=("$BE_PID")

hr "Starting Atlas UI (next dev → :$ATLAS_UI_PORT)"
(cd "$UI_DIR" && NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$ATLAS_RULES_PORT" nohup "$NEXT_BIN" dev -p "$ATLAS_UI_PORT" -H 127.0.0.1 >"$LOG_FE" 2>&1 & echo $! >"$PID_FE")
FE_PID=$(<"$PID_FE"); STARTED_PIDS+=("$FE_PID")

hr 'Healthcheck'
fq_health_rc=0; be_health_rc=0; fe_health_rc=0
wait_for_health "http://127.0.0.1:$ATLAS_FINLYNQ_PORT/health" Finlynq "$START_FQ_TIMEOUT" "$LOG_FQ" || fq_health_rc=$?
wait_for_health "http://127.0.0.1:$ATLAS_RULES_PORT/health" Rules "$START_BE_TIMEOUT" "$LOG_BE" || be_health_rc=$?
wait_for_health "http://127.0.0.1:$ATLAS_UI_PORT/" UI "$START_FE_TIMEOUT" "$LOG_FE" || fe_health_rc=$?
health_rc=$((fq_health_rc | be_health_rc | fe_health_rc))

FE_LISTENER=$(lsof -ti:"$ATLAS_UI_PORT" 2>/dev/null | head -1 | tr -d ' ' || true)
if [ -n "$FE_LISTENER" ] && atlas_pid_owner "$FE_LISTENER" && [ "$FE_LISTENER" != "$FE_PID" ]; then
  printf '%s\n' "$FE_LISTENER" >"$PID_FE"
  FE_PID=$FE_LISTENER
fi

FQ_HTTP=$(http_probe "http://127.0.0.1:$ATLAS_FINLYNQ_PORT/health")
BE_HTTP=$(http_probe "http://127.0.0.1:$ATLAS_RULES_PORT/health")
FE_HTTP=$(http_probe "http://127.0.0.1:$ATLAS_UI_PORT/")
hr 'Status'
printf '  FQ (finlynq       :%s) pid=%s HTTP=%s log=%s\n' "$ATLAS_FINLYNQ_PORT" "$FQ_PID" "$FQ_HTTP" "$LOG_FQ"
printf '  BE (rules-service :%s) pid=%s HTTP=%s log=%s\n' "$ATLAS_RULES_PORT" "$BE_PID" "$BE_HTTP" "$LOG_BE"
printf '  FE (Atlas UI      :%s) pid=%s HTTP=%s log=%s\n' "$ATLAS_UI_PORT" "$FE_PID" "$FE_HTTP" "$LOG_FE"
printf '  Open: http://127.0.0.1:%s\n' "$ATLAS_UI_PORT"

if [ "$health_rc" -ne 0 ]; then
  cleanup_started_pids
  exit "$health_rc"
fi
hr 'Atlas AI CFO ready'

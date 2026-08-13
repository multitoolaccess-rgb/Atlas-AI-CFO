#!/bin/bash
# Atlas AI CFO - development server stop wrapper.

set -u

usage() {
  cat <<'EOF'
Usage: ./stop.sh [--help|--check]

Stop Atlas AI CFO development processes recorded in this project's .run/.
The process working directory must be this Atlas project before any signal is
sent. Generic process names are never trusted.

Environment overrides:
  ATLAS_UI_PORT       UI port (default: 3333)
  ATLAS_RULES_PORT    Rules Service port (default: 8888)
  ATLAS_FINLYNQ_PORT  Finlynq port (default: 8889)
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
RUN_DIR="$PROJECT_ROOT/.run"
: "${ATLAS_UI_PORT:=3333}"
: "${ATLAS_RULES_PORT:=8888}"
: "${ATLAS_FINLYNQ_PORT:=8889}"
: "${STOP_GRACE_SECONDS:=5}"

valid_port() { [[ "$1" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$1" -le 65535 ]; }
for port_name in ATLAS_UI_PORT ATLAS_RULES_PORT ATLAS_FINLYNQ_PORT; do
  valid_port "${!port_name}" || { printf '%s must be an integer between 1 and 65535\n' "$port_name" >&2; exit 2; }
done

if [ "$MODE" = help ]; then usage; exit 0; fi
if [ "$MODE" = check ]; then
  printf 'Atlas AI CFO lifecycle stop configuration (non-mutating)\n'
  printf '  UI=%s Rules=%s Finlynq=%s\n' "$ATLAS_UI_PORT" "$ATLAS_RULES_PORT" "$ATLAS_FINLYNQ_PORT"
  printf '  run dir: %s\n' "$RUN_DIR"
  exit 0
fi

PID_FQ="$RUN_DIR/fq.pid"; PID_BE="$RUN_DIR/be.pid"; PID_FE="$RUN_DIR/fe.pid"
LOG_FQ="$RUN_DIR/finlynq.log"; LOG_BE="$RUN_DIR/backend.log"; LOG_FE="$RUN_DIR/frontend.log"
hr() { printf '\n=== %s ===\n' "$1"; }
note() { printf '  • %s\n' "$1"; }

process_cwd() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1; }
atlas_pid_owner() {
  local pid=$1 cwd
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  cwd=$(process_cwd "$pid")
  [ "$cwd" = "$PROJECT_ROOT" ] || [[ "$cwd" == "$PROJECT_ROOT/"* ]] || return 1
  kill -0 "$pid" 2>/dev/null
}
ATLAS_TREE_PIDS=()
snapshot_atlas_tree() {
  local root_pid=$1 queue= seen= node children pid index
  ATLAS_TREE_PIDS=()
  atlas_pid_owner "$root_pid" || return 1
  queue=$root_pid
  while [ -n "$queue" ]; do
    node=${queue%% *}
    if [ "$node" = "$queue" ]; then queue=; else queue=${queue#* }; fi
    case " $seen " in *" $node "*) continue ;; esac
    seen="$seen $node"
    children=$(pgrep -P "$node" 2>/dev/null || true)
    [ -n "$children" ] && queue="${queue:+$queue }$children"
    atlas_pid_owner "$node" && ATLAS_TREE_PIDS+=("$node")
  done
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
    atlas_pid_owner "$pid" && kill -"$signal" "$pid" 2>/dev/null || true
  done
}
graceful_kill() {
  local label=$1 pid=$2 end
  local -a pid_tree=()
  if ! snapshot_atlas_tree "$pid"; then
    note "$label : pid ${pid:-'(missing)'} is absent or not Atlas-owned — refusing to signal"
    return 0
  fi
  pid_tree=("${ATLAS_TREE_PIDS[@]}")
  note "$label : SIGTERM pid=$pid (verified Atlas process tree)"
  signal_atlas_snapshot TERM "${pid_tree[@]}"
  end=$((SECONDS + STOP_GRACE_SECONDS))
  while [ "$SECONDS" -lt "$end" ]; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 1
  done
  if atlas_pid_owner "$pid"; then
    note "$label : grace expired; SIGKILL verified Atlas process tree"
    signal_atlas_snapshot KILL "${pid_tree[@]}"
  fi
}
port_state() {
  local port=$1 pid
  pid=$(lsof -ti:"$port" 2>/dev/null | head -1 | tr -d ' ' || true)
  [ -z "$pid" ] && { printf '✓ stopped'; return; }
  if atlas_pid_owner "$pid"; then printf '✗ Atlas listener (pid=%s)' "$pid"; else printf 'ℹ unrelated listener (pid=%s)' "$pid"; fi
}

FQ_PID=$(cat "$PID_FQ" 2>/dev/null || true)
BE_PID=$(cat "$PID_BE" 2>/dev/null || true)
FE_PID=$(cat "$PID_FE" 2>/dev/null || true)
hr 'Atlas AI CFO — Stop'
graceful_kill Finlynq "$FQ_PID"
graceful_kill Rules "$BE_PID"
graceful_kill 'Atlas UI' "$FE_PID"
hr Status
printf '  FQ (finlynq       :%s) %s log=%s\n' "$ATLAS_FINLYNQ_PORT" "$(port_state "$ATLAS_FINLYNQ_PORT")" "$LOG_FQ"
printf '  BE (rules-service :%s) %s log=%s\n' "$ATLAS_RULES_PORT" "$(port_state "$ATLAS_RULES_PORT")" "$LOG_BE"
printf '  FE (Atlas UI      :%s) %s log=%s\n' "$ATLAS_UI_PORT" "$(port_state "$ATLAS_UI_PORT")" "$LOG_FE"
printf '  Reload: ./start.sh\n'
hr 'Atlas AI CFO stopped'

#!/bin/bash
# Atlas - Stop Wrapper
# --------------------
# Companion to ``start.sh``. Reads ``.run/{be.pid,fe.pid}``, sends
# SIGTERM to the process tree (so ``next dev``'s listener child is
# also reaped via a child-walk), waits ``$STOP_GRACE_SECONDS``
# (default 5 s), escalates to SIGKILL on any survivor, then prints a
# status block mirroring
# ``start.sh`` so the dev always sees the same diagnostic format.
#
# Stop:
#   ./stop.sh
#   STOP_GRACE_SECONDS=15 ./stop.sh     # longer grace (slow CI boxes)
#
# Status block layout mirrors ``start.sh`` so terminal scrollback reads
# the same way stop → start → stop. Idempotent: re-running on an
# already-stopped system is a no-op success; missing pidfile ⇒ banner
# "already gone" rather than a hard exit. Defensive: refuses to kill
# a PID whose cmdline does not match this project (finance-copilot /
# rules-service / uvicorn / next-server / "next dev") — same pattern
# as ``start.sh::reap_port``.

set -u  # do NOT use -e: graceful_kill has its own error semantics

: "${STOP_GRACE_SECONDS:=5}"

# Match start.sh exactly. Empty, privileged, nonnumeric, and duplicate ports
# are rejected before this script reads a PID file or signals a process.
ATLAS_UI_PORT="${ATLAS_UI_PORT-3333}"
ATLAS_RULES_PORT="${ATLAS_RULES_PORT-8888}"
ATLAS_FINLYNQ_PORT="${ATLAS_FINLYNQ_PORT-8889}"

validate_port() {
  local name=$1 value=$2
  if [[ ! "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1024 ] || [ "$value" -gt 65535 ]; then
    printf '  ✗ %s must be a non-privileged numeric TCP port (1024-65535); got %q\n' "$name" "$value"
    exit 2
  fi
}

validate_port "ATLAS_UI_PORT" "$ATLAS_UI_PORT"
validate_port "ATLAS_RULES_PORT" "$ATLAS_RULES_PORT"
validate_port "ATLAS_FINLYNQ_PORT" "$ATLAS_FINLYNQ_PORT"
if [ "$ATLAS_UI_PORT" = "$ATLAS_RULES_PORT" ] || [ "$ATLAS_UI_PORT" = "$ATLAS_FINLYNQ_PORT" ] || [ "$ATLAS_RULES_PORT" = "$ATLAS_FINLYNQ_PORT" ]; then
  printf '  ✗ ATLAS_UI_PORT, ATLAS_RULES_PORT, and ATLAS_FINLYNQ_PORT must be distinct\n'
  exit 2
fi

# ----- paths --------------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_BE="$RUN_DIR/backend.log"
LOG_FE="$RUN_DIR/frontend.log"
LOG_FQ="$RUN_DIR/finlynq.log"
PID_BE="$RUN_DIR/be.pid"
PID_FE="$RUN_DIR/fe.pid"
PID_FQ="$RUN_DIR/fq.pid"

# ----- helpers (same shape as start.sh) ----------------------------------
hr()   { printf '\n=== %s ===\n' "$1"; }
note() { printf '  • %s\n' "$1"; }

# Confirm a pidfile owner is actually an Atlas development server before we
# touch it. macOS process command lines omit the checkout/virtualenv path for
# uvicorn and next-server children, so use the process CWD as the ownership
# proof, then require an expected development-server command shape.
project_pid_owner() {
  local pid=$1
  # Guard against [ -z ] missing AND pid=0 (``kill -0 0`` would signal
  # the calling shell's process group on Unix — never what we want).
  [ -z "$pid" ] && return 1
  [ "$pid" = "0" ] && return 1
  # ``kill -0`` first: returns 1 if the pid is GONE (so we don't try
  # to inspect a process that's already dead).
  kill -0 "$pid" 2>/dev/null || return 1
  local cwd cmd
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
  case "$cwd" in "$PROJECT_ROOT"/*) ;; *) return 1 ;; esac
  cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
  case "$cmd" in
    *"-m uvicorn app.main:app"*|*next-server*|"next dev"*) return 0 ;;
    *) return 1 ;;
  esac
}

# Walk the process tree rooted at $pid and signal every descendant.
# We intentionally avoid Unix process-group semantics (negative-pid
# kill via ``kill -SIG -PID``) because that has interop quirks on
# macOS bash — the negative-pid form is unreliable across systems
# (probed empirically: SIGKILL via ``kill -KILL -PID`` left the
# listener bound). Instead we enumerate children of $pid with
# ``pgrep -P`` and recurse, which is deterministic on every Unix.
kill_tree() {
  local sig=$1 pid=$2
  # ``pid=0`` would signal the calling shell's process group via
  # ``kill -SIG 0`` — explicit guard so a malformed pidfile can
  # never reach that path.
  [ -z "$pid" ] && return 0
  [ "$pid" = "0" ] && return 0
  if ! kill -0 "$pid" 2>/dev/null; then return 0; fi

  # BFS through descendants of $pid.
  local wave="$pid"
  while [ -n "$wave" ]; do
    # Signal everyone in the current wave first.
    for node in $wave; do
      kill -"$sig" "$node" 2>/dev/null || true
    done
    # Then collect children of the current wave for the next iteration.
    local next_wave=
    for node in $wave; do
      local children
      children=$(pgrep -P "$node" 2>/dev/null || true)
      [ -n "$children" ] && next_wave="$next_wave $children"
    done
    wave="$next_wave"
  done
}

# SIGTERM → wait grace → escalate survivors to SIGKILL. ``label`` is
# only used in the bullet output so the diagnostic reads naturally.
# Defensive: refuses to invoke ``kill -0`` (or any signal) on pid=0 —
# ``kill -0 0`` is a permission test that addresses the calling shell's
# own process group on Unix, so a malformed pidfile containing ``0``
# must never reach the liveness check below.
graceful_kill() {
  local label=$1 pid=$2
  if [ -z "$pid" ]; then
    note "$label : pidfile missing/empty — already gone"
    return 0
  fi
  if [ "$pid" = "0" ]; then
    # ``kill -SIG 0`` targets the calling shell's own process group on
    # Unix — a malformed pidfile ``0`` must never reach ``kill -0``.
    note "$label : pidfile contains 0 — refusing (kill -SIG 0 addresses the calling shell's own process group)"
    return 1
  fi
  # Liveness check FIRST so a dead-but-our-own pidfile short-circuits
  # with the original ``already gone`` semantics. The cmdline allow-list
  # check (``project_pid_owner``) can only run on PIDs that are still
  # alive — otherwise ``ps -p`` returns empty for a dead PID, which
  # the case-statement would mis-classify as ``NOT this project``.
  if ! kill -0 "$pid" 2>/dev/null; then
    note "$label : pid $pid not alive — already gone"
    return 0
  fi
  if ! project_pid_owner "$pid"; then
    note "$label : pid $pid is NOT this project (refusing to kill)"
    return 1
  fi
  note "$label : SIGTERM  pid=$pid (process tree)"
  kill_tree TERM "$pid"
  local end=$((SECONDS + STOP_GRACE_SECONDS))
  while [ $SECONDS -lt $end ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      note "$label : exited gracefully within ${STOP_GRACE_SECONDS}s"
      return 0
    fi
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    note "$label : grace expired, escalating to SIGKILL (pid=$pid, process tree)"
    kill_tree KILL "$pid"
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      note "$label : STILL alive after SIGKILL — manual intervention needed"
      return 1
    fi
    note "$label : killed after SIGKILL"
  fi
  return 0
}

# ----- intro --------------------------------------------------------------
hr "🛑 Atlas — Stop"
note "grace window  : ${STOP_GRACE_SECONDS}s (override with STOP_GRACE_SECONDS=N)"
note "log dir       : $RUN_DIR"
BE_PID=$(cat "$PID_BE" 2>/dev/null || true)
FE_PID=$(cat "$PID_FE" 2>/dev/null || true)
FQ_PID=$(cat "$PID_FQ" 2>/dev/null || true)
[ -n "$BE_PID" ] && note "be.pid record : $BE_PID" || note "be.pid record : (missing)"
[ -n "$FE_PID" ] && note "fe.pid record : $FE_PID" || note "fe.pid record : (missing)"
[ -n "$FQ_PID" ] && note "fq.pid record : $FQ_PID" || note "fq.pid record : (missing)"

# ----- terminate Finlynq, BE, then FE ------------------------------------
# Symmetry with start.sh, which now launches THREE services (Finlynq
# configured Finlynq + Rules + Next dev ports). Dropping FQ from stop.sh would
# leave its configured port squatting on a stale pid file until the next start.sh's
# ``reap_port`` block clears it. Order is intentional: Finlynq first
# (it owns the rules-service schema cache), then BE, then FE.
graceful_kill "FQ" "$FQ_PID" || true
graceful_kill "BE" "$BE_PID" || true
graceful_kill "FE" "$FE_PID" || true

# ----- status block (mirrors start.sh) ------------------------------------
hr "🛟 Status"
# Verify the port-side state by checking real listeners. If something
# else is squatting on a configured Atlas port, we surface it but do NOT kill it
# (out of scope for stop.sh — start.sh::reap_port handles that).
port_state() {
  local port=$1
  if ! lsof -ti:"$port" >/dev/null 2>&1; then
    printf '✓ stopped'
  else
    printf '✗ still listening (pid=%s)' "$(lsof -ti:"$port" | head -1 | tr -d ' ')"
  fi
}
# As probe for Finlynq's port too so the status block mirrors start.sh.
fq_state=$(port_state "$ATLAS_FINLYNQ_PORT")
be_state=$(port_state "$ATLAS_RULES_PORT")
fe_state=$(port_state "$ATLAS_UI_PORT")
printf '  FQ (finlynq       :%s)  pid=%-6s  %s   log=%s\n' "$ATLAS_FINLYNQ_PORT" "${FQ_PID:-—}" "$fq_state" "$LOG_FQ"
printf '  BE (rules-service :%s)  pid=%-6s  %s   log=%s\n' "$ATLAS_RULES_PORT" "${BE_PID:-—}" "$be_state" "$LOG_BE"
printf '  FE (next dev      :%s)  pid=%-6s  %s   log=%s\n' "$ATLAS_UI_PORT" "${FE_PID:-—}" "$fe_state" "$LOG_FE"
printf '\n'
printf '  🌐 Reload : ./start.sh\n'  printf '  📋 Tail   : tail -f %s %s %s\n' "$LOG_FQ" "$LOG_FE" "$LOG_BE"
printf '  ⚠️  Note  : pidfiles are NOT removed — re-run ./start.sh to reuse them\n'
hr "✨ Done"

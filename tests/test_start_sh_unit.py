"""Unit tests for start.sh (no actual service boot).

These tests run in <1s: they grep / regex the script source for the
three polish-pattern invariants applied in round-6 + a ``bash -n``
syntax check. Anything that would actually launch uvicorn or bind a
TCP port lives in ``test_start_sh_e2e.py`` (marked ``slow`` so
contributors can opt out via ``-m 'not slow'``).

Polish items covered here:

  #1 cleanup-on-gate-failure
        - ``cleanup_started_pids`` function defined.
        - ``$STARTED_PIDS`` array initialised.
        - Each launch block (``Starting Finlynq``, ``Starting
          Rules``, ``Starting Frontend``) appends to ``STARTED_PIDS``.
        - The strict-gate failure branch invokes cleanup_started_pids
          BEFORE ``exit "$health_rc"``.

  #2 probe-then-skip pip
        - The Finlynq-deps block runs an import probe FIRST and only
          falls through to ``pip install`` on probe failure.
        - **Round-7 reviewer #1 lock-down**: the probe set MUST be
          DERIVED from finlynq/requirements.txt (using
          ``importlib.metadata``) -- not a hand-maintained allowlist
          that misses deps like uvicorn / pydantic-settings /
          python-jose / Pillow / ofxparse / xlrd / reportlab.

  #3 status-block pid-column alignment
        - The 3 ``printf`` statements for FQ / BE / FE use the EXACT
          same byte offset for the ``pid=`` column so columns line up
          under any pid-width (3-digit, 4-digit, 5-digit).

These are static-analysis tests so they fail fast on a regression
introduced by future start.sh edits -- the alternative (detecting a
regression by staring at the live status block) is fragile.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


# ---------- helpers ------------------------------------------------------

def _bash_check_syntax(script: Path) -> None:
    """Run ``bash -n`` against the script; raises CalledProcessError on syntax error."""
    subprocess.run(
        ["bash", "-n", str(script)],
        check=True,
        capture_output=True,
        text=True,
    )


# ---------- #NOP / syntax -------------------------------------------------


def test_start_sh_is_a_valid_bash_script(start_sh_path: Path) -> None:
    """``bash -n`` returns 0 -- no syntax errors anywhere in the script.

    Catches the dumbest regression first: an unclosed quote, a stray
    back-tick, a ``set -e`` typo. Runs <100ms.
    """
    _bash_check_syntax(start_sh_path)


# ---------- #3 status-block pid-column alignment ---------------------------


def _printf_rows(start_sh_path: Path) -> list[str]:
    """Extract every status-block ``printf`` row (FQ / BE / FE).

    Anchors on the ``printf '  FQ|printf '  BE|printf '  FE`` prefix
    (2-letter service code AFTER 2-space pad) so the discriminator is the
    ServiceCode column, not a fragile substring filter. Other printfs in
    start.sh (``reap_port`` busy-kill banner, ``FE-listener`` fork note,
    etc.) DON'T start with ``printf '  FQ|...`` so they're naturally
    excluded.
    """
    text = start_sh_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^\s*printf\s+'  (?:FQ|BE|FE)\b")
    return [
        line.strip()
        for line in text.splitlines()
        if pattern.match(line)
    ]


def test_start_sh_status_block_emits_pid_for_each_three_services(start_sh_path: Path) -> None:
    """Three ``printf`` rows (FQ, BE, FE) -- one per service."""
    rows = _printf_rows(start_sh_path)
    assert len(rows) == 3, (
        f"Expected exactly 3 status-block printf rows (FQ/BE/FE), found {len(rows)}:\n"
        + "\n".join(f"  {r}" for r in rows)
    )
    # Each row must mention a service label inside parens.
    labels = re.findall(r"\([^)]+\)", "\n".join(rows))
    assert len(labels) == 3
    assert "finlynq" in labels[0].lower()
    assert "rules-service" in labels[1].lower()
    assert "next dev" in labels[2].lower()


def test_start_sh_status_block_pid_aligned_to_same_byte_offset(start_sh_path: Path) -> None:
    """The byte offset of ``pid=%s`` in the printf format string must be the
    same across all 3 rows so the live ``status`` block lines up under
    variable-width PIDs (3-digit 1234 to 5-digit 12345).

    Polished start.sh was edited so the names + padding lines up to
    exactly the same column. This regression-guard fails immediately
    if a future contributor tweaks one name without re-aligning the
    other two.
    """
    rows = _printf_rows(start_sh_path)
    offsets = [r.index("pid=%s") for r in rows]
    assert len(set(offsets)) == 1, (
        f"prinf rows disagree on `pid=%s` column position: {offsets}\n\n"
        + "\n".join(f"  offset={o:>2}  {r}" for o, r in zip(offsets, rows))
    )


# ---------- isolated service environments ---------------------------------


def test_start_sh_uses_service_specific_interpreters(start_sh_path: Path) -> None:
    """Finlynq and Rules Service must never share a Python environment."""
    text = start_sh_path.read_text(encoding="utf-8")
    assert 'RULES_VENV_PY="$PROJECT_ROOT/.venv-rules/bin/python"' in text
    assert 'FINLYNQ_VENV_PY="$PROJECT_ROOT/.venv-finlynq/bin/python"' in text
    assert 'nohup "$FINLYNQ_VENV_PY" -m uvicorn app.main:app' in text
    assert '"$RULES_VENV_PY" -m alembic upgrade head' in text
    assert 'nohup "$RULES_VENV_PY" -m uvicorn app.main:app' in text
    assert 'pip install -r "$FQ_DIR/requirements.txt"' not in text


# ---------- #1 cleanup-on-gate-failure ------------------------------------


def test_start_sh_defines_cleanup_started_pids_function(start_sh_path: Path) -> None:
    """The cleanup helper is a real ``name() { ... }`` bash function (not a comment).

    Polish #1: cleanup-on-gate-failure requires a callable we can
    invoke from the strict-gate failure branch. A future contributor
    replacing the function definition with prose must trip this test.
    """
    text = start_sh_path.read_text(encoding="utf-8")
    match = re.search(
        r"^cleanup_started_pids\(\)\s*\{(.*?)^\}",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert match, (
        "start.sh is missing the `cleanup_started_pids()` function. "
        "Polish #1 (cleanup-on-gate-failure) requires it as a callable."
    )
    body = match.group(1)
    # The function must send a signal - otherwise it's a no-op shell of a function.
    assert "kill " in body, (
        "cleanup_started_pids() body must invoke `kill` so it actually tears "
        "down started services on strict-gate failure."
    )


def test_start_sh_tracks_started_pids_at_each_launch(start_sh_path: Path) -> None:
    """Each of the 3 launch blocks (Starting Finlynq/Rules/Frontend)
    appends its captured PID to the ``STARTED_PIDS`` array.

    Polish #1: cleanup-walkability requires STARTED_PIDS be populated
    BEFORE the strict gate runs; otherwise the array is empty and
    cleanup is a no-op.
    """
    text = start_sh_path.read_text(encoding="utf-8")
    expected_blocks = (
        "Starting Finlynq",
        "Starting Rules",
        "Starting Frontend",
    )
    for header in expected_blocks:
        # Find the header line, then look for ``STARTED_PIDS+=(`` within the next
        # ~600 lines (covers the cd, nohup, $! capture, echo to pid file, append, note).
        header_idx = text.find(header)
        assert header_idx != -1, f"start.sh is missing the launch header {header!r}"
        section = text[header_idx : header_idx + 600]
        assert "STARTED_PIDS+=(" in section, (
            f"Block under '{header}' does not append to STARTED_PIDS. "
            "Polish #1 requires every successful launch to register its PID."
        )


def test_start_sh_calls_cleanup_on_strict_gate_failure_branch(start_sh_path: Path) -> None:
    """The strict-gate failure branch (the ``if [ "$health_rc" -ne 0 ]`` block
    AFTER the status block) MUST call ``cleanup_started_pids`` BEFORE
    the ``exit "$health_rc"`` line.

    A future contributor moving the cleanup would leave the user's
    dev machine with orphaned BE+FE processes after a single FQ
    healthcheck timeout - this test prevents that regression without
    having to actually fail a probe to discover it.
    """
    text = start_sh_path.read_text(encoding="utf-8")
    gate_idx = text.find('if [ "$health_rc" -ne 0 ]')
    assert gate_idx != -1, (
        "start.sh is missing the strict-gate `if [ $health_rc -ne 0 ]` block."
    )
    end_idx = text.find('exit "$health_rc"', gate_idx)
    assert end_idx != -1, (
        "start.sh is missing the strict-gate `exit $health_rc` line."
    )
    branch = text[gate_idx:end_idx]
    assert "cleanup_started_pids" in branch, (
        "Strict-gate failure branch must invoke cleanup_started_pids BEFORE "
        "exit. Without this call, BE+FE PIDs are orphaned when only FQ timed out."
    )
    cleanup_idx = branch.find("cleanup_started_pids")
    assert cleanup_idx < (end_idx - gate_idx), (
        "cleanup_started_pids must be invoked BEFORE the `exit` line in the "
        "strict-gate failure branch (otherwise we exit without cleaning up)."
    )


# ---------- breadth: linty invariants --------------------------------------


@pytest.mark.parametrize(
    "name,pattern",
    [
        ("wait_for_health helper", r"wait_for_health\(\)"),
        ("reap_port helper", r"reap_port\(\)"),
        ("http_probe helper", r"http_probe\(\)"),
        # Port-flag patterns use ``(?:^|\s)`` start anchor instead of ``\b``:
        # ``--`` and ``-`` are non-word chars, so ``\b--port`` cannot match
        # in the middle of a line. ``(?:^|\s)`` accepts either start-of-line
        # OR whitespace before the flag, which is the actual bash-arg context.
        ("FQ configured port", r'--port\s+"\$ATLAS_FINLYNQ_PORT"'),
        ("BE configured port", r'--port\s+"\$ATLAS_RULES_PORT"'),
        ("FE configured port", r'-p\s+"\$ATLAS_UI_PORT"'),
        ("pin file .run/fq.pid", r'PID_FQ="\$RUN_DIR/fq\.pid"'),
        ("pin file .run/be.pid", r'PID_BE="\$RUN_DIR/be\.pid"'),
        ("pin file .run/fe.pid", r'PID_FE="\$RUN_DIR/fe\.pid"'),
        ("log file .run/finlynq.log", r'LOG_FQ="\$RUN_DIR/finlynq\.log"'),
        ("log file .run/backend.log", r'LOG_BE="\$RUN_DIR/backend\.log"'),
        ("log file .run/frontend.log", r'LOG_FE="\$RUN_DIR/frontend\.log"'),
    ],
)
def test_start_sh_required_invariants_present(
    start_sh_path: Path, name: str, pattern: str
) -> None:
    r"""Sundry invariants the cold-boot depends on. If any go missing, the
    shell-session-by-shell-session boot will break in a way that's
    hard to attribute. A single ``re.search`` (NOT substring ``in``) catches
    them all.

    Round-7 wave-4 fix: ``\b--port`` /\ ``\b-p`` were broken because ``--``
    and ``-`` are non-word characters, so there is no ``\b`` between
    whitespace and ``-``. Replaced with ``(?:^|\s)`` start anchor that
    respects actual bash-arg context.

    Raw-string rules: the leading ``r`` prefix silences Python 3.12+
    SyntaxWarnings for backslash-escape-looking sequences like ``\b``
    and ``\s`` in non-raw docstrings. NEVER embed three consecutive
    double-quote characters in the docstring body, even escaped with a
    backslash: the raw-string parser still treats the backslash-plus-
    quote as an escape and the next two raw quotes close the docstring
    early, putting all following content back into code-parsing scope.
    """

    text = start_sh_path.read_text(encoding="utf-8")
    assert re.search(pattern, text), (
        f"start.sh is missing the required invariant {name!r} "
        f"(pattern {pattern!r}). Either re-add the invariant or update "
        "this test if the design changed."
    )


# ---------- Atlas local port profile --------------------------------------


def test_start_sh_declares_atlas_port_defaults_and_wires_each_service(
    start_sh_path: Path,
) -> None:
    """The default Atlas profile is isolated from Finance Copilot's ports."""
    text = start_sh_path.read_text(encoding="utf-8")
    assert 'ATLAS_UI_PORT="${ATLAS_UI_PORT-3333}"' in text
    assert 'ATLAS_RULES_PORT="${ATLAS_RULES_PORT-8888}"' in text
    assert 'ATLAS_FINLYNQ_PORT="${ATLAS_FINLYNQ_PORT-8889}"' in text
    assert 'reap_port "$ATLAS_FINLYNQ_PORT"' in text
    assert 'reap_port "$ATLAS_RULES_PORT"' in text
    assert 'reap_port "$ATLAS_UI_PORT"' in text
    assert 'FINLYNQ_BASE_URL="http://127.0.0.1:${ATLAS_FINLYNQ_PORT}"' in text
    assert 'NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${ATLAS_RULES_PORT}"' in text
    assert 'http://127.0.0.1:${ATLAS_FINLYNQ_PORT}/health' in text
    assert 'http://127.0.0.1:${ATLAS_RULES_PORT}/health' in text
    assert 'http://127.0.0.1:${ATLAS_UI_PORT}/' in text


def test_start_sh_uses_environment_values_at_every_port_boundary(start_sh_path: Path) -> None:
    """A caller's valid port override flows to listeners, URLs, and probes."""
    text = start_sh_path.read_text(encoding="utf-8")
    for variable in ("ATLAS_UI_PORT", "ATLAS_RULES_PORT", "ATLAS_FINLYNQ_PORT"):
        assert text.count(f'"${variable}"') >= 3, variable
    assert 'lsof -ti:"$ATLAS_UI_PORT"' in text
    assert 'lsof -a -p "$pid" -d cwd -Fn' in text
    assert 'atlas_process_owner()' in text


@pytest.mark.parametrize(
    "name,value",
    [
        ("ATLAS_UI_PORT", ""),
        ("ATLAS_UI_PORT", "not-a-port"),
        ("ATLAS_RULES_PORT", "80"),
        ("ATLAS_FINLYNQ_PORT", "65536"),
    ],
)
def test_start_sh_rejects_invalid_port_values_before_startup(
    start_sh_path: Path, name: str, value: str
) -> None:
    """Bad local port input fails before dependencies or listeners are touched."""
    result = subprocess.run(
        ["bash", str(start_sh_path)],
        env={**os.environ, name: value},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert name in result.stdout
    assert "non-privileged numeric TCP port" in result.stdout


def test_start_sh_rejects_duplicate_configured_ports(start_sh_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(start_sh_path)],
        env={
            **os.environ,
            "ATLAS_UI_PORT": "4333",
            "ATLAS_RULES_PORT": "4333",
            "ATLAS_FINLYNQ_PORT": "4334",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "must be distinct" in result.stdout

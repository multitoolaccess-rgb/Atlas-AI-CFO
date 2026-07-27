"""E2E test for start.sh — ONE cold-boot run that asserts across cold-boot
health + all three polish items.

Marked ``@pytest.mark.slow``. On a clean dev machine this takes ~60-120s
(uvicorn boot × 2 + first next-dev compile). Opt out with:

    pytest tests/test_start_sh_e2e.py -m "not slow"

Why one big test, not three small ones: each ``bash start.sh`` is
~60-120s. Three separate cold-boots would multiply that 3×. The tests
share one captured stdout via a single subprocess invocation.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_SLOW = pytest.mark.slow


@_SLOW
def test_start_sh_e2e_cold_boot_meets_all_polish_invariants(
    start_sh_path: Path, project_root: Path
) -> None:
    """One e2e cold-boot asserts:

    1. Cold-boot health: status block shows HTTP=200 on all 3 services
       (FQ finlynq :8001, BE rules-service :8000, FE next dev :3000).
    2. Polish #2 (probe-then-skip pip): on a warm cache, ``start.sh`` MUST
       NOT rewrite ``.run/finlynq-pip.log``. Asserted by comparing
       (mtime, size) before vs after.
    3. Polish #3 (status-block pid-column alignment): the byte offset of
       ``pid=`` is the same across all 3 rows so columns survive any
       pid-width variation.

    Polish #1 (cleanup-on-gate-failure) is verified by the static-analysis
    tests in ``test_start_sh_unit.py`` — inducing an actual gate failure
    in CI would require pre-binding a port that uvicorn can't use, which
    adds nondeterminism the static test avoids entirely.
    """

    # Snapshot pip log (mtime + size) for the warm-cache probe-then-skip
    # invariant. If the file does NOT exist yet, that's still a valid
    # snapshot — a warm cache that NEVER needed to install will leave
    # the file absent across runs.
    pip_log = project_root / ".run" / "finlynq-pip.log"
    pre_pip = (
        pip_log.exists(),
        pip_log.stat().st_mtime if pip_log.exists() else 0.0,
        pip_log.stat().st_size if pip_log.exists() else 0,
    )

    # ---- Boot ----------------------------------------------------------
    result = subprocess.run(
        ["bash", str(start_sh_path)],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"start.sh exited {result.returncode}.\n"
        f"--- stdout (last 4000 chars) ---\n{result.stdout[-4000:]}\n"
        f"--- stderr (last 4000 chars) ---\n{result.stderr[-4000:]}"
    )

    # ---- 1. Cold-boot health ------------------------------------------
    # The captured label is JUST the service name (``finlynq`` /
    # ``rules-service`` / ``next dev``); the variable-width port +
    # padding inside the parens (``finlynq       :8001``) is consumed
    # but not captured so the dict equality assert below is stable across
    # pid-width variations.
    rows = re.findall(
        r"^\s+(?:FQ|BE|FE)\s+\((?P<label>finlynq|rules-service|next dev)\b[^)]*\)\s+pid=\S+\s+HTTP=(\d+)",
        result.stdout,
        re.MULTILINE,
    )
    assert len(rows) == 3, (
        f"Expected exactly 3 service rows in the status block; found {len(rows)}.\n"
        f"Rows: {rows}\n"
        f"--- stdout (last 4000 chars) ---\n{result.stdout[-4000:]}"
    )
    by_label = dict(rows)
    expected = {"finlynq": "200", "rules-service": "200", "next dev": "200"}
    assert by_label == expected, (
        f"Status block rows: {by_label}. Expected {expected} (all HTTP=200)."
    )

    # ---- 2. Polish #2 probe-then-skip --------------------------------
    # If the probe-satisfied branch fired (the warm case), pip install
    # was NOT invoked and the log mtime/size stay identical to the
    # pre-run snapshot. A regression that runs pip unconditionally
    # would mtime-flip the file mid-run and trip this assertion.
    if pip_log.exists():
        post_pip = pip_log.stat()
        assert (post_pip.st_mtime, post_pip.st_size) == (pre_pip[1], pre_pip[2]), (
            f"Warm-boot rewrote `.run/finlynq-pip.log` "
            f"(mtime {pre_pip[1]} → {post_pip.st_mtime}; "
            f"size {pre_pip[2]} → {post_pip.st_size}). "
            f"Polish #2 (probe-then-skip) regressed — start.sh is running "
            f"`pip install` even though the venv already satisfies the deps."
        )

    # ---- 3. Polish #3 pid-column alignment ---------------------------
    pid_lines = re.findall(
        r"(?P<line>^\s+(?:FQ|BE|FE)\s+\([^)]+\)\s+pid=.*$)",
        result.stdout,
        re.MULTILINE,
    )
    assert len(pid_lines) == 3, (
        f"regex for status-block pid rows found {len(pid_lines)} (need 3):\n"
        + "\n".join(f"  {p}" for p in pid_lines)
    )
    offsets = {line.index("pid=") for line in pid_lines}
    assert len(offsets) == 1, (
        f"`pid=` offsets disagree across rows: {sorted(offsets)} "
        f"(rows:\n" + "\n".join(f"  {line!r}" for line in pid_lines) + ")"
    )

import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_status_is_healthy() -> None:
    """Phase 3 baseline — must stay 'healthy' so any client gating on
    it (the FE's bootstrap fetch) keeps working after the Phase 19
    extension adds new fields."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def _repo_root_for_test() -> str:
    """``tests/test_health.py`` lives at
    ``<repo>/services/rules-service/tests/test_health.py``.
    Four ``Path.parents`` hops land at the repo root where ``.git/``
    lives — same ascent ``app.main._REPO_ROOT`` uses internally, so
    the cross-check below compares against the SAME source of truth
    the running backend reads.
    """
    return str(Path(__file__).resolve().parents[3])


def test_health_extended_contract() -> None:
    """Phase 19 — /health exposes process diagnostics so an operator
    can answer 'is the running process stale?' with one curl.

    Asserts shape + types + ranges AND cross-checks the returned
    ``git_sha`` against the working-tree SHA — a helper regression
    (wrong cwd, broken subprocess, hardcoded string) trips the test
    loudly instead of being silently waved through.
    """
    repo_root = _repo_root_for_test()

    # 1. Cross-check the working-tree SHA first. Its presence is the
    # premise for the strict ``git_sha is not None`` assertion below;
    # if THIS subprocess fails, the test env isn't a checkout and the
    # assertion would be meaningless. Asserting on it surfaces the
    # actual cause instead of a downstream AttributeError.
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=2.0,
    )
    assert proc.returncode == 0, (
        f"test env isn't a git checkout (cwd={repo_root!r}); cannot "
        f"cross-check health.git_sha. stderr: {proc.stderr!r}"
    )
    expected_sha = proc.stdout.strip()

    # 2. Issue the live request. Same interpreter as the imported
    # ``app``, so ``_APP_PID`` was captured in this process.
    body = client.get("/health").json()

    # 3. ``status`` unchanged (Phase 3 wealthiq contract).
    assert body["status"] == "healthy"

    # 4. ``started_at`` must round-trip through ``datetime.fromisoformat``
    # AND carry a tz offset — otherwise cross-tz arithmetic ("10
    # minutes ago" vs "5 minutes ago") misbehaves for an operator.
    parsed = datetime.fromisoformat(body["started_at"])
    assert parsed.tzinfo is not None, (
        f"started_at must be tz-aware (got {body['started_at']!r}); "
        f"operator cross-tz arithmetic breaks otherwise."
    )

    # 5. ``pid`` is captured at app boot. It SHOULD equal
    # ``os.getpid()`` in the test interpreter (pytest re-uses one
    # process for the test run).
    pid = body["pid"]
    assert isinstance(pid, int)
    assert pid > 0
    assert pid == os.getpid(), (
        f"health.pid ({pid}) should equal os.getpid() ({os.getpid()}); "
        f"mismatch means _APP_PID wasn't captured in this process."
    )

    # 6. ``git_sha``: strict non-None + matches the working-tree SHA.
    # DEV + CI environments have git, so a None return is a helper
    # regression — fail loudly instead of being silently waved through.
    sha = body["git_sha"]
    assert sha is not None, (
        f"git_sha is None — the /health helper regressed. Expected "
        f"{expected_sha!r} from working-tree git rev-parse; fix "
        f"app.main._detect_git_sha."
    )
    assert isinstance(sha, str)
    assert 4 <= len(sha) <= 40, f"git_sha length suspicious: {sha!r}"
    assert all(c in "0123456789abcdef" for c in sha.lower()), (
        f"git_sha must be lowercase hex (got {sha!r})"
    )
    assert sha == expected_sha, (
        f"git_sha returned by /health ({sha!r}) doesn't match the "
        f"working-tree git rev-parse ({expected_sha!r}). Likely "
        f"cause: subprocess cwd points to the wrong repo (vendored "
        f"copy, fixture clone) — verify _REPO_ROOT ascent."
    )

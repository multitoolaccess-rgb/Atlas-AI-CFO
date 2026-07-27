# services/tests/conftest.py
#
# Phase-F2 #1 round-1: ``pytest_configure`` hook pins env vars BEFORE
# any test module-load. Previously, services/tests/test_cross_db_roundtrip.py
# wrote ``os.environ["DATABASE_URL"]`` AT MODULE IMPORT time, which
# is fragile under pytest's collection ordering (a sibling rules-service
# or finlynq test file collected BEFORE this one would side-effect-bind
# its engine first and miss the shared URL pin).
#
# ``pytest_configure`` runs ONCE at the start of the test session,
# BEFORE any test file's conftest or test module imports execute, so
# the env var is set deterministically regardless of collection
# order.
#
# ``pytest_unconfigure`` drops the temp SQLite file at session end
# so the temp-file pattern doesn't accumulate across re-runs.
import os
import uuid


def _resolve_shared_db_path() -> str:
    """Resolve the temp SQLite path once at conftest module-load.

    Uniquified per-process (PID + uuid4 hex) so two concurrent pytest
    invocations on the same dev laptop don't lock-step on a shared
    file. The path is exposed at module level so test_cross_db_roundtrip
    can dispose its external engine against the SAME path Finlynq
    bound to.
    """
    return f"/tmp/fc-cross-engine-{os.getpid()}-{uuid.uuid4().hex[:8]}.db"


_SHARED_DB_PATH = _resolve_shared_db_path()
_SHARED_DB_URL = f"sqlite:////{_SHARED_DB_PATH}"
# Expose for test modules that want to read the committed path.
os.environ.setdefault("FC_SHARED_CROSS_DB_PATH", _SHARED_DB_PATH)


def pytest_configure(config):
    """Pin DATABASE_URL + TEST_DATABASE_URL to the shared SQLite path.

    Runs once at session start, before any test module-load. By the
    time services/tests/test_cross_db_roundtrip.py executes its
    imports, ``app.database.engine`` is guaranteed to bind to
    ``os.environ["DATABASE_URL"]`` (the shared URL).
    """
    os.environ["DATABASE_URL"] = _SHARED_DB_URL
    os.environ["TEST_DATABASE_URL"] = _SHARED_DB_URL
    # JWT secret + local user + environment are pinned so the in-process
    # ``app.config.settings`` resolves consistently with rules-service
    # and finlynq's own conftests. We intentionally DON'T clobber
    # JWT_SECRET if a caller already set it (idempotent for nested
    # pytest configurations).
    os.environ.setdefault("JWT_SECRET", "pytest-jwt-secret-cross-engine-integration")
    os.environ.setdefault("LOCAL_USER", "alex")
    os.environ.setdefault("ENVIRONMENT", "development")


def pytest_unconfigure(config):
    """Drop the shared SQLite file at session end.

    Best-effort: an OSError here is fine (the file may already be
    gone if pytest was interrupted mid-session). External-engine
    disposal lives in the cross-DB test's atexit so a session crash
    mid-test still drops the file when Python exits.
    """
    try:
        if os.path.exists(_SHARED_DB_PATH):
            os.remove(_SHARED_DB_PATH)
    except OSError:
        pass

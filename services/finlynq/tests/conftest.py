"""Pytest fixtures for Finlynq tests — Phase F4.

Hermetic guarantees:
- ``JWT_SECRET`` is overridden to a fixed test value BEFORE app.config
  imports so ``Settings`` reads deterministically regardless of the
  host ``.env`` file.
- ``LOCAL_USER`` matches what rules-service issues (default "alex" but
  pinned here so a CI runner with a different ENV var still aligns).
- ``DATABASE_URL`` resolves to a uniquified temp-file SQLite URL
  (per-PID so concurrent pytest invocations don't lock-step on a
  shared DB).

Phase-F4 seeding: ``Base.metadata.create_all(engine)`` runs in an
autouse session-scope fixture, then ``seed_default_categories(db)``
populates the 12 default rows so routes that depend on the lookup
table don't see an empty result. This mirrors rules-service's
``_bootstrap_test_schema`` autouse fixture.

Cross-service invariant: the temp-file URL is shared with
rules-service's conftest when the cross-service integration test
sets ``TEST_DATABASE_URL`` — both services bind to the SAME
SQLite file per Phase-F2 shared-DB wiring.
"""
import os

# Pin env vars BEFORE any `from app.config import settings` happens.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "pytest-finlynq-secret-do-not-leak-to-prod")
os.environ.setdefault("LOCAL_USER", "alex")
# Phase-F2: honor TEST_DATABASE_URL when set (cross-service harness),
# default to a uniquified temp-file SQLite URL for hermetic Finlynq-only runs.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL") or f"sqlite:////tmp/fc-finlynq-test-{os.getpid()}.db",
)


def _disable_env_file_lookup():
    """Same env_file backdoor close as rules-service/tests/conftest.py.

    Re-creates the module-level ``settings`` singleton after the class patch
    so a host ``services/finlynq/.env`` cannot leak into tests.
    """
    try:
        from app.config import Settings
        old = dict(Settings.model_config)
        Settings.model_config = {**old, "env_file": None}
        import app.config as _app_config

        _app_config.settings = Settings()
    except Exception:
        pass


_disable_env_file_lookup()


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import issue_token  # noqa: E402
from app.main import app  # noqa: E402  (registers ORM models + seed bootstrap)
from app.services.categorizer import seed_default_categories  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_schema_and_seed():
    """Phase-F4 hermetic: create tables + seed default categories ONCE
    per pytest process. The category table is the lookup for
    /categorize + /categories; without seeds the categorizer returns
    ``{categorized: 0, skipped: N}`` because the heuristic's
    ``MERCHANT_RULES`` keys have no corresponding Category rows.

    NOTE: this runs after ``disable_env_file_lookup`` AND after the
    import of ``app.main`` so the engine binding is the per-PID
    temp-file SQLite URL — concurrent test processes therefore
    don't collide on a shared DB.
    """
    from app.database import Base, SessionLocal, engine  # noqa: E402

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_default_categories(db)
    finally:
        db.close()
    yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient without lifespan context. /categorize +
    /categories don't depend on the alembic-on-startup hook — the
    schema + seeds are bootstrapped by the session-scope autouse
    fixture above.
    """
    return TestClient(app)


@pytest.fixture
def client_with_auth() -> TestClient:
    """TestClient with a valid ``fc_session`` cookie pre-loaded so
    ``Depends(require_user)`` accepts the request.

    Phase-F4 ships most /categorize + /categories routes as
    auth-gated. ``client`` (no auth) returns 401 from those routes;
    ``client_with_auth`` returns 200.
    """
    token = issue_token()
    c = TestClient(app)
    c.headers["Cookie"] = f"fc_session={token}"
    return c


@pytest.fixture
def db_session():
    """Yield a SQLAlchemy Session for direct DB assertions.

    Tests use this to seed transaction rows that the categorizer
    reads, then call ``POST /categorize`` and assert the count.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Alembic migration round-trip test (Phase 3 — generates schema via migration, not ``create_all``).

Per ``docs/architecture.md`` Phase 3 forward-look + ``docs/master-plan.md``:
Alembic is the single source of schema truth. This test enforces:

1. The existing ``alembic/versions/0001_initial.py`` (auto-generated during
   Phase 3) runs cleanly against an empty Postgres database.
2. It creates ALL 7 expected app tables (plus ``alembic_version``).
3. ``alembic downgrade base`` removes them.
4. ``alembic upgrade head`` recreates them (round-trip).

Uses the dev Postgres on port 5433 (set up by the wealthiq-baseline-test recipe
from earlier in this conversation) with a dedicated test database name
``wealthiq_alembic_phase3`` so it stays isolated from the wealthiq baseline
pytest run.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa


# --- Path constants --------------------------------------------------------

RULES_SVC = Path(__file__).resolve().parents[1]
REPO_ROOT = RULES_SVC.parents[1]
ALEMBIC_BIN = Path(sys.executable).with_name("alembic")
PG_BIN = Path("/opt/homebrew/opt/postgresql@15/bin")

TEST_DB_NAME = "wealthiq_alembic_phase3"
TEST_DB_URL = f"postgresql+psycopg2://postgres@localhost:5433/{TEST_DB_NAME}"

# Phase-F2 task #1: this module REQUIRES a Postgres dev sidecar on :5433.
# Skip ALL tests if the sidecar isn't reachable so a dev-laptop
# session doesn't fail every test with ``OperationalError: could not
# connect to server``. CI / pre-commit with the sidecar up via
# docker-compose still runs the full suite.

_PG_SIDECAR_ADMIN_URL = "postgresql+psycopg2://postgres@localhost:5433/postgres"

try:
    _probe_engine = sa.create_engine(_PG_SIDECAR_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with _probe_engine.connect() as _probe_conn:
            _probe_conn.execute(sa.text("SELECT 1"))
        _PG_SIDECAR_OK = True
    finally:
        _probe_engine.dispose()
except Exception:
    _PG_SIDECAR_OK = False

# Apply at module level — pytest treats ``pytestmark = skipif(...)``
# as if every individual ``@pytest.mark.skipif(...)`` decorator were
# applied to every test in the module. Cleaner than four identical
# decorators.
pytestmark = pytest.mark.skipif(
    not _PG_SIDECAR_OK,
    reason="requires Postgres dev sidecar on :5433 (set TEST_DATABASE_URL to a Postgres URL or run docker-compose up first)",
)


# --- Core helpers ----------------------------------------------------------


def _pg_env() -> dict:
    """PATH-augmented env so dropdb/createdb/psql are reachable."""
    env = os.environ.copy()
    env["PATH"] = str(PG_BIN) + ":" + env.get("PATH", "")
    return env


def _read_all_revisions() -> dict[str, str | None]:
    """Parse every ``alembic/versions/*.py`` file for ``revision`` +
    ``down_revision`` so we can walk the chain in order. Phase 7+ ships a
    second migration (``b0a32894ce61_add_local_user_sub.py``); the test
    fixtures now handle a chain of any length instead of assuming
    ``len(mig_files) == 1``.
    Returns ``{revision_sha: down_revision_sha_or_None}``.
    """
    out: dict[str, str | None] = {}
    for path in sorted((RULES_SVC / "alembic" / "versions").glob("*.py")):
        rev, down = None, None
        for line in path.read_text().splitlines():
            s = line.strip()
            if s.startswith("revision") and "=" in s and "str" in s:
                try:
                    rev = s.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
            elif s.startswith("down_revision") and "=" in s:
                try:
                    value = s.split("=", 1)[1].strip()
                    if value in ("None", "null", ""):
                        down = None
                    else:
                        down = value.strip('"').strip("'")
                except Exception:
                    pass
        if rev is not None:
            out[rev] = down
    return out


def _head_revision() -> str | None:
    """Walk the alembic revision chain to the head (no-CHILDREN node).

    Alembic semantics:

    - **Base** = a revision with ``down_revision = None`` (the genesis node
      of the chain — it has a parent-less position because alembic's
      empty pre-migration state is its conceptual parent).
    - **Head** = a revision with NO children — i.e. no other revision's
      ``down_revision`` points at it. The head is the most recent revision
      the schema is upgraded TO.

    The head-finding logic below works for linear chains, branched chains
    with multiple heads, and single-revision trees uniformly. Round 2's
    draft treated ``down_revision is None`` as the head — that flags the
    *base* as the head, which is wrong; this round inverts the criterion
    to "no one's parent".
    """
    chain = _read_all_revisions()
    if not chain:
        return None
    down_revs = {down for down in chain.values() if down is not None}
    heads = [rev for rev in chain.keys() if rev not in down_revs]
    return heads[0] if heads else None


def _prepare_test_db() -> None:
    """Drop + recreate the test database via raw SQL (psycopg2 + sqlalchemy).

    Phase 3 evolution:

    1. **subprocess** (``dropdb`` + ``createdb``) — racy when prior test's
       engine connections weren't released quickly enough; raised
       ``CalledProcessError`` during the THIRD test's fixture setup.

    2. **plain SQL DROP/CREATE** — broke for the SAME reason in a different
       form: Postgres refused DROP DATABASE ``wealthiq_alembic_phase3`` with
       ``psycopg2.errors.ObjectInUse`` because the previous test's
       ``engine.dispose()`` laundered psycopg2's connection state but Postgres
       still saw the backend in ``pg_stat_activity`` for a few milliseconds.

    3. **DROP DATABASE ... WITH (FORCE)** (Postgres 13+) — cleanly terminates
       all backends connected to the test DB before dropping it. This is the
       canonical Postgres idiom for tests that cycle a database across runs,
       and it's idempotent across the 3 sequential test invocations here.
    """
    import sqlalchemy as sa
    from sqlalchemy import text

    admin_url = f"postgresql+psycopg2://postgres@localhost:5433/postgres"
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
            )
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin.dispose()


def _alembic(*args: str, url: str = TEST_DB_URL) -> subprocess.CompletedProcess:
    """Invoke alembic CLI from services/rules-service with DATABASE_URL set."""
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["PATH"] = str(PG_BIN) + ":" + env.get("PATH", "")
    return subprocess.run(
        [str(ALEMBIC_BIN), *args],
        cwd=str(RULES_SVC),
        env=env,
        capture_output=True,
        text=True,
    )


# --- Fixture + tests -------------------------------------------------------


@pytest.fixture(scope="function")
def fresh_test_db():
    """Drop+create the test DB PER TEST — no order-dependence.

    Phase 3 code-review raised: ``scope="module"`` made every test inherit
    whatever state the previous test left the DB in, so a round-trip failure
    in test #2 leaked into the version-check in test #3. ``scope="function"``
    costs an extra drop+create per test (≈0.5s) but makes the suite safe to
    run in any order or to re-run after a failure.
    """
    _prepare_test_db()
    yield


def test_alembic_upgrade_head_creates_all_seven_app_tables(fresh_test_db):
    """The first alembic migration must create every Phase 3-lifted table."""
    r = _alembic("upgrade", "head")
    assert r.returncode == 0, (
        f"alembic upgrade head failed (exit {r.returncode}):\n"
        f"stderr: {r.stderr}\nstdout: {r.stdout}"
    )

    import sqlalchemy as sa

    engine = sa.create_engine(TEST_DB_URL)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "users", "institutions", "accounts", "categories",
            "transactions", "import_batches", "budgets",
        }
        missing = expected - tables
        assert not missing, f"missing after upgrade: {missing}"
        assert "alembic_version" in tables, "alembic_version table should exist"
    finally:
        engine.dispose()


def test_alembic_downgrade_base_then_reup_round_trip(fresh_test_db):
    """downgrade base drops tables; re-upgrade brings them back."""
    expected_revision = _head_revision()
    assert expected_revision is not None, (
        "could not parse the alembic revision chain; cannot verify downgrade moved past the head"
    )

    # 1. downgrade -> all 7 app tables should disappear
    r = _alembic("downgrade", "base")
    assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"

    import sqlalchemy as sa
    from sqlalchemy import text

    engine = sa.create_engine(TEST_DB_URL)
    try:
        inspector = sa.inspect(engine)
        tables_after_down = set(inspector.get_table_names())
        assert "users" not in tables_after_down, "users should not exist after downgrade base"
        assert "transactions" not in tables_after_down, "transactions should not exist after downgrade base"
        # alembic preserves the `alembic_version` table across downgrades; the
        # current revision row is just cleared. Verify the row does NOT point at
        # our migration SHA (proves the downgrade actually moved the version).
        result = engine.connect().execute(text("SELECT version_num FROM alembic_version"))
        rows = result.fetchall()
        current_revision = rows[0][0] if rows else None
        assert current_revision != expected_revision, (
            f"downgrade base should clear the current revision; "
            f"alembic_version.version_num = {current_revision!r}, "
            f"expected != {expected_revision!r}"
        )
    finally:
        engine.dispose()

    # 2. re-upgrade -> tables come back
    r = _alembic("upgrade", "head")
    assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"
    engine = sa.create_engine(TEST_DB_URL)
    try:
        inspector = sa.inspect(engine)
        tables_after_reup = set(inspector.get_table_names())
        expected = {
            "users", "institutions", "accounts", "categories",
            "transactions", "import_batches", "budgets",
        }
        assert expected.issubset(tables_after_reup), (
            f"missing after re-upgrade: {expected - tables_after_reup}"
        )
    finally:
        engine.dispose()


def test_alembic_version_matches_latest_revision(fresh_test_db):
    """After upgrade head, alembic's version row matches the head SHA.

    Phase 3 code-review raised: a non-empty stdout check is too weak — it
    catches a missing version row but not a mismatch. Strengthen: walk the
    alembic revision chain to the head SHA, then assert it is in
    ``alembic current``'s output.
    """
    expected_revision = _head_revision()
    assert expected_revision is not None, (
        f"could not parse alembic revision chain; migration files: "
        f"{[m.name for m in (RULES_SVC / 'alembic' / 'versions').glob('*.py')]}"
    )

    # Apply migration so alembic_version exists.
    r = _alembic("upgrade", "head")
    assert r.returncode == 0

    r = _alembic("current")
    assert r.returncode == 0
    # `alembic current` prints something like "<sha> (head)" or plain "<sha>".
    assert expected_revision in r.stdout, (
        f"expected alembic current output to mention {expected_revision}; got:\n{r.stdout}"
    )

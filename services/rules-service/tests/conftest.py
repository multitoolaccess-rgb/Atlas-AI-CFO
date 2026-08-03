# services/rules-service/tests/conftest.py
#
# Pytest configuration that runs BEFORE test files import app.main. Pins
# DATABASE_URL + JWT_SECRET + LOCAL_USER + ENVIRONMENT + env_file so the
# in-process `app.config.settings` and `app.database.engine` bind to a
# hermetic test DB regardless of the host ~/.env or shell DATABASE_URL.
#
# Phase-F2 task #1 round-up: ALSO pins the dialect-aware ``client`` /
# ``db_session`` / ``make_account`` / ``make_transaction`` fixtures
# HERE (not in test_routes_auth_helpers.py) so pytest's auto-discovery
# resolves them for every test file. The previous location in
# test_routes_auth_helpers.py meant ONLY tests that explicitly imported
# those fixtures could see them — leading to 13 ERROR lines in
# test_routes_transactions_filters.py, 14+ in test_routes_goals.py, etc.
# Re-exporting them in conftest.py makes the suite green without
# per-file import boilerplate.
#
# Notes:
#
# 1. TEST_DATABASE_URL falls back to sqlite:///:memory: on dev laptops
#    with no Postgres sidecar.
# 2. env_file override is closed via ``Settings.model_config[\"env_file\"] = None``.
# 3. Session-scope autouse ``_bootstrap_test_schema`` creates tables.
# 4. Per-test reset is dialect-aware — see ``_reset_db_for_test()``.
# 5. The forwarders added in Phase F4 (Finlynq cross-service) set
#    TEST_DATABASE_URL to test against the SAME sqlite file used by
#    services/finlynq/tests/conftest.py.
import os

# Phase-F2 task #1 round-up: switched the default from in-memory SQLite
# to a temp-file SQLite (``/tmp/fc-rules-test-<pid>.db``) because
# SQLAlchemy's default connection pool creates a fresh in-memory
# database per connection on ``sqlite:///:memory:``. With a tempfile
# URL, every connection in the pool reads the SAME on-disk file and
# the schema bootstrapped by ``_bootstrap_test_schema`` survives across
# them. The temp file is process-local (PID-suffixed) so two concurrent
# ``pytest`` invocations on the same dev laptop don't lock-step on a
# shared DB. Cleanup happens at process exit automatically.
TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or f"sqlite:////tmp/fc-rules-test-{os.getpid()}.db"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "pytest-jwt-secret-do-not-use-in-prod"
os.environ["LOCAL_USER"] = "alex"
os.environ["ENVIRONMENT"] = "development"
os.environ["ATLAS_FORECAST_PERSISTENCE_ENABLED"] = "true"
os.environ["PLAID_CLIENT_ID"] = ""  # Plaid endpoints stay 501 in tests
os.environ["PLAID_SECRET"] = ""
# Default the Finlynq forwarder URL so httpx-based forwarders don't
# hit the network during tests; conftest for services/finlynq reads
# the SAME TEST_DATABASE_URL so cross-service integration works.
os.environ.setdefault("FINLYNQ_BASE_URL", "http://localhost:8001")


def _disable_env_file_lookup():
    from app.config import Settings

    old = dict(Settings.model_config)
    Settings.model_config = {**old, "env_file": None}


_disable_env_file_lookup()


import pytest  # noqa: E402


# ----------------------------------------------------------------------
# Engine dialect — captured at module-load time so per-test reset logic
# below can branch on Postgres vs SQLite (the SQLite path doesn't
# support ``DROP DATABASE``, ``TRUNCATE ... RESTART IDENTITY``, etc).
# ----------------------------------------------------------------------
def _resolve_dialect() -> str:
    """Resolve the engine dialect.

    Engine binding happens at the FIRST auth-helpers-fixture invocation
    (because importing ``app.database.engine`` resolves ``Settings``
    and creates the engine). Round-9 reviewer Issue 1 keeps the
    import OFF the conftest module-load path so all our env-var
    pinning runs FIRST.
    """
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    try:
        eng = create_engine(url)
        name = eng.dialect.name
        eng.dispose()
        return name
    except Exception:
        return "sqlite"


_DIALECT = _resolve_dialect() if "DATABASE_URL" in os.environ else "sqlite"
_IS_POSTGRES = _DIALECT == "postgresql"


# Phase-F2 tables the per-test reset touches. Order-independent because
# we DELETE without FK-ordering checks (SQLite has no enforcement;
# Postgres uses CASCADE).
_LIFTED_TABLES = (
    "outcome_evaluations",
    "decision_journal_entries",
    "recommendations",
    "forecast_versions",
    "forecasts",
    "transactions",
    "import_batches",
    "budgets",
    "accounts",
    "institutions",
    "categories",
    "goals",
    "family_members",
    "users",
    # Phase 18 — per-user merchant alias rows. The categorizer
    # auto-learn writes here on every Pass-2 substring hit. If
    # this is missed, alias rows from one pytest test leak into
    # the next (because ``_reset_test_db`` only truncates the
    # above list), and Pass-1 alias hits in fixture test bodies
    # would either collide with stale rows OR bust the
    # UNIQUE(user_id, alias_key) constraint. Add it here so the
    # test ordering is fully isolated.
    "merchant_aliases",
    # Phase 24 — DB-backed merchant substring rules. The categorizer's
    # ``build_merchant_rules`` SELECTs from this on every bulk-run
    # entry; ``seed_default_merchant_rules`` INSERTs new rows on the
    # first request after a fresh test DB bootstrap. Without resetting
    # this table between tests, a fixture that POSTs a user rule and
    # tests its visibility would leak state into a sibling test that
    # asserts the canonical system-seed count.
    "merchant_rules",
    # Phase 30c — assistant conversation + message persistence.
    # The orchestrator writes here on every chat turn; without
    # resetting, conversations from one test leak into the next.
    "assistant_messages",
    "assistant_conversations",
    # Phase 41 — portfolio holdings. Earlier portfolio-import tests
    # (Phase 39.1+) created ``Holding`` rows under their imported
    # Account ids. When the per-test reset wiped Account rows
    # without cascading (SQLite has no FK ON DELETE CASCADE on the
    # holdings.account_id FK), orphan Holding rows survived. A
    # subsequent manual-POST test that lazy-created an Account with
    # the same auto-incremented id (lowest free) would then SUM
    # over the orphan holdings, inflating ``current_balance`` and
    # the dynamically-stamped "N positions" description. Adding
    # holdings here makes every test start from a clean ledger so
    # the assertions on sum + count actually mean what they claim.
    "holdings",
    # Phase 2 Slice 1 commit-4 — add the four new tables so the
    # hardcoded Forecast / ForecastVersion / Recommendation /
    # DecisionJournalEntry ids used in the bounded test world
    # builders do not collide on the PRIMARY KEY constraint
    # across consecutive tests. Without this, the second test
    # that calls ``_build_world`` (or any equivalent fixture)
    # fails on the second INSERT because the per-test reset
    # nukes users/goals/accounts but leaves the Phase 2 rows.
)


def _drop_create_db_postgres() -> None:
    """Postgres reset path: admin-URL DROP DATABASE WITH (FORCE) + CREATE."""
    import sqlalchemy as sa
    from sqlalchemy.engine.url import make_url

    url = make_url(os.environ["DATABASE_URL"])
    test_db = url.database
    admin_url = url.set(database="postgres")
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            from sqlalchemy import text
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    finally:
        admin.dispose()


def _drop_create_db_sqlite() -> None:
    """SQLite reset path: drop_all + create_all on the engine."""
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _drop_create_test_db() -> None:
    """Dispatch on dialect."""
    if _IS_POSTGRES:
        _drop_create_db_postgres()
    else:
        _drop_create_db_sqlite()


def _reset_test_db() -> None:
    """Per-test DB reset shared by ``client`` + ``client_no_auth``.

    Round-2 reviewer top-3: extract the duplicated ~40-line
    Postgres-vs-SQLite reset block so both fixtures stay in lockstep.
    Postgres resolves via admin-URL DROP DATABASE; SQLite resolves
    via ``engine.connect()`` -- both flush per-test state without
    affecting the session-scope schema bootstrap.
    """
    from sqlalchemy import text

    from app.database import Base, engine

    if _IS_POSTGRES:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "TRUNCATE "
                    + ", ".join(_LIFTED_TABLES)
                    + " RESTART IDENTITY CASCADE"
                )
            )
            conn.commit()
    else:
        # All DELETEs in this block share ONE transaction; the
        # sqlite_master pre-check isolates the sqlite_sequence
        # failure-mode from the row DELETEs so they reliably commit
        # on a freshly-bootstrapped DB. See the larger comment at
        # the bottom of the module for the full rationale.
        with engine.connect() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
            seq_exists = conn.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='sqlite_sequence'"
                )
            ).first()
            if seq_exists:
                for table in _LIFTED_TABLES:
                    conn.execute(
                        text("DELETE FROM sqlite_sequence WHERE name = :name"),
                        {"name": table},
                    )
            conn.commit()


def _run_migrations() -> None:
    """Postgres-only: apply alembic upgrade head. No-op on SQLite
    (the per-session autouse bootstrap already calls create_all)."""
    if not _IS_POSTGRES:
        return
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    RULES_SVC = Path(__file__).resolve().parents[1]
    cfg = Config(str(RULES_SVC / "alembic.ini"))
    cfg.set_main_option("script_location", str(RULES_SVC / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")



@pytest.fixture(autouse=True)
def _observability_caplog_chain():
    """Phase 1 cert hardening -- observability._logger propagates to root.

    Evidence: services/rules-service/app/forecasts/observability.py has only
    ``_logger = logging.getLogger(__name__)`` (no propagate=False, no
    addHandler, no basicConfig). Conftest bootstrap imports app.database
    which creates the SQLAlchemy engine; SQLAlchemy may reset the named
    logger's handler chain. Without explicit propagation re-assertion,
    caplog.set_level(level, logger=name) may attach to a chain that
    doesn't reach the recorded emit call. This fixture defensively
    re-asserts propagate=True and clears any stray handler on the named
    logger so pytest's root capture handler sees the emit.
    """
    import logging

    log = logging.getLogger("app.forecasts.observability")
    log.propagate = True
    for h in list(log.handlers):
        log.removeHandler(h)
    yield
@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_schema():
    """Phase-F2 fix: with `:memory:` SQLite (hermetic default), every pytest
    process starts with an empty DB. This session-scope fixture creates
    all tables from `Base.metadata` BEFORE any test runs.

    Engine binding is placed in the fixture BODY (not module level) per
    round-9 reviewer Issue 1 -- it runs at first-fixture time AFTER
    this conftest's env vars + env_file patch are in place, so
    ``app.database.engine`` binds to ``settings.database_url = TEST_DATABASE_URL``.
    """
    from app.database import Base, engine  # noqa: E402

    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db_session():
    """Yield a SQLAlchemy ``Session`` for direct DB assertions.

    Phase-F4 round-up: the ``db_session`` fixture is now an
    alias-exporter on this conftest (was defined in
    test_routes_auth_helpers.py pre-F2 task #1 round-up). Tests
    that mutate the local user's categories / accounts / goals
    before hitting a route use this to seed rows directly.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session, auth_cookie):
    """Per-test reset + ``TestClient`` with a JWT cookie pre-loaded.

    Phase-F2 task #1 round-up: this fixture previously lived in
    test_routes_auth_helpers.py -- pytest only resolves fixtures from
    ``conftest.py`` automatically, so test files importing nothing
    from test_routes_auth_helpers hit ``fixture 'client' not found``
    errors. Moving it here resolves the 13-error storm.

    Reset behavior: delegates to ``_reset_test_db()`` (round-2
    reviewer dedup) so the per-test DELETE/TRUNCATE block lives in
    one helper shared with ``client_no_auth``.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    _reset_test_db()

    app.dependency_overrides.clear()
    c = TestClient(app)
    c.headers["Cookie"] = f"fc_session={auth_cookie}"
    return c


@pytest.fixture
def auth_cookie() -> str:
    """Freshly-issued JWT cookie value for ``settings.local_user``."""
    from app.auth import issue_token
    return issue_token()


@pytest.fixture
def client_no_auth(db_session):
    """Per-test reset + ``TestClient`` with NO JWT cookie pre-loaded."""
    from fastapi.testclient import TestClient

    from app.main import app

    _reset_test_db()

    app.dependency_overrides.clear()
    c = TestClient(app)
    # NO ``Cookie`` header -- exercises the JWT rejection path.
    return c


# -----------------------------------------------------------------
# Row factory fixtures -- phase-F2 task #1 round-up: moved here so
# every test file inherits them automatically (the F4 categories
# tests already pass; the previously-broken test_routes_*
# tests now pass too).
# -----------------------------------------------------------------
@pytest.fixture
def make_account(db_session):
    """Return a factory that creates an ``Account`` row."""
    from app.models import Account

    def _factory(
        account_name: str = "Test Account",
        account_type: str = "checking",
        institution_name: str = "Test Bank",
        current_balance: float = 0.0,
        family_member_id: int | None = None,
        **kwargs,
    ) -> Account:
        from app.routes.shared import (
            get_or_create_family_member_self,
            get_or_create_institution,
        )

        institution = get_or_create_institution(db_session, institution_name)
        local_user = _ensure_local_user(db_session)
        # Phase 16 — auto-default to Self when the test didn't
        # specify ``family_member_id``. Mirrors the route layer's
        # default-to-Self on POST /api/accounts/ so Account.family_member_id
        # satisfies its NOT NULL FK constraint.
        if family_member_id is None:
            self_row = get_or_create_family_member_self(db_session, local_user)
            family_member_id = self_row.id
        account = Account(
            user_id=local_user.id,
            institution_id=institution.id,
            account_name=account_name,
            account_type=account_type,
            current_balance=current_balance,
            is_active=True,
            family_member_id=family_member_id,
            **kwargs,
        )
        return account

    return _factory


@pytest.fixture
def make_transaction(db_session):
    """Return a factory that creates a ``Transaction`` row."""
    from datetime import datetime, timezone

    from app.models import Transaction

    def _factory(
        account_id: int,
        description: str = "Test Transaction",
        amount: float = -10.0,
        transaction_date: datetime = None,
        merchant_name: str = None,
        category_id: int = None,
        debit: float | None = None,
        credit: float | None = None,
        **kwargs,
    ) -> Transaction:
        # Phase 52+ — dual-column debit/credit support. When the
        # test passes a single signed `amount` without explicit
        # debit/credit values, derive the unsigned-positive split
        # so a fixture like ``make_transaction(amount=-50)``
        # produces a row the new type-aware
        # ``recalculate_account_balance`` can read (no NULL
        # columns). Explicit `debit=` / `credit=` parameters
        # bypass the auto-derive so a test can assert
        # split-column-specific behaviour (e.g. an FX-neutral
        # zero-amount row that needs both columns NULL).
        if debit is None and credit is None:
            if amount > 0:
                credit = float(amount)
            elif amount < 0:
                debit = float(-amount)
            # amount == 0 leaves both NULL (FX-neutral row)
        local_user = _ensure_local_user(db_session)
        t = Transaction(
            account_id=account_id,
            description=description,
            amount=amount,
            debit=debit,
            credit=credit,
            transaction_date=transaction_date
            or datetime.now(timezone.utc),
            merchant_name=merchant_name,
            category_id=category_id,
            **kwargs,
        )
        return t

    return _factory


@pytest.fixture
def make_goal(db_session):
    """Return a factory that creates a ``Goal`` row."""
    from app.models import Goal

    def _factory(
        name: str = "Test Goal",
        target_amount: float = 10000.0,
        priority: int = 0,
        is_archived: bool = False,
        **kwargs,
    ) -> Goal:
        local_user = _ensure_local_user(db_session)
        return Goal(
            user_id=local_user.id,
            name=name,
            target_amount=target_amount,
            priority=priority,
            is_archived=is_archived,
            **kwargs,
        )

    return _factory


@pytest.fixture
def make_category(db_session):
    """Return a factory that creates a ``Category`` row.

    Phase 44 fixture — Transaction has ``category_id`` (FK to
    ``categories.id``); there's no denormalized ``category_name``
    column on Transaction. Tests that previously seeded transactions
    with a fake ``category_name`` attribute would silently break the
    dashboard chart endpoints (which read ``t.category.name`` via the
    joined relation), so this factory exists so tests can wire a real
    ``Category`` row and then attach it to a Transaction via
    ``category_id=<row.id>``.

    Conftest conventions preserved: factory returns the ORM row but
    does NOT auto-commit, matching ``make_account`` /
    ``make_transaction`` / ``make_goal`` / ``make_family_member``.
    Tests call ``db_session.add(row); db_session.commit()`` after.

    NOTE: ``Category.name`` is UNIQUE in the model (Phase 3 lift
    contract). Test bodies that call this fixture repeatedly with
    the same ``name`` should expect a UNIQUE violation on the second
    call — that's an intentional trip-wire for the test to re-use
    one Category across multiple Transactions instead of creating
    duplicates.
    """
    from app.models import Category

    def _factory(
        name: str = "Test Category",
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        **kwargs,
    ) -> Category:
        return Category(
            name=name,
            description=description,
            icon=icon,
            color=color,
            **kwargs,
        )

    return _factory


@pytest.fixture
def make_family_member(db_session):
    """Return a factory that creates a ``FamilyMember`` row.

    Phase 16 — the factory is intentionally low-level (returns the
    ORM row, NOT a commit) so the same fixture can seed the row for
    follow-up assertions without committing twice. Existing tests
    that flushed via ``db_session.add`` + ``db_session.commit()``
    continue to work; new tests can ``add`` the returned row then
    ``commit`` directly.
    """
    from app.models import FamilyMember

    def _factory(
        name: str = "Test Member",
        color: str = "#3b82f6",
        is_self: bool = False,
        is_archived: bool = False,
        **kwargs,
    ) -> FamilyMember:
        local_user = _ensure_local_user(db_session)
        return FamilyMember(
            user_id=local_user.id,
            name=name,
            color=color,
            is_self=is_self,
            is_archived=is_archived,
            **kwargs,
        )

    return _factory


def _ensure_local_user(db_session):
    """Helper: get-or-create the local user so factory fixtures don't
    need to wire auth just to seed rows.
    """
    from app.routes.shared import get_or_create_local_user
    return get_or_create_local_user(db_session, "alex")


# -----------------------------------------------------------------
# Phase-F5 forwarder-mocking FIXTURE.
#
# IMPORTANT: this is a pytest.fixture (NOT a plain helper function).
# pytest auto-injects fixtures into test function arguments, but it
# does NOT auto-merge plain helper names from conftest into the
# test module's namespace -- so a plain ``install_finlynq_state_forward``
# here triggers ``NameError`` in tests that call it. The fixture
# form sidesteps that bug.
#
# Phase-F5 lifted the dashboard aggregator into Finlynq (canonical
# store); the rules-service ``/api/dashboard/summary`` route is a
# 5-line httpx forwarder that calls Finlynq over HTTP. In pytest,
# Finlynq is NOT running, so each forwarder contract test stubs
# the ``app.routes.dashboard._forward`` coroutine to return canned
# ``httpx.Response`` objects.
#
# Cross-service integration of the AGGREGATOR lives in
# services/tests/test_state_aggregator_cross_db.py (F5f test).
# THIS fixture is for forwarder WS-contract tests ONLY.
# -----------------------------------------------------------------
@pytest.fixture
def install_finlynq_state_forward(monkeypatch):
    """Return a callable that stubs ``app.routes.dashboard._forward``.

    Tests receive this fixture (auto-injected by pytest) and invoke
    ``install_finlynq_state_forward(canned_response, status_code=200)``
    in their body to install a stub that returns canned JSON.

    Parameters the returned callable accepts
    ----------------------------------------
    canned_response : dict
        The dict the stub serializes as the response body.
    status_code : int, default 200
        The HTTP status to return. Default 200 for happy-path
        tests. Pass 409 / 500 / 302 etc. to exercise the F5d
        envelope-mapping branches.

    Why this is a fixture (not a plain helper)
    ------------------------------------------
    pytest's auto-injection requires fixtures to be declared with
    ``@pytest.fixture``. A plain ``def install_finlynq_state_forward(...)``
    in conftest is callable via ``conftest.install_finlynq_state_forward(...)``
    but tests that reference it BY NAME in their signature
    (``def test_xxx(client, install_finlynq_state_forward):``) get a
    ``fixture not found`` error -- pytest does NOT bring conftest's
    plain helper names into the test module's namespace.
    """
    def _install(canned_response, status_code=200):
        import httpx

        async def _stub(method, path, *, json=None, fc_session=None, authorization=None):
            # method / path / fc_session accepted but ignored; the
            # stub always returns canned. Tests that need 4xx/5xx
            # propagation pass status_code here.
            return httpx.Response(status_code, json=canned_response)

        _stub._canned_response = canned_response  # type: ignore[attr-defined]
        _stub._status_code = status_code  # type: ignore[attr-defined]
        monkeypatch.setattr("app.routes.dashboard._forward", _stub)
        return _stub

    return _install

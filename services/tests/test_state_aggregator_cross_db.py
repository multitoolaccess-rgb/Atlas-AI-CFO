"""Phase-F5 cross-service aggregator test -- third-engine verifier.

Sibling to ``test_cross_db_roundtrip.py`` -- applies the SAME
third-engine pattern to a NEW surface: the Finlynq
``GET /state/summary`` aggregator. The two tests share a sibling
directory (``services/tests/``) outside both service conftest
domains so neither service's per-test reset interferes with the
shared-DB invariant being verified.

Why a separate file (not extending ``test_cross_db_roundtrip.py``):
extending the roundtrip test to also seed users + accounts + goals
+ transactions would dilute invariant clarity. A focused F5f test
reads more cleanly and the pytest-discovery footprint stays low
(+1 test file, +1-2 tests).

Why THREE engine bindings matter (not two):

1. ``FINLYNQ_ENGINE`` - Finlynq's app.database engine; the TestClient
   uses this implicitly when it processes a request.
2. ``ExternalSessionLocal`` - the third engine; reads/writes from
   BIND-SAME-FILE-BUT-INDEPENDENT-CONNECTIONS. Proves a separate
   ``uvicorn`` process (rules-service in production) would observe the
   same rows.
3. (NO rules-service engine binding here - per the Phase-F5 risk
   register: rules-service's conftest ``_reset_test_db`` DELETEs
   FROM shared tables on every per-test reset. If the F5f test
   imported rules-service's ``client`` fixture, the DELETE would
   wipe Finlynq's seed data plus any rows the external engine
   wrote. The F5f test deliberately uses ONLY Finlynq-side
   machinery + the external engine, never rules-service's
   fixtures.)

Test surface:

- ``test_state_summary_third_engine_aggregator_totals_match``
  - F5 invariant: an EXTERNAL ``create_engine`` seeded with
    User + Institution + Account + Goal + Transaction + ImportBatch
    rows is observed by Finlynq's ``GET /state/summary`` with the
    JWT-derived user, and the aggregator sums match.
- ``test_state_summary_401_without_jwt``
  - F5 invariant: ``Depends(require_user)`` on Finlynq's
    ``/state/summary`` rejects requests without a valid JWT cookie.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

# Unique marker so the cross-service write + read can correlate
# without colliding with seed_default_categories's other rows or
# sibling test files in this directory.
_MARKER = f"F5AggregatorMarker.{uuid.uuid4().hex[:8]}"
_LOCAL_USER_SUB = "alex"

# services/tests/conftest.py::pytest_configure already pinned
# TEST_DATABASE_URL to a uniquified shared SQLite path; read it back
# so the F5f test binds the external engine to the SAME file
# Finlynq's TestClient will.
_TEST_URL = os.environ["TEST_DATABASE_URL"]
_TEST_DB_PATH = _TEST_URL.split("sqlite:////", 1)[-1]


# ---- Import Finlynq conftest BEFORE first Finlynq app import --------------
# The conftest pins DATABASE_URL at module-load; we want Finlynq's
# settings.database_url to bind the shared URL (Phase-F2 wiring).
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "finlynq",
    ),
)

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.auth import issue_token  # noqa: E402

# NOTE: importing ``app.main`` triggers Finlynq conftest discovery
# via the sys.path insert above -- specifically Finlynq's conftest
# pins DATABASE_URL + JWT_SECRET + LOCAL_USER and (importantly)
# registers the app.database engine. Importing app.main binds the
# engine to the shared URL synchronously.
from app.database import Base as FinlynqBase  # noqa: E402
from app.database import SessionLocal as FinlynqSessionLocal  # noqa: E402
from app.database import engine as FINLYNQ_ENGINE  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    Goal,
    ImportBatch,
    Institution,
    Transaction,
    User,
)
from app.services.categorizer import seed_default_categories  # noqa: E402


# ---- Bootstrap a CLEAN shared DB for this test file ----------------------
# Drop + create all 8 tables on Finlynq's engine (it owns the schema
# metadata post-F5 lift). The drop_all + create_all mirrors the
# F2 roundtrip test's pattern and isolates this test file from any
# previous test file's state on the shared SQLite file.
FinlynqBase.metadata.drop_all(bind=FINLYNQ_ENGINE)
FinlynqBase.metadata.create_all(bind=FINLYNQ_ENGINE)
with FinlynqSessionLocal() as _seed_session:
    seed_default_categories(_seed_session)

# The EXTERNAL third engine: bound to the SAME shared SQLite URL but
# built at test time so it has no prior knowledge of Finlynq's
# app.database engine. If Phase-F2 wiring drifts (Finlynq's engine
# binds to a different path / Postgres DB / etc.) this engine sees a
# DIFFERENT table state and the cross-service assertions go red.
external_engine = create_engine(
    _TEST_URL,
    future=True,
)
ExternalSessionLocal = sessionmaker(bind=external_engine)


def _build_finlynq_client() -> TestClient:
    """Finlynq TestClient with a valid ``fc_session`` cookie pre-loaded.

    The JWT subject matches settings.local_user (default "alex") so
    ``Depends(require_user)`` accepts the request. The same JWT subject
    seeds the User row via ``_seed_local_user_via_external_engine``
    below -- so the aggregator's WHERE clause finds the rows we write.
    """
    token = issue_token()
    c = TestClient(app)
    c.headers["Cookie"] = f"fc_session={token}"
    return c


def _seed_via_external_engine() -> dict:
    """Seed User + Institution + Account + 2 Transactions + 1 Goal +
    1 ImportBatch through the EXTERNAL third engine, returning the
    user-id the aggregator queries under.

    Order matters:
    - User FIRST (FK root).
    - Institution + Account AFTER User (Account.user_id + Account.institution_id
      both FK-reference rows above).
    - Transaction AFTER Account (account_id FK).
    - ImportBatch AFTER User + Account (user_id + account_id FKs).

    Phase-F5 risk register item: the ``Goal.user_id`` FK is NOT NULL
    no-default; we seed a User row BEFORE the Goal row, otherwise
    SQLite would raise ``IntegrityError: NOT NULL constraint failed``,
    which goes red on this test regardless of Phase-F5 status.
    """
    with ExternalSessionLocal() as s:
        u = User(
            local_user_sub=_LOCAL_USER_SUB,
            email=_LOCAL_USER_SUB,
            hashed_password="auth-via-jwt-cookie-no-password",
            full_name="Alex",
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        user_id = u.id

        inst = Institution(name=f"{_MARKER} Bank")
        s.add(inst)
        s.commit()
        s.refresh(inst)

        acct = Account(
            user_id=user_id,
            institution_id=inst.id,
            account_name=f"{_MARKER} Checking",
            account_type="checking",
            current_balance=1500.50,
            is_active=True,
        )
        s.add(acct)
        s.commit()
        s.refresh(acct)

        goal = Goal(
            user_id=user_id,
            name=f"{_MARKER} Goal",
            target_amount=100000.0,
            priority=1,
            is_archived=False,
        )
        s.add(goal)
        s.commit()

        now = datetime.now(timezone.utc)

        income = Transaction(
            account_id=acct.id,
            description=f"{_MARKER} Payroll",
            amount=2000.0,
            transaction_date=now,
        )
        expense = Transaction(
            account_id=acct.id,
            description=f"{_MARKER} Coffee",
            amount=-25.50,
            transaction_date=now,
        )
        s.add_all([income, expense])

        ib = ImportBatch(
            user_id=user_id,
            account_id=acct.id,
            filename=f"{_MARKER}.pdf",
            file_type="pdf",
            record_count=2,
            processed_at=now,
        )
        s.add(ib)
        s.commit()

    return {"user_id": user_id}


# ---- The actual F5 invariant checks ------------------------------------


def test_state_summary_third_engine_aggregator_totals_match() -> None:
    """Phase-F5 aggregator invariant: rows written through an EXTERNAL
    ``create_engine`` (third engine, never touched Finlynq's
    ``app.database.engine``) are observed by Finlynq's
    ``GET /state/summary`` with the JWT-derived user, and the
    aggregator sums match the seeded values exactly.

    Cross-service invariant: this is the F5 analog of
    ``test_cross_db_roundtrip.py`` -- but applied to the dashboard
    aggregator. If Phase-F2 wiring ever drifts OR Phase-F5 lifting
    leaves rules-service's dashboard forwarder pointing at a stale
    Finlynq endpoint, this test goes red.
    """
    _seed_via_external_engine()

    finlynq_client = _build_finlynq_client()
    response = finlynq_client.get("/state/summary")

    assert response.status_code == 200, (
        f"Finlynq GET /state/summary should return 200 (got "
        f"{response.status_code} {response.text!r}). Either the F5 "
        f"aggregator is broken OR Phase-F2 wiring for the cross-DB "
        f"binding drift (verify DATABASE_URL points at the shared file)."
    )
    body = response.json()

    # Aggregator sums derived from the external seeded rows above.
    assert body["total_balance"] == 1500.50, (
        f"Aggregator total_balance drifted. body={body!r}"
    )
    assert body["total_income_month"] == 2000.0, (
        f"Aggregator total_income_month drifted. body={body!r}"
    )
    assert body["total_expenses_month"] == 25.5, (
        f"Aggregator total_expenses_month drifted (must be abs of "
        f"negative expense). body={body!r}"
    )
    assert body["accounts_count"] == 1, (
        f"Aggregator accounts_count drifted. body={body!r}"
    )
    assert body["transactions_count"] >= 2, (
        f"Aggregator transactions_count must include the two seeded "
        f"Transactions (>= 2). body={body!r}"
    )
    assert body["import_batches_count"] == 1, (
        f"Aggregator import_batches_count drifted. body={body!r}"
    )
    assert body["last_import_at"] is not None, (
        f"Aggregator last_import_at must be populated from the "
        f"processed_at on the seeded ImportBatch. body={body!r}"
    )

    # Goal must surface via the aggregator.
    goals_in_response = body["user_goals"]
    goal_names = {g["name"] for g in goals_in_response}
    f5_marker_goal = f"{_MARKER} Goal"
    assert f5_marker_goal in goal_names, (
        f"Aggregator must surface the seeded goal via the external "
        f"engine's row. goals={[g['name'] for g in goals_in_response]!r}"
    )

    # Goal row must be coerced into GoalSummary (not raw dict with
    # extra fields). Spot-check 3 invariants.
    for g in goals_in_response:
        if g["name"] != f5_marker_goal:
            continue
        assert g["target_amount"] == 100000.0, g
        assert g["priority"] == 1, g
        assert g["is_archived"] is False, g


def test_state_summary_401_without_jwt() -> None:
    """Phase-F5 forwarder dep invariant: ``Depends(require_user)`` on
    Finlynq's ``/state/summary`` rejects requests without a valid
    JWT cookie.

    Tests the deps spec directly via Finlynq's TestClient rather than
    through rules-service's forwarder to pin the Finlynq-surface state
    (rules-service's forwarder also propagates the 401 verbatim, but
    that's covered by rules-service's auth tests).
    """
    no_auth_client = TestClient(app)  # no cookie attached
    response = no_auth_client.get("/state/summary")
    assert response.status_code == 401, (
        f"GET /state/summary without a valid JWT cookie must return "
        f"401 (got {response.status_code} {response.text!r}). F5 added "
        f"Depends(require_user) BEHIND the real aggregator precisely "
        f"to lock 401-on-no-cookie."
    )


# ---- Cleanup ----------------------------------------------------------------
# Mirror test_cross_db_roundtrip.py's safety: dispose the EXTERNAL
# engine to clean up the in-memory connection pool before
# pytest_unconfigure drops the temp SQLite file at session end.
def _teardown_dispose_external_engine() -> None:
    try:
        external_engine.dispose()
    except Exception:  # pragma: no cover  -- best-effort cleanup
        pass


import atexit  # noqa: E402

atexit.register(_teardown_dispose_external_engine)

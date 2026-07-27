"""Phase-F2 cross-service integration test — second-engine verifier.

Why this lives OUTSIDE services/finlynq/tests/ and OUTSIDE
services/rules-service/tests/
==============================================================

Both services' conftests bind their own ``app.database.engine`` AT
FIRST IMPORT (``from app.config import settings`` -> ``database_url``
-> ``create_engine``). Once pytest has imported either conftest, the
respective service's engine is locked to whatever URL that conftest
pinned.

To prove the Phase-F2 shared-DB invariant end-to-end we need a
**third engine** that binds to the same shared URL independently of
both services. Doing this from either service's test directory would
import one of the conftests first + side-effect-bind that service's
engine, polluting the test environment.

This file lives in ``services/tests/`` (a sibling directory, NOT a
test inside either service). It runs as a standalone TestClient +
external ``create_engine(test_url)`` pair:

1. ``services/tests/conftest.py::pytest_configure`` runs FIRST at
   session start and pins ``DATABASE_URL`` + ``TEST_DATABASE_URL`` to
   a uniquified shared SQLite path.
2. A Finlynq ``TestClient(app)`` is instantiated — this binds
   Finlynq's app.database.engine to the shared URL.
3. An EXTERNAL ``create_engine(shared_url)`` is instantiated — this
   is a SEPARATE Python engine, the same way a separate ``uvicorn``
   process would.
4. A POST is fired; an EXTERNAL ``Session`` reads the row.

Two engines, one file, one row — the canonical-store invariant.

Phase-F2 #1 round-1 fix: the previous version of this file wrote
``os.environ["DATABASE_URL"]`` AT MODULE IMPORT time, which is
fragile under pytest's collection ordering (a sibling rules-service
or finlynq test file collected BEFORE this one would side-effect-bind
its engine first and miss the shared URL pin). The pinning now lives
in ``services/tests/conftest.py::pytest_configure`` which runs ONCE
at session start BEFORE any test module imports execute.
"""

import os
import sys
import uuid

# Unique marker so the cross-service write + read can correlate
# without colliding with seed_default_categories's other rows.
_MARKER = f"CrossEngineMarker.{uuid.uuid4().hex[:8]}"

# Read the env vars the conftest hook already set so we don't have
# to pin them again (and risk divergence). Both vars point to the
# same uniquified temp SQLite path /tmp/fc-cross-engine-<pid>-<uuid>.db.
_TEST_URL = os.environ["TEST_DATABASE_URL"]
_TEST_DB_PATH = _TEST_URL.split("sqlite:////", 1)[-1]

# ---- Import Finlynq conftest BEFORE first Finlynq app import --------------
# The conftest pins DATABASE_URL at module-load; we want that to see our
# shared URL (above) and bind its engine accordingly.
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
from app.database import Base as FinlynqBase  # noqa: E402
from app.database import SessionLocal as FinlynqSessionLocal  # noqa: E402
from app.database import engine as FINLYNQ_ENGINE  # noqa: E402  (for cleanup)
from app.main import app  # noqa: E402
from app.models import Category  # noqa: E402
from app.services.categorizer import seed_default_categories  # noqa: E402

# ---- Bootstrap a CLEAN shared DB for the test -----------------------------
# Drop + create all tables on Finlynq's engine (it wrote the schema).
# Both engines below see the SAME files on disk; drop_all + create_all
# on Finlynq's engine ALSO clears any tables the external engine would
# see afterwards (they share the catalog).
FinlynqBase.metadata.drop_all(bind=FINLYNQ_ENGINE)
FinlynqBase.metadata.create_all(bind=FINLYNQ_ENGINE)
with FinlynqSessionLocal() as _seed_session:
    seed_default_categories(_seed_session)

# Build the EXTERNAL second engine to prove the cross-service invariant.
# ``create_engine(url)`` is what a SECOND service process would do
# (Finlynq boots with its own engine; rules-service would do the same
# bound to the same URL via the F2 shared-DB wiring). The fact that
# this second engine observes the SAME rows as Finlynq's TestClient
# is what the test LOCKS.
external_engine = create_engine(
    _TEST_URL,
    future=True,
)
ExternalSessionLocal = sessionmaker(bind=external_engine)


def _build_finlynq_client() -> TestClient:
    token = issue_token()
    client = TestClient(app)
    client.headers["Cookie"] = f"fc_session={token}"
    return client


# ---- The actual cross-service invariant check -----------------------------
def test_post_category_visible_via_external_engine_bound_to_same_url() -> None:
    """Phase-F2 sanity check: a Category written via Finlynq's TestClient
    (which commits through Finlynq's app.database.engine) is observable
    via an EXTERNAL ``create_engine(...)`` session bound to the SAME
    SQLite URL but constructed from scratch at test time. This mirrors the
    way a separate ``uvicorn`` rules-service process would observe the
    same row in production (Postgres or shared-volume SQLite).

    Critical contract: if Phase-F2 wiring ever drifts (Finlynq's engine
    binds to a different path / different Postgres DB / etc.), this
    test goes red because the external engine reads an empty
    ``categories`` table.
    """
    payload = {
        "name": _MARKER,
        "description": "Phase-F2 cross-engine invariant lock.",
        "icon": "link",
        "color": "#999999",
    }
    finlynq_client = _build_finlynq_client()
    write_resp = finlynq_client.post("/categories", json=payload)
    assert write_resp.status_code == 201, (
        f"Finlynq POST /categories should return 201 (got "
        f"{write_resp.status_code} {write_resp.text!r})"
    )

    # The cross-service read: an EXTERNAL ``create_engine`` session
    # built AT TEST TIME that has never touched Finlynq's app.database
    # engine module. If the row is NOT visible here, the Phase-F2
    # invariant is broken at the OS-file level.
    with ExternalSessionLocal() as external_session:
        external_row = (
            external_session.query(Category)
            .filter(Category.name == _MARKER)
            .first()
        )
    assert external_row is not None, (
        f"Phase-F2 cross-service invariant BROKEN: Finlynq TestClient "
        f"committed a row named {_MARKER!r} but the EXTERNAL engine "
        f"bound to the same URL observes an empty categories table. "
        f"Verify DATABASE_URL + the shared-DB wiring (file path "
        f"mounting in docker-compose, Postgres DB name in CI)."
    )
    assert external_row.description == payload["description"]
    assert external_row.icon == payload["icon"]
    assert external_row.color == payload["color"]


def test_get_categories_lists_row_written_via_finlynq() -> None:
    """Round-trip via Finlynq's own GET /categories router.

    After the external-engine write above, Finlynq's HTTP list
    endpoint must observe the same row. This is the contract
    ``test_routes_categories.py`` (Phase F4) relies on from
    rules-service's forwarder — without this, the cross-service
    forwarder is dead on arrival.
    """
    finlynq_client = _build_finlynq_client()
    list_resp = finlynq_client.get("/categories")
    assert list_resp.status_code == 200
    listed_names = {row["name"] for row in list_resp.json()}
    assert _MARKER in listed_names, (
        f"Finlynq GET /categories must observe {_MARKER!r}; "
        f"observed names: {sorted(listed_names)!r}"
    )


# ---- Cleanup ----------------------------------------------------------------
# The conftest's ``pytest_unconfigure`` hook owns dropping the temp
# SQLite file at session end. We just dispose the EXTERNAL engine so
# the in-memory connection pool cleans up reliably before the file
# removal runs.
def _teardown_dispose_external_engine():
    try:
        external_engine.dispose()
    except Exception:  # pragma: no cover  -- best-effort cleanup
        pass


import atexit  # noqa: E402

atexit.register(_teardown_dispose_external_engine)

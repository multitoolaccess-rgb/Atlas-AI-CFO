"""Phase-F4 forwarder tests — rules-service's /api/categories/* now
POSTs everything to Finlynq's canonical store.

The pre-F4 tests asserted DB-write semantics directly on rules-service's
``categories`` table; those invariants no longer hold because the
canonical store moved to Finlynq. Today's tests assert the CROSS-SERVICE
WIRE-SHAPE: rules-service's forwarder re-emits Finlynq's response
verbatim and surfaces Finlynq's 409 on duplicate names.

This file replaces the F3-pre architecture's tests in this filename;
the new test set mirrors ``services/finlynq/tests/test_categorize_endpoint_contract.py``
so a regression on either side is immediately visible.
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

# Phase-audit: the cross-service forwarder pattern this file tests was
# abandoned. ``app.routes.categories`` was rewritten to local ORM CRUD
# (no ``httpx.AsyncClient.request`` symbol on the module — the test
# raises ``AttributeError: module 'app.routes.categories' has no attribute
# 'httpx'`` at runtime). The /api/categories/ endpoints now read/write
# ``categories`` directly via SQLAlchemy; their contract is locked by
# ``services/rules-service/tests/test_categories_local_orm.py`` (added
# post-rewrite) plus the route's own unit-test file when needed. Skip
# the file rather than executing the dead-shape assertions.
pytestmark = pytest.mark.skip(
    reason="Cross-service forwarder pattern abandoned; routes/categories uses local ORM via /api/categories/. Replacement coverage: test_categories_local_orm.py."
)


_FAKE_FINLYNQ_LIST = [
    {"id": 1, "name": "Food & Dining", "description": "Restaurants", "icon": "🍽️", "color": "#f97316"},
    {"id": 2, "name": "Groceries", "description": "Supermarkets", "icon": "🛒", "color": "#10b981"},
]


def _stub_async_response(status_code: int, body):
    """Build an AsyncMock returning ``body`` with the given status."""
    fake_response = MagicMock()
    fake_response.status_code = status_code
    fake_response.json = MagicMock(return_value=body)
    async_mock = AsyncMock(return_value=fake_response)
    return async_mock


# -----------------------------------------------------------------
# GET /api/categories/ — forwarder round-trip
# -----------------------------------------------------------------


def test_categories_list_forwards_to_finlynq(client):
    """Phase-F4 forwarder-shape assertion: GET /api/categories/ on
    rules-service asks Finlynq's ``GET /categories`` and re-emits the
    list verbatim."""
    with patch(
        "app.routes.categories.httpx.AsyncClient.request",
        new=_stub_async_response(200, _FAKE_FINLYNQ_LIST),
    ):
        r = client.get("/api/categories/")
    assert r.status_code == 200, f"unexpected: {r.status_code} {r.text}"
    body = r.json()
    assert body == _FAKE_FINLYNQ_LIST, (
        f"forwarder must re-emit Finlynq's list verbatim (got {body})"
    )


def test_categories_post_forwards_payload_and_propagates_201(client):
    """Phase-F4 forwarder-shape assertion: POST /api/categories/ on
    rules-service POSTs the same body to Finlynq's ``POST /categories``
    and re-emits the 201 + row.
    """
    payload = {
        "name": "Pet Care 33",
        "description": "Vet, food, grooming",
        "icon": "⚓",
        "color": "#22c55e",
    }
    response_body = {
        "id": 99,
        "name": "Pet Care 33",
        "description": "Vet, food, grooming",
        "icon": "⚓",
        "color": "#22c55e",
    }
    async_mock = _stub_async_response(201, response_body)

    with patch("app.routes.categories.httpx.AsyncClient.request", new=async_mock):
        r = client.post("/api/categories/", json=payload)

    assert r.status_code == 201
    assert r.json() == response_body
    call_args = async_mock.call_args
    assert call_args.args[0] == "POST"
    assert call_args.args[1].endswith("/categories"), (
        f"forwarder POSTed to {call_args.args[1]!r}; expected to end with /categories"
    )
    assert call_args.kwargs["json"] == payload, (
        f"forwarder must POST the user-supplied payload verbatim (got {call_args.kwargs.get('json')})"
    )


def test_categories_post_propagates_409_on_duplicate_name(client):
    """Phase-F4 idempotency contract: a 409 from Finlynq propagates
    verbatim — the FE sees the same "already exists" detail whether
    the request hits Finlynq directly or via rules-service's
    forwarder.
    """
    payload = {"name": "Dupes", "icon": "🧪", "color": "#ffffff"}
    async_mock = _stub_async_response(
        409,
        {"detail": "A category with that name already exists."},
    )

    with patch("app.routes.categories.httpx.AsyncClient.request", new=async_mock):
        r = client.post("/api/categories/", json=payload)

    assert r.status_code == 409, (
        f"forwarder must propagate Finlynq's 409 unchanged (got {r.status_code} {r.text})"
    )
    assert "exists" in str(r.json().get("detail", "")).lower()


def test_categories_put_forwards_partial_patch_and_propagates_200(client):
    """Phase-F4 forwarder-shape assertion: PUT /api/categories/{id} on
    rules-service PUTs to Finlynq's ``PUT /categories/{id}`` and
    forwards ``None``-stripped payload.
    """
    payload = {"name": "Other / Misc 44", "color": "#0ea5e9"}
    response_body = {
        "id": 12,
        "name": "Other / Misc 44",
        "description": "Unmatched transactions",
        "icon": "❓",
        "color": "#0ea5e9",
    }
    async_mock = _stub_async_response(200, response_body)

    with patch("app.routes.categories.httpx.AsyncClient.request", new=async_mock):
        r = client.put("/api/categories/12", json=payload)

    assert r.status_code == 200
    assert r.json() == response_body
    call_kwargs = async_mock.call_args.kwargs
    assert "name" in call_kwargs["json"]
    assert "color" in call_kwargs["json"]
    # None-strip semantics — description must NOT be forwarded when the
    # caller didn't set it.
    assert "description" not in call_kwargs["json"], (
        "forwarder must NOT forward None fields (the FE's partial-PUT "
        f"ships the change-set only; got {call_kwargs['json']!r})"
    )


# -----------------------------------------------------------------
# AUTH — the forwarder must still require auth
# -----------------------------------------------------------------


def test_categories_list_requires_auth(client_no_auth):
    """Phase-F4 hardening: the forwarder surface keeps the auth dep
    even though it delegates to Finlynq. An unauth request gets 401
    BEFORE the httpx POST fires (so a malicious client cannot
    bypass rules-service's auth by spoofing the forwarder URL).
    """
    r = client_no_auth.get("/api/categories/")
    assert r.status_code == 401


def test_categories_post_requires_auth(client_no_auth):
    r = client_no_auth.post("/api/categories/", json={"name": "X"})
    assert r.status_code == 401


def test_categories_put_requires_auth(client_no_auth):
    r = client_no_auth.put("/api/categories/1", json={"name": "X"})
    assert r.status_code == 401


# Fixtures
@pytest.fixture
def client():
    """TestClient with a valid ``fc_session`` cookie pre-loaded so
    ``Depends(require_user)`` accepts the request and the forwarder
    fires. No DB reset / no module-scope bootstrap — the forwarder
    routes don't touch rules-service's DB.
    """
    from app.auth import issue_token
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    c.headers["Cookie"] = f"fc_session={issue_token()}"
    return c


@pytest.fixture
def client_no_auth():
    """TestClient with NO auth cookie — the forwarder must reject
    unauth requests at 401 BEFORE the httpx forward fires.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)

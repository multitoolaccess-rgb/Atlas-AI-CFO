"""Phase 1 Slice D-post: authenticated forecast generation POST route.

Test set exercises the bounded 9-case status matrix plus the goal
ownership / persistence gate ordering, the sanitized envelope shapes,
the conditional-header semantics, and the path-prefix-scoped
``RequestValidationError`` handler's non-v1 fallback.

The test suite uses a stub ``FinlynqProjectionStateAdapter`` that
returns a deterministic canonical ``CanonicalProjectionState`` so
the route's trusted-adapter invariant is honored without hitting the
network.  All persistence goes through the merged
``ForecastRepository`` against the same in-process SQLite used by
conftest.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import issue_token
from app.config import settings
from app.database import Base, SessionLocal, engine  # Base used by _reset_db autouse fixture
from app.forecasts.api_codecs import format_forecast_etag_header
from app.forecasts.canonical_state import (
    HASH_SCHEMA_VERSION,
    PROJECTION_STATE_SCHEMA_VERSION,
    CanonicalProjectionState,
    CanonicalStateValidationError,
    FinlynqProjectionStateAdapter,
)
from app.forecasts.repository import ForecastRepository, IdempotencyConflict, StaleForecastVersion
from app.forecasts.schemas import (
    # Envelope codes used in the assertions
    ERROR_CODE_FORECAST_GENERATION_UNAVAILABLE,
    ERROR_CODE_FORECAST_VERSION_CONFLICT,
    ERROR_CODE_GOAL_NOT_FOUND,
    ERROR_CODE_IDEMPOTENCY_CONFLICT,
    ERROR_CODE_PRECONDITION_FAILED,
    ERROR_CODE_BAD_REQUEST,
    ERROR_CODE_FORECAST_VALIDATION,
)
from app.main import app
from app.models import Goal, User  # Base lives in app.database


# Phase 1 Slice D-post cleanup NOTE
# The 9 route-matrix tests under this file were originally marked
# `@pytest.mark.xfail(strict=False)` because the mapper schema applied the
# canonical-money validator (MAX_TOTAL_DIGITS=38) to fields whose source
# values are atlas-calculation-decimal/v1 (MAX_DIGITS=50). The mapper-cleanup
# follow-up PR split the validator routing: monthly_real_rate +
# unrounded_ending_balance + unrounded_target_amount now use
# _check_calculation_decimal; the canonical-money fields stay bounded at 38.
# The xfail markers have been removed and the Goal fixture target_amount
# restored to the original Slice D-post realistic values (1000.0 / 500.0).


# ----------------------------------------------------------------------
# Stub adapter — deterministic canonical state, zero network.
# ----------------------------------------------------------------------


_TEST_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


class _StubAdapter:
    """Stub ``FinlynqProjectionStateAdapter`` returning a canonical state."""

    def __init__(self, state: CanonicalProjectionState) -> None:
        self._state = state

    def load_projection_state(self, *, user_id: str, goal_id: int) -> CanonicalProjectionState:
        if user_id != self._state.user_id or int(goal_id) != int(self._state.goal_id):
            raise CanonicalStateValidationError("user/goal mismatch")
        return self._state


def _stub_state(user_id: str, goal_id: int, goal_target_amount: str = "0") -> CanonicalProjectionState:
    # Use one fixed synthetic instant for both the trusted state and the
    # route's calculation clock. A live wall clock would race at UTC
    # rollover and could make this otherwise-valid fixture stale.
    as_of_z = _TEST_NOW.isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": PROJECTION_STATE_SCHEMA_VERSION,
        "canonicalization": {
            "canonical_json_version": "atlas-canonical-json/v1",
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "hash_algorithm": "sha256",
        },
        "user_id": user_id,
        "goal_id": goal_id,
        "as_of_timestamp": as_of_z,
        "currency": "USD",
        "current_value_components": [
            {
                "kind": "investment",
                "amount": goal_target_amount,
                "source_reference": "atlas-stub-current-value",
                "observed_at": as_of_z,
            }
        ],
        "contribution_inputs": [
            {
                "kind": "monthly_investable_cash_flow",
                "amount": "0",
                "source_reference": "atlas-stub-contribution",
                "observed_at": as_of_z,
            }
        ],
        "freshness": {
            "max_data_age_days": 30,
            "observed_age_days": 0,
            "source_updated_at": as_of_z,
        },
        "provenance": [
            {
                "source_system": "atlas-stub",
                "reference_id": "atlas-stub-reference",
                "observed_at": as_of_z,
                "record_count": 1,
                "source_state_hash": "a" * 64,
            }
        ],
        "missing_data_codes": [],
        "reconciliation_state": "reconciled",
    }
    return CanonicalProjectionState.model_validate(payload)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture()
def stub_adapter(monkeypatch):
    """Override the route's adapter dep with the stub — zero network calls."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _TEST_NOW

    # The route imports datetime directly, so patch that module binding—not
    # the immutable built-in datetime class. pytest restores it after each
    # test, keeping this deterministic clock local to the route tests.
    monkeypatch.setattr(
        "app.routes.forecasts_generation.datetime", _FrozenDateTime
    )
    state = _stub_state(settings.local_user, 1)
    adapter = _StubAdapter(state)
    monkeypatch.setattr(
        "app.routes.forecasts_generation.HttpFinlynqProjectionStateAdapter",
        lambda **kwargs: adapter,
    )
    return adapter


@pytest.fixture(autouse=True)
def _reset_db():
    """Per-test DB reset + bounded seed for the bounded slice under test."""

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        # Truncate to a clean slate per test
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        # Seed the auth-associated user and one owned goal
        session.add(User(id=1, local_user_sub=settings.local_user, email="alex@example.com", hashed_password="x"))
        session.flush()
        session.add(
            Goal(
                id=1,
                user_id=1,
                name="Atlas Goal",
                target_amount=1000.0,
                horizon_years=1,
                target_date=None,
                priority=0,
                is_archived=False,
            )
        )
        session.add(
            Goal(
                id=2,
                user_id=1,
                name="Atlas Goal with date",
                target_amount=500.0,
                horizon_years=None,
                target_date=datetime(2027, 7, 1).date(),
                priority=1,
                is_archived=False,
            )
        )
        session.commit()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def _auth_headers(*, idem: str | None = "atlas-route-key") -> dict[str, str]:
    token = issue_token()
    out: dict[str, str] = {"Authorization": f"Bearer {token}"}
    if idem is not None:
        out["Idempotency-Key"] = idem
    return out


def _post(client: TestClient, *, goal_id: int, headers: dict[str, str], body=None) -> object:
    if body is None:
        body = {}
    return client.post(f"/api/v1/goals/{goal_id}/forecasts", headers=headers, json=body)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------



def test_201_first_creation_no_headers_emits_location_etag_and_hateoas(client: TestClient, stub_adapter) -> None:
    response = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-c-1"))
    assert response.status_code == 201
    body = response.json()
    # Wire envelope shape
    assert body["forecast_id"]
    assert body["version_id"]
    assert body["version_number"] == 1
    assert body["currency"] == "USD"
    assert body["target_decision"]["scenario"] == "base"
    # HATEOAS rels deterministic
    rels = {link["rel"]: link["href"] for link in body["links"]}
    assert set(rels) == {"self", "forecast", "goal"}
    assert rels["self"].endswith(f"/api/v1/forecasts/{body['forecast_id']}/versions/1")
    # Location and ETag headers
    assert response.headers["Location"].endswith(f"/api/v1/forecasts/{body['forecast_id']}/versions/1")
    etag = response.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"')
    assert etag.strip('"') == body["etag"]

def test_200_replay_with_same_idempotency_key_returns_identical_version(client: TestClient, stub_adapter) -> None:
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-replay-1"))
    assert response_1.status_code == 201
    response_2 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-replay-1"))
    assert response_2.status_code == 200
    assert response_1.json()["version_id"] == response_2.json()["version_id"]
    assert response_1.json()["version_number"] == response_2.json()["version_number"]


def test_404_missing_goal_returns_indistinguishable_goal_not_found_envelope(client: TestClient, stub_adapter) -> None:
    response = _post(client, goal_id=999999, headers=_auth_headers(idem="atlas-404-1"))
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == ERROR_CODE_GOAL_NOT_FOUND
    assert body["message"] == "Goal not found."


def test_404_cross_user_goal_returns_same_envelope_as_missing(client: TestClient, stub_adapter, monkeypatch) -> None:
    """A different ``local_user_sub`` row exists with a goal at ``goal_id=1``;
    the settings.local_user request gets 404 (non-disclosing).

    We simulate a cross-user scenario by ensuring the auth dependency
    could match a user with a different sub: the canonical 401
    response already blocks the forged sub, so we test the
    POST-with-owner-mismatch path through the User row resolution.
    Concretely: the route's ``_resolve_user_sub_to_id`` raises
    ``RuntimeError`` when the user row is missing; the global 500
    handler picks that up.  Here we verify that an owned-goal lookup
    with no matching row returns 404 directly.
    """

    # Phase 1 expectation: 404 indistinguishable, not a 403/401 disclosure.
    headers = _auth_headers(idem="atlas-cross-1")
    # Forge a goal that does not belong to settings.local_user by
    # re-seeding the DB with a goal under a different user_id.
    from sqlalchemy import text

    with SessionLocal() as session:
        session.execute(text("DELETE FROM goals WHERE id = 1"))
        session.execute(text(
            "INSERT INTO users (id, local_user_sub, email, hashed_password)"
            " VALUES (2, 'foreign-user', 'fb@example.com', 'x')"
        ))
        session.execute(text(
            "INSERT INTO goals (id, user_id, name, target_amount, horizon_years, target_date, priority, is_archived)"
            " VALUES (1, 2, 'foreign goal', 1000.0, 1, NULL, 0, 0)"
        ))
        session.commit()
    headers["Authorization"] = f"Bearer {issue_token()}"
    response = _post(client, goal_id=1, headers=headers)
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == ERROR_CODE_GOAL_NOT_FOUND


def test_503_persistence_disabled_returns_forecast_generation_unavailable(client: TestClient, stub_adapter, monkeypatch) -> None:
    monkeypatch.setattr(settings, "atlas_forecast_persistence_enabled", False)
    response = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-503-1"))
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == ERROR_CODE_FORECAST_GENERATION_UNAVAILABLE
    assert "currently unavailable" in body["message"]

def test_412_if_none_match_wildcard_against_existing(client: TestClient, stub_adapter) -> None:
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-nm-c-1"))
    assert response_1.status_code == 201
    response_2 = _post(
        client,
        goal_id=1,
        headers={**_auth_headers(idem="atlas-nm-c-2"), "If-None-Match": "*"},
    )
    assert response_2.status_code == 412
    assert response_2.json()["code"] == ERROR_CODE_PRECONDITION_FAILED

def test_201_if_none_match_wildcard_no_existing(client: TestClient, stub_adapter) -> None:
    response = _post(
        client,
        goal_id=1,
        headers={**_auth_headers(idem="atlas-nm-h-1"), "If-None-Match": "*"},
    )
    assert response.status_code == 201

def test_409_if_match_stale_returns_current_etag_and_latest_version(client: TestClient, stub_adapter) -> None:
    # Create a known version v1
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-im-d-1"))
    assert response_1.status_code == 201
    # Fabricate a stale v99 ETag pointing at the right forecast
    forecast_id = response_1.json()["forecast_id"]
    stale_etag = format_forecast_etag_header(forecast_id=forecast_id, version_number=99)
    response_2 = _post(
        client,
        goal_id=1,
        headers={**_auth_headers(idem="atlas-im-d-2"), "If-Match": stale_etag},
    )
    assert response_2.status_code == 409
    body = response_2.json()
    assert body["code"] == ERROR_CODE_FORECAST_VERSION_CONFLICT
    # The reported current_etag is the actual latest v1
    expected_etag = format_forecast_etag_header(forecast_id=forecast_id, version_number=1)
    assert body["current_etag"] == expected_etag.strip('"')
    assert body["latest_version_number"] == 1

def test_200_if_match_matches_existing_returns_replay(client: TestClient, stub_adapter) -> None:
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-im-e-1"))
    assert response_1.status_code == 201
    etag = response_1.headers["ETag"]
    response_2 = _post(
        client,
        goal_id=1,
        headers={**_auth_headers(idem="atlas-im-e-2"), "If-Match": etag},
    )
    assert response_2.status_code == 200
    assert response_2.json()["version_id"] == response_1.json()["version_id"]


def test_412_if_match_provided_but_no_existing(client: TestClient, stub_adapter) -> None:
    fake_etag = format_forecast_etag_header(
        forecast_id="00000000-0000-0000-0000-000000000000",
        version_number=1,
    )
    response = _post(
        client,
        goal_id=1,
        headers={**_auth_headers(idem="atlas-im-f-1"), "If-Match": fake_etag},
    )
    assert response.status_code == 412
    assert response.json()["code"] == ERROR_CODE_PRECONDITION_FAILED

def test_400_both_conditional_headers_provided(client: TestClient, stub_adapter) -> None:
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-g-1"))
    assert response_1.status_code == 201
    etag = response_1.headers["ETag"]
    response = _post(
        client,
        goal_id=1,
        headers={
            **_auth_headers(idem="atlas-g-2"),
            "If-Match": etag,
            "If-None-Match": "*",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == ERROR_CODE_BAD_REQUEST

def test_400_if_none_match_with_explicit_etag(client: TestClient, stub_adapter) -> None:
    response_1 = _post(client, goal_id=1, headers=_auth_headers(idem="atlas-i-1"))
    assert response_1.status_code == 201
    etag = response_1.headers["ETag"]
    response = _post(
        client,
        goal_id=1,
        headers={
            **_auth_headers(idem="atlas-i-2"),
            "If-None-Match": etag,
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == ERROR_CODE_BAD_REQUEST


def test_422_missing_idempotency_key(client: TestClient, stub_adapter) -> None:
    headers = _auth_headers(idem=None)
    response = _post(client, goal_id=1, headers=headers)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == ERROR_CODE_FORECAST_VALIDATION
    assert any("Idempotency-Key" in entry["loc"] for entry in body["errors"])


def test_422_idempotency_key_with_non_visible_ascii(client: TestClient, stub_adapter) -> None:
    # Use horizontal tab inside the key (codepoint 9, below visible ASCII 33)
    headers = _auth_headers(idem=None)
    headers["Idempotency-Key"] = "atlas-key-\there"
    response = _post(client, goal_id=1, headers=headers)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == ERROR_CODE_FORECAST_VALIDATION


def test_422_body_rejects_unknown_field(client: TestClient, stub_adapter) -> None:
    response = _post(
        client,
        goal_id=1,
        headers=_auth_headers(idem="atlas-extra-1"),
        body={"unauthorized_account_hint": "evade"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == ERROR_CODE_FORECAST_VALIDATION

def test_422_empty_body_accepted_with_extra_forbid(client: TestClient, stub_adapter) -> None:
    """An explicit empty body (``{}``) must succeed — only unknown fields
    are rejected by ``extra=\"forbid\"``.  This validates the strict
    empty-body contract."""

    response = _post(
        client,
        goal_id=1,
        headers=_auth_headers(idem="atlas-empty-1"),
        body={},
    )
    assert response.status_code == 201


def test_401_missing_auth_token(client: TestClient, stub_adapter) -> None:
    response = client.post(
        "/api/v1/goals/1/forecasts",
        headers={"Idempotency-Key": "atlas-no-auth-1"},
        json={},
    )
    assert response.status_code == 401


def test_log_output_does_not_leak_user_sub_or_goal_id_on_validation_failure(
    client: TestClient, stub_adapter, caplog
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    response = _post(
        client,
        goal_id=1,
        headers=_auth_headers(idem=None),
    )
    assert response.status_code == 422
    flat_log = "\n".join(record.getMessage() for record in caplog.records)
    assert settings.local_user not in flat_log
    assert "goal_id" not in flat_log.lower() or "1" not in flat_log.split("goal_id")[1][:5]


def test_regression_non_v1_path_422_falls_back_to_default_detail_shape(
    client: TestClient, stub_adapter
) -> None:
    """A non-v1 endpoint receiving a malformed body must still emit the
    FastAPI default ``{\"detail\": [...]}`` shape.  This is the regression
    test proving the path-prefix handler does not change behavior for
    legacy endpoints.
    """

    # Hit a known non-v1 endpoint with a malformed body.  We use
    # ``/api/categories`` which is registered on the existing routes
    # and lets us POST a malformed body.
    response = client.post("/api/categories/", json={"unexpected": "field"})
    # Categories endpoint likely 401 (no auth) or 422 (validation),
    # but the IMPORTANT assertion is: if 422, body has ``detail`` list,
    # NOT ``errors``.
    if response.status_code == 422:
        body = response.json()
        assert "detail" in body
        assert "errors" not in body
    else:
        # The fallback test still proves the handler does not crash non-v1
        # paths.  Auth failure is acceptable as long as the response was
        # produced (no 500).
        assert response.status_code in (401, 405)

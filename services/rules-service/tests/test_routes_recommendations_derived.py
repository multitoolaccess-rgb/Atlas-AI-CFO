"""Phase 2 Slice 1 commit-4 integration tests for the bounded
``app.routes.recommendations_derived`` routes.

Uses existing conftest fixtures (``client`` with JWT cookie,
``db_session``, ``monkeypatch``, ``make_goal``).  The matrix:

1. ``GET /api/v1/forecasts/{forecast_id}/recommendation``
   - 503 when ``atlas_forecast_read_api_enabled`` is False
   - 200 happy path with envelope shape + ETag header
   - 404 indistinguishability when forecast is missing
   - Idempotent replay returns the same row + envelope

2. ``POST /api/v1/recommendations/{recommendation_id}/decisions``
   - 503 when ``atlas_forecast_read_api_enabled`` is False
   - 422 missing Idempotency-Key header
   - 422 unknown body field (``extra='forbid'``)
   - 422 invalid decision_etag regex
   - 422 missing body
   - 201 happy path with Location + ETag headers
   - 201 idempotent replay is byte-identical
   - 409 cross-row conflict on different payload + same key
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RFC3339_UTC: str = "%Y-%m-%dT%H:%M:%S.%f+00:00"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _build_world(
    db_session,
    *,
    currency: str = "USD",
    user_sub: str = "alex",
    forecast_id: str = "11111111-1111-4111-8111-111111111111",
):
    """Bring up a Forecast + ForecastVersion + (committed) Goal world.

    Returns ``(user, goal, forecast, latest_version)``.  No
    ``Recommendation`` row is created at this layer — the GET route
    is responsible for deriving it on first mint.
    """
    from app.models import Forecast, ForecastVersion, Goal, User
    from app.routes.shared import get_or_create_local_user

    user: User = get_or_create_local_user(db_session, user_sub)

    goal = Goal(
        user_id=user.id,
        name=f"commit4-goal-{currency}",
        target_amount=Decimal("1000.00"),
        priority=0,
        is_archived=False,
    )
    db_session.add(goal)
    db_session.commit()
    db_session.refresh(goal)

    forecast = Forecast(
        id=forecast_id,
        user_id=user.id,
        goal_id=goal.id,
        currency=currency,
    )
    db_session.add(forecast)
    db_session.commit()

    version_id = str(uuid4())
    now = _now_utc()
    version = ForecastVersion(
        id=version_id,
        forecast_id=forecast.id,
        version_number=1,
        model_version="atlas-projection/v1",
        calculation_version="atlas-calculation-decimal/v1",
        snapshot_schema_version="atlas-snapshot/v1",
        hash_schema_version="atlas-hash/v1",
        input_state_hash="0" * 64,
        idempotency_key_hash="0" * 64,
        currency=currency,
        ending_balance=Decimal("1100.00"),
        target_gap=Decimal("0.00"),
        max_data_age_days=30,
        data_age_days=5,
        calculated_at=now,
        data_as_of=now,
        created_at=now,
        assumption_snapshot_json=json.dumps({
            "assumption_schema_version": "atlas-assumption/v1",
            "assumption_profile": "default-profile",
            "annual_return_rates": {
                "conservative": "0.05",
                "base": "0.07",
                "optimistic": "0.09",
            },
            "annual_inflation_rate": "0.02",
            "contribution_timing": "monthly",
            "period": "monthly",
            "rounding_rule": "ROUND_HALF_EVEN",
            "money_precision": "0.01",
            "goal_inputs": {
                "target_amount": "1000",
                "horizon_years": 10,
                "target_date": None,
            },
        }),
        output_snapshot_json=json.dumps({
            "calculation_decimal_schema_version": "atlas-calculation-decimal/v1",
            "target_status": True,
            "target_decision": {
                "schema_version": "atlas-target-decision/v2",
                "rounded_ending_balance": "1100.00",
                "target_amount": "1000.00",
                "currency": "USD",
            },
            "drivers": {
                "schema_version": "atlas-drivers/v1",
                "data_as_of": _rfc3339(now),
                "annual_inflation_rate": "0.02",
            },
            "scenarios": {
                "conservative": {"annual_return_rate": "0.05", "ending_balance": "1050.00"},
                "base": {"annual_return_rate": "0.07", "ending_balance": "1100.00"},
                "optimistic": {"annual_return_rate": "0.09", "ending_balance": "1150.00"},
            },
        }),
        provenance_snapshot_json=json.dumps({
            "provenance": [],
            "freshness": {"schema_version": "atlas-freshness/v1"},
        }),
        input_snapshot_json=json.dumps({}),
    )
    db_session.add(version)
    db_session.commit()

    return user, goal, forecast, version


# ---------------------------------------------------------------------------
# 1. GET /api/v1/forecasts/{forecast_id}/recommendation
# ---------------------------------------------------------------------------


@pytest.fixture
def enable_read_flag(monkeypatch):
    """Default-on helper: per-test turn-on for the read-API gate."""
    monkeypatch.setattr(
        "app.config.settings.atlas_forecast_read_api_enabled", True
    )


def test_get_recommendation_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.atlas_forecast_read_api_enabled", False
    )
    response = client.get(
        "/api/v1/forecasts/11111111-1111-4111-8111-111111111111/recommendation"
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "forecast_read_api_unavailable"


def test_get_recommendation_404_when_forecast_missing(client, enable_read_flag):
    response = client.get(
        "/api/v1/forecasts/22222222-2222-4222-8222-222222222222/recommendation"
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "recommendation_not_found"
    # Same envelope for missing AND cross-user (AC7 indistinguishability)
    assert body["message"] == "Recommendation not found."


def test_get_recommendation_404_when_latest_version_missing(
    client, enable_read_flag, db_session
):
    """404 when forecast exists but no ForecastVersion row under it."""
    from decimal import Decimal

    from app.models import Forecast, Goal, User
    from app.routes.shared import get_or_create_local_user

    user = get_or_create_local_user(db_session, "alex")
    goal = Goal(
        user_id=user.id,
        name="missing-version-goal",
        target_amount=Decimal("1000.00"),
        priority=0,
        is_archived=False,
    )
    db_session.add(goal)
    db_session.commit()
    db_session.refresh(goal)

    forecast = Forecast(
        id="33333333-3333-4333-8333-333333333333",
        user_id=user.id,
        goal_id=goal.id,
        currency="USD",
    )
    db_session.add(forecast)
    db_session.commit()

    response = client.get(
        "/api/v1/forecasts/33333333-3333-4333-8333-333333333333/recommendation"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "recommendation_not_found"


def test_get_recommendation_200_happy_path(
    client, enable_read_flag, db_session
):
    _user, _goal, forecast, _version = _build_world(db_session)
    response = client.get(
        f"/api/v1/forecasts/{forecast.id}/recommendation",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert "etag" in response.headers.get("access-control-expose-headers", "").lower()
    body = response.json()
    assert body["schema_version"] == "atlas-derived-recommendation/v1"
    assert body["recommendation_kind"] in {
        "increase_contribution",
        "rebalance_allocation",
        "extend_horizon",
        "hold",
    }
    assert body["action_verb"] in {"Increase", "Reallocate", "Extend", "Hold"}
    assert body["forecast_id"] == forecast.id
    assert body["forecast_etag"].endswith("-v1")
    assert len(body["assumptions_reference"]) == 64
    assert len(body["evidence_references"]["forecast_id"]) == 36

    # The decision ETag lives in the strong-quoted header form.
    etag = response.headers.get("ETag", "")
    assert etag.startswith('"')
    assert etag.endswith("-d1\"")


def test_get_recommendation_idempotent_replay_returns_same_envelope(
    client, enable_read_flag, db_session
):
    _u, _g, forecast, _v = _build_world(db_session)
    response_1 = client.get(f"/api/v1/forecasts/{forecast.id}/recommendation")
    response_2 = client.get(f"/api/v1/forecasts/{forecast.id}/recommendation")
    assert response_1.status_code == response_2.status_code == 200
    # The envelope is byte-identical (idempotent replay) per the
    # plan AC10 stable-contract expectation.
    assert response_1.json() == response_2.json()


# ---------------------------------------------------------------------------
# 2. POST /api/v1/recommendations/{recommendation_id}/decisions
# ---------------------------------------------------------------------------


def _mint_recommendation(client, db_session, enable_read_flag):
    """Helper: bring up the Forecast world + mint a Recommendation row via
    the GET route, then return ``(forecast, recommendation_id)``.
    """
    _u, _g, forecast, _v = _build_world(db_session)
    response = client.get(f"/api/v1/forecasts/{forecast.id}/recommendation")
    assert response.status_code == 200, response.text
    return forecast


def _recommendation_id_for(client, db_session, enable_read_flag) -> str:
    from app.models import Recommendation

    _u, _g, forecast, _v = _build_world(db_session)
    response = client.get(f"/api/v1/forecasts/{forecast.id}/recommendation")
    assert response.status_code == 200
    rec_id = response.json()["links"][1]["href"].rsplit("/", 2)[-2]
    # Sanity: the canonical Recommendation.id roundtrips through the link href.
    row = db_session.get(Recommendation, rec_id)
    assert row is not None
    return rec_id


def _decision_headers(idempotency_key: str, decision_etag: str) -> dict[str, str]:
    return {
        "Idempotency-Key": idempotency_key,
        "If-Match": f'"{decision_etag}"',
    }


def test_post_decision_422_missing_if_match(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers={"Idempotency-Key": "idemp-missing-if-match"},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["header", "If-Match"]


def test_post_decision_409_when_decision_etag_is_stale(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    stale_etag = f"{rec_id}-d2"
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": stale_etag},
        headers=_decision_headers("idemp-stale-etag", stale_etag),
    )
    assert response.status_code == 409
    assert response.json() == {
        "code": "decision_version_conflict",
        "message": "Decision etag conflict.",
        "current_etag": f"{rec_id}-d1",
    }


def test_post_decision_409_when_if_match_does_not_match_body(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("idemp-mismatched-if-match", f"{rec_id}-d2"),
    )
    assert response.status_code == 409
    assert response.json()["current_etag"] == f"{rec_id}-d1"


def test_post_decision_503_when_disabled(client, monkeypatch, db_session):
    """Disabled-phase POST returns 503 with the canonical envelope.

    The test sets the read-flag ``False`` *AFTER* minting the
    recommendation via GET.  Otherwise pytest's monkeypatch LIFO
    would leave the flag ``False`` for the entire test body and the
    GET inside ``_recommendation_id_for`` would itself return 503.
    """
    monkeypatch.setattr(
        "app.config.settings.atlas_forecast_read_api_enabled", True
    )
    _u, _g, forecast, _v = _build_world(db_session)
    response = client.get(f"/api/v1/forecasts/{forecast.id}/recommendation")
    assert response.status_code == 200, response.text
    rec_id = response.json()["links"][1]["href"].rsplit("/", 2)[-2]
    from app.models import Recommendation
    assert db_session.get(Recommendation, rec_id) is not None

    # Now flip the flag to False and POST — expect 503.
    monkeypatch.setattr(
        "app.config.settings.atlas_forecast_read_api_enabled", False
    )
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("idemp1", f"{rec_id}-d1"),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "forecast_read_api_unavailable"


def test_post_decision_422_missing_idempotency_key(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
    )
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(
        err.get("loc", ())[-1] == "Idempotency-Key" for err in errors
    )


def test_post_decision_422_unknown_body_field(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={
            "action": "accept",
            "decision_etag": f"{rec_id}-d1",
            "extra_field": "forbidden",
        },
        headers={"Idempotency-Key": "idemp-unknown-field"},
    )
    assert response.status_code == 422


def test_post_decision_422_malformed_decision_etag(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": "not-a-decision-etag"},
        headers={"Idempotency-Key": "idemp-malformed-etag"},
    )
    assert response.status_code == 422


def test_post_decision_422_unknown_action(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "YOLO", "decision_etag": f"{rec_id}-d1"},
        headers={"Idempotency-Key": "idemp-bad-action"},
    )
    assert response.status_code == 422


def test_post_decision_422_missing_body(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        headers={"Idempotency-Key": "idemp-no-body"},
    )
    assert response.status_code == 422


def test_post_decision_404_when_recommendation_missing(
    client, enable_read_flag
):
    """Cross-user / missing returns the SAME envelope (AC7)."""
    response = client.post(
        "/api/v1/recommendations/99999999-9999-4999-8999-999999999999/decisions",
        json={"action": "accept", "decision_etag": "99999999-9999-4999-8999-999999999999-d1"},
        headers=_decision_headers("idemp-404", "99999999-9999-4999-8999-999999999999-d1"),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "recommendation_not_found"


def test_post_decision_201_happy_path(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("idemp-happy-path", f"{rec_id}-d1"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["schema_version"] == "atlas-decision-journal-entry/v1"
    assert body["action_taken"] == "accept"
    assert body["decision_etag"].endswith("-d1")
    assert len(body["journal_entry_id"]) == 36
    assert body["recommendation_id"] == rec_id
    # Location + ETag headers present per plan AC5 stable-contract.
    location = response.headers.get("Location", "")
    assert location.startswith("/api/v1/decisions/")
    assert location.endswith(body["journal_entry_id"])
    etag = response.headers.get("ETag", "")
    assert etag.startswith('"')
    assert etag.endswith("-d1\"")


def test_post_decision_201_idempotent_replay_is_identical(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    payload = {
        "action": "accept",
        "decision_etag": f"{rec_id}-d1",
    }
    headers = {"Idempotency-Key": "idemp-replay"}
    response_1 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json=payload, headers={**headers, "If-Match": f'"{rec_id}-d1"'},
    )
    response_2 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json=payload, headers={**headers, "If-Match": f'"{rec_id}-d1"'},
    )
    assert response_1.status_code == 201
    assert response_2.status_code == 201
    # Same journal_entry_id (no double write)
    assert response_1.json()["journal_entry_id"] == response_2.json()["journal_entry_id"]
    # Body byte-identical (deterministic canonical envelope)
    assert response_1.json() == response_2.json()


def test_post_decision_409_cross_row_conflict(
    client, enable_read_flag, db_session
):
    """Same Idempotency-Key + DIFFERENT payload -> ``DecisionConflict``..

    The canonical ``DecisionConflictEnvelope`` carries the current
    bare ``decision_etag`` so the UI can refresh and retry.
    """
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    headers = _decision_headers("idemp-conflict", f"{rec_id}-d1")
    response_1 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={
            "action": "accept",
            "decision_etag": f"{rec_id}-d1",
        },
        headers=headers,
    )
    assert response_1.status_code == 201
    response_2 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={
            "action": "reject",
            "decision_etag": f"{rec_id}-d1",
        },
        headers=headers,
    )
    assert response_2.status_code == 409
    body = response_2.json()
    assert body["code"] == "decision_version_conflict"
    assert body["current_etag"].endswith("-d1")


def test_post_decision_201_replay_then_change_decision_writes_new_row(
    client, enable_read_flag, db_session
):
    """Different idempotency-key + different action: a new row is appended.."""
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    response_1 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("idemp-first-accept", f"{rec_id}-d1"),
    )
    assert response_1.status_code == 201
    response_2 = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "reject", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("idemp-second-reject", f"{rec_id}-d1"),
    )
    assert response_2.status_code == 201
    # Different canonical request -> different journal_entry_id (no replay)
    assert response_1.json()["journal_entry_id"] != response_2.json()["journal_entry_id"]


# ---------------------------------------------------------------------------
# 3. GET /api/v1/recommendations/{recommendation_id}/contract (Phase 3)
# ---------------------------------------------------------------------------


def test_get_recommendation_contract_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.atlas_forecast_read_api_enabled", False
    )
    response = client.get(
        "/api/v1/recommendations/99999999-9999-4999-8999-999999999999/contract"
    )
    assert response.status_code == 503
    assert response.json() == {
        "code": "forecast_read_api_unavailable",
        "message": "Forecast read API is currently disabled.",
    }


def test_get_recommendation_contract_links_goal_evidence_risks_confidence_and_approvals(
    client, enable_read_flag, db_session
):
    """Accepted decisions expose their immutable, privacy-safe linkage."""
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    accepted = client.post(
        f"/api/v1/recommendations/{rec_id}/decisions",
        json={"action": "accept", "decision_etag": f"{rec_id}-d1"},
        headers=_decision_headers("contract-accept", f"{rec_id}-d1"),
    )
    assert accepted.status_code == 201, accepted.text
    decision_id = accepted.json()["journal_entry_id"]

    from app.forecasts.outcome_evaluation_service import OutcomeEvaluationService
    from app.models import Recommendation

    recommendation = db_session.get(Recommendation, rec_id)
    assert recommendation is not None
    now = _now_utc()
    OutcomeEvaluationService(db_session).record(
        user_id=int(recommendation.user_id),
        goal_id=int(recommendation.goal_id),
        recommendation_id=rec_id,
        decision_journal_entry_id=decision_id,
        lifecycle="measured",
        raw_idempotency_key="contract-outcome",
        evidence_source_kind="account_balance_delta",
        measurement_window_start=now,
        measurement_window_end=now,
        result_json='{"delta_usd":"150"}',
        confidence="high",
        explanation="Measured outcome recorded.",
    )

    response = client.get(f"/api/v1/recommendations/{rec_id}/contract")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "atlas-recommendation-contract/v1"
    assert body["recommendation_id"] == rec_id
    assert body["goal"]["goal_id"] == recommendation.goal_id
    assert body["evidence"]["forecast_id"]
    assert body["risks"] == []
    assert body["confidence"] == "high"
    assert len(body["approvals"]) == 1
    approval = body["approvals"][0]
    assert approval["decision_journal_entry_id"] == decision_id
    assert approval["action"] == "accept"
    assert len(approval["outcome_evaluations"]) == 1
    evaluation = approval["outcome_evaluations"][0]
    assert evaluation["lifecycle"] == "measured"
    assert evaluation["evidence_source_kind"] == "account_balance_delta"
    assert len(evaluation["evidence_reference_hash"]) == 64
    assert evaluation["confidence"] == "high"
    # The linkage response never echoes raw evidence or measured payloads.
    serialized = response.text
    assert "delta_usd" not in serialized
    assert "Measured outcome recorded" not in serialized


def test_get_recommendation_contract_excludes_rejected_and_deferred_decisions(
    client, enable_read_flag, db_session
):
    rec_id = _recommendation_id_for(client, db_session, enable_read_flag)
    for action in ("reject", "defer"):
        response = client.post(
            f"/api/v1/recommendations/{rec_id}/decisions",
            json={"action": action, "decision_etag": f"{rec_id}-d1"},
            headers=_decision_headers(f"contract-{action}", f"{rec_id}-d1"),
        )
        assert response.status_code == 201, response.text

    response = client.get(f"/api/v1/recommendations/{rec_id}/contract")
    assert response.status_code == 200, response.text
    assert response.json()["approvals"] == []


def test_get_recommendation_contract_404_is_indistinguishable_from_cross_user(
    client, enable_read_flag, db_session
):
    """A real other-user recommendation is indistinguishable from missing."""
    from app.forecasts.recommendation_repository import RecommendationRepository

    other_user, other_goal, _forecast, version = _build_world(
        db_session,
        user_sub="contract-intruder",
        forecast_id="44444444-4444-4444-8444-444444444444",
    )
    other_recommendation = RecommendationRepository(db_session).persist(
        user_id=int(other_user.id),
        goal_id=int(other_goal.id),
        forecast_version_id=str(version.id),
        recommendation_kind="hold",
        rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    ).recommendation
    cross_user = client.get(
        f"/api/v1/recommendations/{other_recommendation.id}/contract"
    )
    missing = client.get(
        "/api/v1/recommendations/99999999-9999-4999-8999-999999999999/contract"
    )
    expected = {
        "code": "recommendation_not_found",
        "message": "Recommendation not found.",
    }
    assert cross_user.status_code == missing.status_code == 404
    assert cross_user.json() == missing.json() == expected

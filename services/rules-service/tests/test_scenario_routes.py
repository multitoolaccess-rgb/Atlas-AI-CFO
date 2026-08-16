"""Owner-scoped Scenario Lab route contracts using synthetic baseline fixtures."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.calculations.projection import ProjectionRequest, project_scenarios
from app.config import settings
from app.database import SessionLocal
from app.forecasts.canonical_state import CanonicalProjectionState, hash_input_state
from app.main import app
from app.models import Forecast, ForecastVersion, Goal, User


class _Adapter:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def load_projection_state(self, *, user_id: str, goal_id: int):
        self.calls += 1
        return self.state


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 15, tzinfo=timezone.utc)


def _state(goal_id: int = 1, user_id: str = "alex") -> CanonicalProjectionState:
    instant = "2026-01-15T00:00:00Z"
    return CanonicalProjectionState.model_validate({
        "schema_version": "atlas-projection-state/v1",
        "canonicalization": {"canonical_json_version": "atlas-canonical-json/v1", "hash_schema_version": "atlas-input-state-hash/v1", "hash_algorithm": "sha256"},
        "user_id": user_id, "goal_id": goal_id, "as_of_timestamp": instant, "currency": "USD",
        "current_value_components": [{"kind": "investment", "amount": "1000", "source_reference": "atlas-test-account", "observed_at": instant}],
        "contribution_inputs": [{"kind": "monthly_investable_cash_flow", "amount": "100", "source_reference": "atlas-test-plan", "observed_at": instant}],
        "freshness": {"max_data_age_days": 30, "observed_age_days": 0, "source_updated_at": instant},
        "provenance": [{"source_system": "atlas-test", "reference_id": "baseline", "observed_at": instant, "record_count": 1, "source_state_hash": "a" * 64}],
        "missing_data_codes": [], "reconciliation_state": "reconciled",
    })


def _baseline(state: CanonicalProjectionState) -> tuple[Forecast, ForecastVersion]:
    request = ProjectionRequest(
        currency="USD", current_balance=Decimal("1000"), monthly_contribution=Decimal("100"), horizon_months=12,
        calculation_date=date(2026, 1, 15), data_as_of=date(2026, 1, 15), max_data_age_days=30,
        contribution_timing="end_of_month", annual_inflation_rate=Decimal("0.02"),
        annual_return_rates={"conservative": Decimal("0.02"), "base": Decimal("0.04"), "optimistic": Decimal("0.06")}, target_amount=Decimal("2500"),
    )
    result = project_scenarios(request)
    output = {"drivers": {"target_amount": str(result.drivers.target_amount)}, "scenarios": {}}
    for name, item in result.scenarios.items():
        output["scenarios"][name] = {"ending_balance": str(item.ending_balance), "target_gap": str(item.target_gap), "reaches_target": item.reaches_target}
    forecast = Forecast(id="11111111-1111-4111-8111-111111111111", user_id=1, goal_id=1, forecast_kind="goal_projection", currency="USD", lifecycle_state="active", latest_version_number=1)
    version = ForecastVersion(
        id="22222222-2222-4222-8222-222222222222", forecast_id=forecast.id, version_number=1,
        input_state_hash=hash_input_state(state), idempotency_key_hash="c" * 64, snapshot_schema_version="atlas-projection-state/v1", hash_schema_version="atlas-input-state-hash/v1",
        model_version="atlas-monthly-scenarios/v1", calculation_version="atlas-monthly-scenarios/v1", currency="USD",
        calculated_at=datetime(2026, 1, 15, tzinfo=timezone.utc), data_as_of=datetime(2026, 1, 15, tzinfo=timezone.utc), max_data_age_days=30, data_age_days=0,
        input_snapshot_json=json.dumps({"state": state.hash_payload()}), assumption_snapshot_json="{}", output_snapshot_json=json.dumps(output), provenance_snapshot_json="{}", ending_balance=result.scenarios["base"].ending_balance, target_gap=result.scenarios["base"].target_gap or Decimal("0"),
    )
    return forecast, version


@pytest.fixture()
def scenario_world(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "atlas_scenario_lab_enabled", True)
    monkeypatch.setattr("app.routes.scenarios.datetime", _FrozenDateTime)
    state = _state()
    adapter = _Adapter(state)
    monkeypatch.setattr("app.routes.scenarios.HttpFinlynqProjectionStateAdapter", lambda **kwargs: adapter)
    user = db_session.scalar(select(User).where(User.local_user_sub == settings.local_user))
    if user is None:
        user = User(id=1, local_user_sub=settings.local_user, email="alex@example.com", hashed_password="synthetic")
        db_session.add(user)
        db_session.flush()
    goal = Goal(id=1, user_id=user.id, name="Synthetic Scenario Goal", target_amount=2500.0, horizon_years=1, priority=0, is_archived=False)
    db_session.add(goal)
    forecast, version = _baseline(state)
    forecast.user_id = user.id
    db_session.add(forecast)
    db_session.add(version)
    db_session.commit()
    return client, db_session, adapter


def test_scenario_generation_forwards_validated_session_cookie(scenario_world, monkeypatch):
    client, _db, adapter = scenario_world
    captured = {}
    monkeypatch.setattr(
        "app.routes.scenarios.HttpFinlynqProjectionStateAdapter",
        lambda **kwargs: (captured.update(kwargs) or adapter),
    )
    response = client.post(
        "/api/v1/goals/1/scenarios",
        json={"monthly_contribution_delta": "10"},
        headers={"Idempotency-Key": "cookie-scenario-forward"},
    )
    assert response.status_code == 201
    assert captured["authorization"].startswith("Bearer ")
    from app.config import settings
    assert captured["authorization"] != settings.jwt_secret


def test_generate_read_compare_list_and_archive_are_owner_scoped(scenario_world):
    client, db, adapter = scenario_world
    headers = {"Idempotency-Key": "route-scenario-1"}
    first = client.post("/api/v1/goals/1/scenarios", json={"monthly_contribution_delta": "50"}, headers=headers)
    assert first.status_code == 201, first.text
    payload = first.json()
    assert payload["currency"] == "USD"
    assert payload["comparison"]["probability"] if "probability" in payload["comparison"] else True
    assert adapter.calls == 1
    replay = client.post("/api/v1/goals/1/scenarios", json={"monthly_contribution_delta": "50"}, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["version_id"] == payload["version_id"]
    scenario_id = payload["scenario_id"]
    read = client.get(f"/api/v1/scenarios/{scenario_id}")
    assert read.status_code == 200
    compare = client.get(f"/api/v1/scenarios/{scenario_id}/compare")
    assert compare.status_code == 200
    listed = client.get("/api/v1/goals/1/scenarios?limit=1")
    assert listed.status_code == 200 and listed.json()["items"][0]["scenario_id"] == scenario_id
    archived = client.post(f"/api/v1/scenarios/{scenario_id}/archive", headers={"Idempotency-Key": "archive-1"})
    assert archived.status_code == 200 and archived.json()["lifecycle_state"] == "archived"
    historical = client.get(f"/api/v1/scenarios/{scenario_id}/versions/1")
    assert historical.status_code == 200
    assert client.get("/api/v1/goals/999/scenarios").status_code == 404


def test_archived_history_survives_new_database_session(scenario_world):
    client, db, _adapter = scenario_world
    generated = client.post("/api/v1/goals/1/scenarios", json={"monthly_contribution_delta": "25"}, headers={"Idempotency-Key": "restart-session-1"})
    assert generated.status_code == 201
    scenario_id = generated.json()["scenario_id"]
    archived = client.post(f"/api/v1/scenarios/{scenario_id}/archive", headers={"Idempotency-Key": "restart-session-archive"})
    assert archived.status_code == 200
    db.close()
    with SessionLocal() as reopened:
        persisted = reopened.execute(select(ForecastVersion).where(ForecastVersion.id == "22222222-2222-4222-8222-222222222222")).scalar_one()
        assert persisted.version_number == 1
    historical = client.get(f"/api/v1/scenarios/{scenario_id}/versions/1")
    assert historical.status_code == 200
    assert historical.json()["lifecycle_state"] == "archived"


def test_strict_body_rejects_owner_state_hash_and_result_fields_without_echo(scenario_world):
    client, _, _ = scenario_world
    response = client.post(
        "/api/v1/goals/1/scenarios",
        json={"monthly_contribution_delta": "1", "owner_id": 999, "result_snapshot": "SECRET-SYNTHETIC", "canonical_state": "SECRET-SYNTHETIC"},
        headers={"Idempotency-Key": "route-sensitive"},
    )
    assert response.status_code == 422
    assert "SECRET-SYNTHETIC" not in response.text
    assert "owner_id" not in response.text


def test_default_off_is_server_owned(scenario_world, monkeypatch):
    client, _, adapter = scenario_world
    monkeypatch.setattr(settings, "atlas_scenario_lab_enabled", False)
    response = client.post("/api/v1/goals/1/scenarios", json={"monthly_contribution_delta": "1"}, headers={"Idempotency-Key": "off-1"})
    assert response.status_code == 503
    assert adapter.calls == 0


def test_scenario_dates_outside_the_projection_horizon_return_422_validation(scenario_world):
    """A user date beyond the baseline horizon is a validation error, not a 503.

    The synthetic baseline runs 12 monthly boundaries through 2026-12-31, so a
    contribution stop date in 2027 must fail with an actionable
    ``scenario_validation_error`` instead of the generic availability 503 the
    UI previously showed as "Scenario Lab could not complete that request".
    """
    client, _, _ = scenario_world
    response = client.post(
        "/api/v1/goals/1/scenarios",
        json={"monthly_contribution_delta": "50", "contribution_stop_date": "2027-01-15"},
        headers={"Idempotency-Key": "validation-horizon-1"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "scenario_validation_error"
    assert "horizon" in body["message"]


def test_negative_contribution_scenario_returns_422_validation(scenario_world):
    client, _, _ = scenario_world
    response = client.post(
        "/api/v1/goals/1/scenarios",
        json={"monthly_contribution_delta": "-1000"},
        headers={"Idempotency-Key": "validation-negative-1"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "scenario_validation_error"


def test_compare_limit_and_incompatible_owner_resources_are_bounded(scenario_world):
    client, _, _ = scenario_world
    ids = []
    for index in range(3):
        response = client.post("/api/v1/goals/1/scenarios", json={"monthly_contribution_delta": str(index + 1)}, headers={"Idempotency-Key": f"compare-{index}"})
        assert response.status_code == 201
        ids.append(response.json()["scenario_id"])
    response = client.post("/api/v1/scenarios/compare", json={"scenario_ids": ids})
    assert response.status_code == 200
    too_many = client.post("/api/v1/scenarios/compare", json={"scenario_ids": ids + [ids[0]]})
    assert too_many.status_code == 422

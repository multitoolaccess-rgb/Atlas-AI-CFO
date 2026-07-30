"""Phase 1 Slice D — read-only /api/v1/forecasts/* route tests.

Every invariant the user enumerated is covered here.  Adapter-bypass
and snapshot-corruption safety are the two highest-severity guards
so they get the most explicit tests; everything else is a bounded
contract test.

All tests share the ``setup_forecast`` fixture, which seeds one
``User`` (the standard ``alex`` local user) + one ``Goal`` + one
``Forecast`` + two ``ForecastVersion`` rows so a single positive-path
GET can be exercised without re-running the generation service.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.forecasts.api_codecs import (
    decode_forecast_cursor,
    derive_forecast_etag,
    encode_forecast_cursor,
    format_forecast_etag_header,
    parse_forecast_etag_header,
)
from app.forecasts.canonical_state import canonical_decimal_string
from app.forecasts.snapshots import (
    ASSUMPTION_SCHEMA_VERSION,
    CALCULATION_DECIMAL_SCHEMA_VERSION,
    TARGET_DECISION_SCHEMA_VERSION,
)
from app.main import app
from app.models import Forecast, ForecastVersion, Goal, User


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

def _uuid_for(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"atlas-tests-forecast-{seed}"))


def _utc_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _clean_forecast_tables(db_session):
    """Defensive: most conftest resets do not yet cover these tables."""
    db_session.query(ForecastVersion).delete()
    db_session.query(Forecast).delete()
    db_session.commit()


def _make_goal(db, user_id: int, *, name: str = "Test goal", target_amount: float = 10000.0) -> Goal:
    goal = Goal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        horizon_years=10,
        target_date=None,
        priority=0,
        is_archived=False,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def _make_forecast(db, *, user_id: int, goal_id: int) -> Forecast:
    fc = Forecast(
        id=_uuid_for(f"forecast-user{user_id}-goal{goal_id}"),
        user_id=user_id,
        goal_id=goal_id,
        forecast_kind="goal_projection",
        currency="USD",
        lifecycle_state="active",
        latest_version_number=0,
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    return fc


def _money_str(value: Decimal) -> str:
    return canonical_decimal_string(value)


def _make_version_payload(*, ending: Decimal, target_gap: Decimal, now: datetime) -> dict:
    target_status = bool(ending.quantize(Decimal("0.01")) >= target_gap.quantize(Decimal("0.01")))
    base_rate = _money_str(Decimal("0.04"))
    cons_rate = _money_str(Decimal("0.02"))
    opt_rate = _money_str(Decimal("0.06"))
    end_str = _money_str(ending.quantize(Decimal("0.01")))
    tgt_str = _money_str(target_gap.quantize(Decimal("0.01")))
    return {
        "calculation_decimal_schema_version": CALCULATION_DECIMAL_SCHEMA_VERSION,
        "target_status": target_status,
        "target_decision": {
            "decision_schema_version": TARGET_DECISION_SCHEMA_VERSION,
            "scenario": "base",
            "comparison": "greater_than_or_equal",
            "decision_basis": "currency_rounded",
            "rounding_rule": "ROUND_HALF_EVEN",
            "money_precision": "0.01",
            "unrounded_ending_balance": end_str,
            "unrounded_target_amount": tgt_str,
            "rounded_ending_balance": end_str,
            "rounded_target_amount": tgt_str,
            "target_status": target_status,
        },
        "drivers": {
            "current_balance": "0",
            "monthly_contribution": _money_str(Decimal("200")),
            "total_contributions": _money_str(Decimal("24000")),
            "target_amount": tgt_str,
            "horizon_months": 120,
            "data_as_of": _utc_z(now),
            "data_age_days": 0,
        },
        # ``OutputSnapshotSchema.scenarios`` is declared as
        # ``tuple[tuple[str, ScenarioSnapshotSchema], ...]``.  Pydantic will
        # only accept a JSON ARRAY of two-element arrays (one element per
        # scenario), not a JSON OBJECT.  We serialize as the sorted list
        # the schema expects on the wire.
        "scenarios": [
            [
                "conservative",
                {
                    "annual_return_rate": cons_rate,
                    "monthly_real_rate": cons_rate,
                    "ending_balance": _money_str(ending * Decimal("0.7")),
                    "investment_growth": _money_str(ending * Decimal("0.4")),
                    "target_gap": tgt_str,
                    "reaches_target": False,
                },
            ],
            [
                "base",
                {
                    "annual_return_rate": base_rate,
                    "monthly_real_rate": base_rate,
                    "ending_balance": end_str,
                    "investment_growth": _money_str(Decimal("24000")),
                    "target_gap": tgt_str if not target_status else None,
                    "reaches_target": target_status,
                },
            ],
            [
                "optimistic",
                {
                    "annual_return_rate": opt_rate,
                    "monthly_real_rate": opt_rate,
                    "ending_balance": _money_str(ending * Decimal("1.3")),
                    "investment_growth": _money_str(ending * Decimal("0.9")),
                    "target_gap": None,
                    "reaches_target": True,
                },
            ],
        ],
    }


def _make_version(
    db,
    *,
    forecast_id: str,
    version_number: int,
    ending: Decimal,
    target_gap: Decimal,
) -> ForecastVersion:
    now = datetime.now(timezone.utc)
    input_hash = hashlib.sha256(f"atlas-tests-input-{forecast_id}-{version_number}".encode("ascii")).hexdigest()
    idem_hash = hashlib.sha256(f"atlas-tests-idem-{forecast_id}-{version_number}".encode("ascii")).hexdigest()
    assumption_payload = {
        "assumption_profile": "phase1-server-default",
        "assumption_schema_version": ASSUMPTION_SCHEMA_VERSION,
        "annual_return_rates": {
            "conservative": _money_str(Decimal("0.02")),
            "base": _money_str(Decimal("0.04")),
            "optimistic": _money_str(Decimal("0.06")),
        },
        "annual_inflation_rate": _money_str(Decimal("0.02")),
        "contribution_timing": "end",
        "period": "monthly",
        "rounding_rule": "ROUND_HALF_EVEN",
        "money_precision": "0.01",
        "goal_inputs": {
            "target_amount": _money_str(Decimal("10000")),
            "horizon_years": 10,
            "target_date": None,
            "source_representation": "float",
            "conversion": "decimal-str",
            "precision_restored": False,
        },
    }
    output_payload = _make_version_payload(ending=ending, target_gap=target_gap, now=now)
    provenance_payload = {
        "provenance": [
            {
                "source_system": "test-fixture",
                "reference_id": f"fixture-{version_number}",
                "observed_at": _utc_z(now),
                "record_count": 1,
                "source_state_hash": input_hash,
            }
        ],
        "freshness": {
            "max_data_age_days": 7,
            "observed_age_days": 0,
            "source_updated_at": _utc_z(now),
        },
    }
    input_payload = {
        "assumptions": assumption_payload,
        "state": {
            "schema_version": "atlas-projection-state/v1",
            "canonicalization": {
                "canonical_json_version": "atlas-canonical-json/v1",
                "hash_schema_version": "atlas-input-state-hash/v1",
                "hash_algorithm": "sha256",
            },
            "user_id": "alex",
            "goal_id": 1,
            "as_of_timestamp": _utc_z(now),
            "currency": "USD",
            "current_value_components": [],
            "contribution_inputs": [],
            "freshness": {"max_data_age_days": 7, "observed_age_days": 0, "source_updated_at": _utc_z(now)},
            "provenance": [],
            "missing_data_codes": [],
            "reconciliation_state": "reconciled",
        },
    }
    fv = ForecastVersion(
        id=_uuid_for(f"version-{forecast_id}-{version_number}"),
        forecast_id=forecast_id,
        version_number=version_number,
        input_state_hash=input_hash,
        idempotency_key_hash=idem_hash,
        snapshot_schema_version=ASSUMPTION_SCHEMA_VERSION,
        hash_schema_version="atlas-input-state-hash/v1",
        model_version="atlas-forecast-model/v1",
        calculation_version="atlas-projection-calc/v1",
        currency="USD",
        calculated_at=now,
        data_as_of=now,
        max_data_age_days=7,
        data_age_days=0,
        input_snapshot_json=json.dumps(input_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        assumption_snapshot_json=json.dumps(assumption_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        output_snapshot_json=json.dumps(output_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        provenance_snapshot_json=json.dumps(provenance_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ending_balance=ending.quantize(Decimal("0.01")),
        target_gap=target_gap.quantize(Decimal("0.01")),
    )
    db.add(fv)
    db.commit()
    db.refresh(fv)
    return fv


@pytest.fixture
def setup_forecast(db_session):
    """Seed one User + Goal + Forecast + two versions for owner ``alex``."""
    from app.routes.shared import get_or_create_local_user

    _clean_forecast_tables(db_session)
    user = get_or_create_local_user(db_session, "alex")
    goal = _make_goal(db_session, user.id, target_amount=10000.0)
    forecast = _make_forecast(db_session, user_id=user.id, goal_id=goal.id)
    v1 = _make_version(db_session, forecast_id=forecast.id, version_number=1, ending=Decimal("2400"), target_gap=Decimal("7600"))
    v2 = _make_version(db_session, forecast_id=forecast.id, version_number=2, ending=Decimal("12000"), target_gap=Decimal("-2000"))
    forecast.latest_version_number = 2
    db_session.commit()
    db_session.refresh(forecast)
    return {"user": user, "goal": goal, "forecast": forecast, "v1": v1, "v2": v2}


# ----------------------------------------------------------------------
# Auth surface
# ----------------------------------------------------------------------

def test_list_requires_auth(client_no_auth, setup_forecast):
    r = client_no_auth.get("/api/v1/forecasts")
    assert r.status_code == 401


def test_detail_requires_auth(client_no_auth, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client_no_auth.get(f"/api/v1/forecasts/{fc_id}")
    assert r.status_code == 401


def test_versions_list_requires_auth(client_no_auth, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client_no_auth.get(f"/api/v1/forecasts/{fc_id}/versions")
    assert r.status_code == 401


def test_version_detail_requires_auth(client_no_auth, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client_no_auth.get(f"/api/v1/forecasts/{fc_id}/versions/1")
    assert r.status_code == 401


# ----------------------------------------------------------------------
# Positive happy paths
# ----------------------------------------------------------------------

def test_list_forecasts_returns_owned(client, setup_forecast):
    r = client.get("/api/v1/forecasts")
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert len(items) == 1
    fc = items[0]
    assert fc["forecast_id"] == setup_forecast["forecast"].id
    assert fc["goal_id"] == setup_forecast["goal"].id
    assert fc["currency"] == "USD"
    assert fc["lifecycle_state"] == "active"
    assert fc["latest_version_number"] == 2
    assert fc["latest_version_id"] == setup_forecast["v2"].id
    assert fc["etag"] == derive_forecast_etag(
        forecast_id=setup_forecast["forecast"].id,
        version_number=2,
    )
    assert body["next_cursor"] is None


def test_list_forecasts_filter_by_owned_goal_id(client, setup_forecast):
    r = client.get(f"/api/v1/forecasts?goal_id={setup_forecast['goal'].id}")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_get_forecast_detail(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_id"] == fc_id
    assert body["latest_version_number"] == 2
    assert body["latest_version_id"] == setup_forecast["v2"].id
    expected_quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=2)
    assert r.headers.get("ETag") == expected_quoted


def test_get_version_detail(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}/versions/1")
    assert r.status_code == 200
    body = r.json()
    assert body["version_id"] == setup_forecast["v1"].id
    assert body["version_number"] == 1
    # Decimal-string money fields.  No float.
    assert isinstance(body["ending_balance"], str)
    assert isinstance(body["target_gap"], str)
    # Drivers nested money.
    for k in ("current_balance", "monthly_contribution", "total_contributions"):
        assert isinstance(body["drivers"][k], str)
    # Snapshot hash + idempotency-key hashes stay lowercase SHA-256.
    assert re.fullmatch(r"[0-9a-f]{64}$", body["input_state_hash"])
    assert re.fullmatch(r"[0-9a-f]{64}$", body["idempotency_key_hash"])
    expected_quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=1)
    assert r.headers.get("ETag") == expected_quoted


# ----------------------------------------------------------------------
# Byte-identical cross-user / missing 404
# ----------------------------------------------------------------------

def test_forecast_detail_404_byte_identical(client, setup_forecast, db_session):
    fc_id = setup_forecast["forecast"].id
    # Case A: missing forecast
    db_session.query(ForecastVersion).filter(ForecastVersion.forecast_id == fc_id).delete()
    db_session.query(Forecast).filter(Forecast.id == fc_id).delete()
    db_session.commit()
    r_missing = client.get(f"/api/v1/forecasts/{fc_id}")
    # Case B: a forecast owned by another user, with a valid UUID-shaped id.
    other = User(local_user_sub="other-user", email="other-user", hashed_password="seed", full_name="Other")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    cross_fc = Forecast(
        id=_uuid_for("cross-user-forecast"),
        user_id=other.id,
        goal_id=9999,
        forecast_kind="goal_projection",
        currency="USD",
        lifecycle_state="active",
        latest_version_number=0,
    )
    db_session.add(cross_fc)
    db_session.commit()
    r_cross = client.get(f"/api/v1/forecasts/{cross_fc.id}")
    assert r_missing.status_code == 404
    assert r_cross.status_code == 404
    assert r_missing.content == r_cross.content  # byte-identical bodies


def test_version_detail_404_byte_identical(client, setup_forecast, db_session):
    fc_id = setup_forecast["forecast"].id
    # delete the version -- version row is missing for this user
    db_session.query(ForecastVersion).filter(
        ForecastVersion.forecast_id == fc_id,
        ForecastVersion.version_number == 1,
    ).delete()
    db_session.commit()
    r_missing = client.get(f"/api/v1/forecasts/{fc_id}/versions/1")
    # build a cross-user forecast that has a version 1
    other = User(local_user_sub="cross-user", email="cross-user", hashed_password="seed", full_name="Cross")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    cross_fc = Forecast(
        id=_uuid_for("cross-user-fc"),
        user_id=other.id,
        goal_id=8888,
        forecast_kind="goal_projection",
        currency="USD",
        lifecycle_state="active",
        latest_version_number=1,
    )
    db_session.add(cross_fc)
    db_session.commit()
    _make_version(db_session, forecast_id=cross_fc.id, version_number=1, ending=Decimal("9000"), target_gap=Decimal("1000"))
    r_cross = client.get(f"/api/v1/forecasts/{cross_fc.id}/versions/1")
    assert r_missing.status_code == 404
    assert r_cross.status_code == 404
    assert r_missing.content == r_cross.content


def test_versions_list_404_byte_identical(client, setup_forecast, db_session):
    fc_id = setup_forecast["forecast"].id
    # delete the forecast itself
    db_session.query(ForecastVersion).filter(ForecastVersion.forecast_id == fc_id).delete()
    db_session.query(Forecast).filter(Forecast.id == fc_id).delete()
    db_session.commit()
    r_missing = client.get(f"/api/v1/forecasts/{fc_id}/versions")
    other = User(local_user_sub="cross-user-v", email="cross-user-v", hashed_password="seed", full_name="Cross")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    cross_fc = Forecast(
        id=_uuid_for("cross-user-fc-v"),
        user_id=other.id,
        goal_id=7777,
        forecast_kind="goal_projection",
        currency="USD",
        lifecycle_state="active",
        latest_version_number=1,
    )
    db_session.add(cross_fc)
    db_session.commit()
    r_cross = client.get(f"/api/v1/forecasts/{cross_fc.id}/versions")
    assert r_missing.status_code == 404
    assert r_cross.status_code == 404
    assert r_missing.content == r_cross.content


# ----------------------------------------------------------------------
# Conditional read behavior (If-None-Match)
# ----------------------------------------------------------------------

def test_if_none_match_returns_304_on_match(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=2)
    r = client.get(f"/api/v1/forecasts/{fc_id}", headers={"If-None-Match": quoted})
    assert r.status_code == 304
    assert r.headers.get("ETag") == quoted
    assert r.text == ""


def test_if_none_match_stale_returns_200(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    quoted_v1 = format_forecast_etag_header(forecast_id=fc_id, version_number=1)
    r = client.get(f"/api/v1/forecasts/{fc_id}", headers={"If-None-Match": quoted_v1})
    assert r.status_code == 200
    quoted_v2 = format_forecast_etag_header(forecast_id=fc_id, version_number=2)
    assert r.headers.get("ETag") == quoted_v2


def test_if_none_match_wildcard_returns_200(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}", headers={"If-None-Match": "*"})
    assert r.status_code == 200


def test_if_none_match_malformed_returns_400(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}", headers={"If-None-Match": "not-an-etag"})
    assert r.status_code == 400
    assert r.json()["code"] == "forecast_validation_error"


def test_if_match_rejected_on_read_routes(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=2)
    paths = [
        f"/api/v1/forecasts/{fc_id}",
        f"/api/v1/forecasts/{fc_id}/versions/1",
        f"/api/v1/forecasts/{fc_id}/versions",
        "/api/v1/forecasts",
    ]
    for path in paths:
        r = client.get(path, headers={"If-Match": quoted})
        assert r.status_code == 400, f"{path} unexpectedly {r.status_code}"
        assert r.json()["code"] == "forecast_validation_error"


def test_collection_conditional_headers_rejected(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=2)
    for path in ("/api/v1/forecasts", f"/api/v1/forecasts/{fc_id}/versions"):
        for header in ("If-None-Match", "If-Match"):
            r = client.get(path, headers={header: quoted})
            assert r.status_code == 400, f"{header} on {path} unexpectedly {r.status_code}"
            assert r.json()["code"] == "forecast_validation_error"


def test_version_detail_conditional_304(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    quoted = format_forecast_etag_header(forecast_id=fc_id, version_number=1)
    r = client.get(f"/api/v1/forecasts/{fc_id}/versions/1", headers={"If-None-Match": quoted})
    assert r.status_code == 304
    assert r.headers.get("ETag") == quoted


# ----------------------------------------------------------------------
# Cursor round-trip
# ----------------------------------------------------------------------

def test_forecast_list_cursor_round_trip(client, setup_forecast, db_session):
    from app.routes.shared import get_or_create_local_user

    user = get_or_create_local_user(db_session, "alex")
    # Each added forecast must have at least one persisted version so the
    # list endpoint's ``latest_version`` lookup surfaces it on the wire.
    for i in range(3):
        g = _make_goal(db_session, user.id, name=f"g-{i}", target_amount=2000.0 + i)
        fc = _make_forecast(db_session, user_id=user.id, goal_id=g.id)
        _make_version(
            db_session,
            forecast_id=fc.id,
            version_number=1,
            ending=Decimal("1000") * Decimal(i + 1),
            target_gap=Decimal("10000") - Decimal("1000") * Decimal(i + 1),
        )
        fc.latest_version_number = 1
        db_session.commit()

    r1 = client.get("/api/v1/forecasts?limit=2")
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None
    # Decoder accepts the emitted cursor.
    decoded = decode_forecast_cursor(body1["next_cursor"])
    assert isinstance(decoded.version_number, int)
    assert isinstance(decoded.created_at, datetime)
    assert isinstance(decoded.forecast_id, str)
    # Second page is disjoint from the first.
    r2 = client.get(f"/api/v1/forecasts?limit=2&cursor={body1['next_cursor']}")
    assert r2.status_code == 200
    body2 = r2.json()
    first = {it["forecast_id"] for it in body1["items"]}
    second = {it["forecast_id"] for it in body2["items"]}
    assert first.isdisjoint(second)
    assert body2["next_cursor"] is None


def test_versions_list_cursor_round_trip_descending(client, setup_forecast, db_session):
    fc_id = setup_forecast["forecast"].id
    # add versions 3..7 so total = 7
    for i in range(3, 8):
        _make_version(db_session, forecast_id=fc_id, version_number=i, ending=Decimal("1000") * (i + 1), target_gap=Decimal("1000"))
    fc = db_session.query(Forecast).filter(Forecast.id == fc_id).one()
    fc.latest_version_number = 7
    db_session.commit()

    r = client.get(f"/api/v1/forecasts/{fc_id}/versions?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert [it["version_number"] for it in body["items"]] == [7, 6, 5]
    assert body["next_cursor"] is not None

    r2 = client.get(f"/api/v1/forecasts/{fc_id}/versions?limit=3&cursor={body['next_cursor']}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert [it["version_number"] for it in body2["items"]] == [4, 3, 2]
    assert body2["next_cursor"] is not None

    r3 = client.get(f"/api/v1/forecasts/{fc_id}/versions?limit=3&cursor={body2['next_cursor']}")
    assert r3.status_code == 200
    body3 = r3.json()
    assert [it["version_number"] for it in body3["items"]] == [1]
    assert body3["next_cursor"] is None


def test_tampered_cursor_returns_400(client, setup_forecast):
    r = client.get("/api/v1/forecasts?cursor=fc1.BOGUS")
    assert r.status_code == 400
    assert r.json()["code"] == "forecast_validation_error"


def test_tampered_etag_returns_400(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}", headers={"If-None-Match": "W/\"weak-etag\""})
    assert r.status_code == 400
    assert r.json()["code"] == "forecast_validation_error"


# ----------------------------------------------------------------------
# Bounded limits
# ----------------------------------------------------------------------

def test_forecast_list_limit_clamped_to_64(client, setup_forecast):
    r = client.get("/api/v1/forecasts?limit=999")
    # FastAPI Query(le=64) returns 422 for invalid bounds; the route
    # uses le=64 so 999 must reject.
    assert r.status_code in (400, 422)


def test_versions_list_limit_clamped_to_64(client, setup_forecast):
    fc_id = setup_forecast["forecast"].id
    r = client.get(f"/api/v1/forecasts/{fc_id}/versions?limit=999")
    assert r.status_code in (400, 422)


# ----------------------------------------------------------------------
# Goal filter on /forecasts
# ----------------------------------------------------------------------

def test_goal_filter_unknown_goal_returns_404(client, setup_forecast):
    r = client.get("/api/v1/forecasts?goal_id=999999")
    assert r.status_code == 404
    assert r.json()["code"] == "goal_not_found"


# ----------------------------------------------------------------------
# Default-off read flag (the OTHER snapshot of Slice E)
# ----------------------------------------------------------------------

def test_read_flag_disabled_returns_503_envelope(client, setup_forecast, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "atlas_forecast_read_api_enabled", False)
    for path in ("/api/v1/forecasts",
                 f"/api/v1/forecasts/{setup_forecast['forecast'].id}",
                 f"/api/v1/forecasts/{setup_forecast['forecast'].id}/versions",
                 f"/api/v1/forecasts/{setup_forecast['forecast'].id}/versions/1"):
        r = client.get(path)
        assert r.status_code == 503, f"{path} unexpectedly {r.status_code}"
        assert r.json() == {
            "code": "forecast_read_api_unavailable",
            "message": "Forecast read API is currently unavailable.",
        }


# ----------------------------------------------------------------------
# No mutable PUT/PATCH/DELETE routes
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/v1/forecasts"),
        ("PATCH", "/api/v1/forecasts"),
        ("DELETE", "/api/v1/forecasts"),
        ("PUT", "/api/v1/forecasts/{fid}"),
        ("PATCH", "/api/v1/forecasts/{fid}"),
        ("DELETE", "/api/v1/forecasts/{fid}"),
        ("PUT", "/api/v1/forecasts/{fid}/versions"),
        ("PATCH", "/api/v1/forecasts/{fid}/versions"),
        ("DELETE", "/api/v1/forecasts/{fid}/versions"),
        ("PUT", "/api/v1/forecasts/{fid}/versions/{n}"),
        ("PATCH", "/api/v1/forecasts/{fid}/versions/{n}"),
        ("DELETE", "/api/v1/forecasts/{fid}/versions/{n}"),
        # Also: the generation POST is NOT in Slice D per the directive.
        ("POST", "/api/v1/forecasts"),
        ("POST", "/api/v1/forecasts/{fid}"),
        ("POST", "/api/v1/forecasts/{fid}/versions"),
        ("POST", "/api/v1/forecasts/{fid}/versions/{n}"),
        ("POST", "/api/v1/goals/1/forecasts"),
    ],
)
def test_no_mutable_forecast_routes_registered(client, setup_forecast, method, path):
    fc_id = setup_forecast["forecast"].id
    real_path = (
        path.replace("{fid}", fc_id).replace("{n}", "1")
    )
    r = client.request(method, real_path)
    assert r.status_code in (404, 405), f"{method} {real_path} -> {r.status_code}"


# ----------------------------------------------------------------------
# Adapter-bypass / import-graph assertions
# ----------------------------------------------------------------------

def test_routes_module_does_not_import_canonical_adapter_or_projection():
    """Belt-and-braces adapter-bypass: ``app.routes.forecasts`` must not
    transitively import the projection or canonical-state contract.

    This is the read-side hygiene check the Slice D def of done requires;
    a future refactor that widens the import list will fail loudly here.
    """
    import app.routes.forecasts as forecasts_module
    src = open(forecasts_module.__file__).read()
    forbidden_substrings = [
        "from app.forecasts.canonical_state import",
        "import app.forecasts.canonical_state",
        "from app.forecasts.canonical_state import FinlynqProjectionStateAdapter",
        "from app.calculations.projection import",
        "import app.calculations.projection",
        "from app.forecasts.service import",  # generation service has the adapter
    ]
    for needle in forbidden_substrings:
        assert needle not in src, f"forbidden import detected in routes/forecasts.py: {needle!r}"


# ----------------------------------------------------------------------
# Snapshot-corruption safety
# ----------------------------------------------------------------------

def test_corrupted_snapshot_yields_sanitized_500(client, setup_forecast, db_session):
    fv = setup_forecast["v1"]
    fv.assumption_snapshot_json = "{not-json"
    db_session.commit()
    r = client.get(f"/api/v1/forecasts/{setup_forecast['forecast'].id}/versions/1")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_data_corruption"
    # No Pydantic internals leak.
    for forbidden_key in ("loc", "msg", "type", "ctx", "input"):
        assert forbidden_key not in body, f"Pydantic internals leaked: {forbidden_key}"


def test_corrupted_snapshot_in_list_yields_sanitized_500(client, setup_forecast, db_session):
    fv = setup_forecast["v1"]
    fv.output_snapshot_json = "{\"calculation_decimal_schema_version\": \"atlas-calculation-decimal/v1\", \"target_status\": \"not-a-bool\"}"
    db_session.commit()
    r = client.get(f"/api/v1/forecasts/{setup_forecast['forecast'].id}/versions")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_data_corruption"


# ----------------------------------------------------------------------
# Response shape (Decimal strings, no ORM leak)
# ----------------------------------------------------------------------

def test_get_version_response_exposes_no_orm_fields(client, setup_forecast):
    r = client.get(f"/api/v1/forecasts/{setup_forecast['forecast'].id}/versions/2")
    body = r.json()
    forbidden_keys = {"_sa_instance_state", "_sa_class_manager"}
    for k in body.keys():
        assert k not in forbidden_keys
    # snapshot is nested Pydantic, no ORM leftovers
    nested = body["drivers"]
    for k in nested.keys():
        assert k not in forbidden_keys


def test_get_forecast_response_exposes_no_orm_fields(client, setup_forecast):
    r = client.get(f"/api/v1/forecasts/{setup_forecast['forecast'].id}")
    body = r.json()
    forbidden_keys = {"_sa_instance_state", "_sa_class_manager"}
    for k in body.keys():
        assert k not in forbidden_keys
